"""Import statement PDFs into the database, with deduplication.

Deduplication works at two levels:
1. File: the SHA-256 of the bytes. Re-uploading the exact same PDF does nothing.
2. Operation: a fingerprint of (bank, account, dates, normalized label, amount, n) where ``n`` numbers
   identical operations inside one statement. Two real identical purchases on the same day are kept
   (n=0 and n=1) while the same operation seen in two overlapping statements is stored once.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

import bankparse
from bankparse.detect import BANK_NAMES
from sqlalchemy import delete, exists
from sqlmodel import Session, select
from unidecode import unidecode

from bankparse_api.categorize.service import apply_rules
from bankparse_api.config import get_settings
from bankparse_api.models import (
    Account,
    Balance,
    Space,
    StatementFile,
    Transaction,
    TransactionSource,
)
from bankparse_api.spaces import get_or_create_space, learn_holder, move_account, owner_key


@dataclass
class ImportResult:
    filename: str
    status: str  # imported | already_imported | failed | unsupported
    file_id: int | None = None
    bank: str | None = None
    statement_date: date | None = None
    accounts: list[str] = field(default_factory=list)
    inserted: int = 0
    duplicates: int = 0
    check_ok: bool | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    space_id: int | None = None  # space the statement's accounts belong to
    space_name: str | None = None
    space_created: bool = False  # a new holder: a space was created for them

    def to_dict(self) -> dict:
        data = asdict(self)
        data["statement_date"] = self.statement_date.isoformat() if self.statement_date else None
        return data


def to_cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


def normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", unidecode(label).upper()).strip()


def fingerprint(bank_code: str, account_number: str, t: bankparse.Transaction, occurrence: int) -> str:
    key = "|".join(
        [
            bank_code,
            account_number,
            t.operation_date.isoformat(),
            t.value_date.isoformat() if t.value_date else "",
            normalize_label(t.label),
            str(to_cents(t.amount)),
            str(occurrence),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()


def import_pdf(
    session: Session, filename: str, content: bytes, space_id: int | None = None, fallback_space_id: int | None = None
) -> ImportResult:
    """``space_id``: the user chosen at import. It decides where the statement goes, over the holder read on it,
    also for a file imported before (its accounts are moved). None: the holder read on the statement decides.

    ``fallback_space_id``: the user the file goes to when nothing else tells (no choice and the file could not be
    read, e.g. an unsupported document): the user shown in the app at import. A file always belongs to one user."""
    sha = hashlib.sha256(content).hexdigest()
    record = session.exec(select(StatementFile).where(StatementFile.sha256 == sha)).first()

    if record is not None and record.status == "parsed":
        if space_id is not None and space_id != record.space_id:
            record.chosen_space_id = space_id
            for account in _file_accounts(session, record.id):
                if account.space_id != space_id:
                    move_account(session, account, space_id)
            record.space_id = space_id
            session.add(record)
            session.commit()
        space = session.get(Space, record.space_id) if record.space_id is not None else None
        return ImportResult(
            filename=filename,
            status="already_imported",
            file_id=record.id,
            bank=BANK_NAMES.get(record.bank_code or ""),
            statement_date=record.statement_date,
            check_ok=record.check_ok,
            space_id=space.id if space else None,
            space_name=space.name if space else None,
        )

    if record is None:
        settings = get_settings()
        path = settings.uploads_dir / f"{sha}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        record = StatementFile(
            sha256=sha,
            filename=filename,
            stored_path=str(path.relative_to(settings.data_dir)),
            size=len(content),
        )
        session.add(record)
        session.flush()

    if space_id is not None:
        record.chosen_space_id = space_id
    # Unreadable files keep this one; a parsed statement is routed again by _store_statement.
    record.space_id = space_id or record.space_id or fallback_space_id
    return process(session, record, content)


def process(session: Session, record: StatementFile, content: bytes) -> ImportResult:
    """(Re)parse a stored statement and write its accounts, operations and balances."""
    # Categories survive a re-analysis: remember them by fingerprint before the operations are rebuilt.
    kept_categories = {
        fp: (category, source)
        for fp, category, source in session.exec(
            select(Transaction.fingerprint, Transaction.category, Transaction.category_source)
            .join(TransactionSource, TransactionSource.transaction_id == Transaction.id)
            .where(TransactionSource.file_id == record.id, Transaction.category.is_not(None))
        ).all()
    } if record.id is not None else {}
    remove_file_data(session, record.id, keep_record=True)
    result = ImportResult(filename=record.filename, status="imported", file_id=record.id)
    record.parser_version = bankparse.__version__

    try:
        statement = bankparse.parse(content)
    except bankparse.UnsupportedStatementError as exc:
        record.status, record.error = "unsupported", str(exc)
    except Exception as exc:  # ParseError or anything unexpected: keep the file, report the error
        record.status, record.error = "failed", str(exc)
    else:
        record.status, record.error = "parsed", None
        record.bank_code = statement.bank_code
        record.statement_date = statement.statement_date
        record.check_ok = statement.is_consistent
        result.bank = statement.bank
        result.statement_date = statement.statement_date
        result.check_ok = statement.is_consistent
        result.warnings = statement.warnings
        _store_statement(session, record, statement, result, kept_categories)

    if record.status != "parsed":
        result.status, result.error = record.status, record.error
    session.add(record)
    session.commit()
    return result


def _store_statement(
    session: Session,
    record: StatementFile,
    statement: bankparse.ParsedStatement,
    result: ImportResult,
    kept_categories: dict[str, tuple[str, str | None]] | None = None,
) -> None:
    kept_categories = kept_categories or {}
    new_transactions: list[Transaction] = []
    accounts: dict[str, Account] = {}
    for acc in statement.accounts:
        accounts[acc.account_id] = session.exec(
            select(Account).where(Account.bank_code == statement.bank_code, Account.account_number == acc.account_id)
        ).first()

    # Space: an account already known keeps its space (it may have been moved by hand). New accounts go to
    # the holder's space; when the holder cannot be read, to the space of a known account of the statement.
    known = next((a.space_id for a in accounts.values() if a is not None and a.space_id is not None), None)
    all_known = all(a is not None for a in accounts.values())
    chosen = session.get(Space, record.chosen_space_id) if record.chosen_space_id is not None else None
    if chosen is not None:
        # The user chose: even accounts already known elsewhere go there.
        space, created = chosen, False
        learn_holder(session, space, statement.owner)
        for account in accounts.values():
            if account is not None and account.space_id != space.id:
                move_account(session, account, space.id)
        if statement.owner and owner_key(statement.owner) != space.owner_key:
            result.warnings.append(
                f"Titulaire lu sur le relevé : {statement.owner}. Importé pour « {space.name} » comme demandé."
            )
    elif not statement.accounts and record.space_id is not None:
        space, created = session.get(Space, record.space_id), False  # nothing to route: keep the file's user
    elif known is not None and (statement.owner is None or all_known):
        space, created = session.get(Space, known), False
    else:
        space, created = get_or_create_space(session, statement.owner)
    for acc in statement.accounts:
        if accounts[acc.account_id] is None:
            account = Account(
                bank_code=statement.bank_code,
                bank=statement.bank,
                account_number=acc.account_id,
                label=acc.label,
                owner=statement.owner,
                space_id=space.id,
            )
            session.add(account)
            session.flush()
            accounts[acc.account_id] = account
    result.accounts = [a.custom_label or a.label for a in accounts.values()]
    record.space_id = space.id
    result.space_id, result.space_name, result.space_created = space.id, space.name, created

    # Operations
    occurrences: Counter[tuple] = Counter()
    rows = []
    for t in statement.transactions:
        key = (t.account_id, t.operation_date, t.value_date, normalize_label(t.label), t.amount)
        fp = fingerprint(statement.bank_code, t.account_id, t, occurrences[key])
        occurrences[key] += 1
        rows.append((fp, t))

    existing = {
        fp: tx_id
        for fp, tx_id in session.exec(
            select(Transaction.fingerprint, Transaction.id).where(Transaction.fingerprint.in_([fp for fp, _ in rows]))
        ).all()
    }
    for fp, t in rows:
        tx_id = existing.get(fp)
        if tx_id is None:
            tx = Transaction(
                account_id=accounts[t.account_id].id,
                operation_date=t.operation_date,
                value_date=t.value_date,
                label=t.label,
                amount_cents=to_cents(t.amount),
                fingerprint=fp,
            )
            if fp in kept_categories:
                tx.category, tx.category_source = kept_categories[fp]
            new_transactions.append(tx)
            session.add(tx)
            session.flush()
            tx_id = existing[fp] = tx.id
            result.inserted += 1
        else:
            result.duplicates += 1
        if session.get(TransactionSource, (tx_id, record.id)) is None:
            session.add(TransactionSource(transaction_id=tx_id, file_id=record.id))

    # Operations of merchants already known get their category right away (no LLM call).
    apply_rules(session, new_transactions)

    # Balances (one per account and date)
    for b in statement.balances:
        account = accounts.get(b.account_id)
        if account is None:
            continue
        found = session.exec(select(Balance).where(Balance.account_id == account.id, Balance.date == b.date)).first()
        if found is None:
            session.add(Balance(account_id=account.id, date=b.date, amount_cents=to_cents(b.amount), file_id=record.id))


def _file_accounts(session: Session, file_id: int) -> list[Account]:
    via_tx = (
        select(Transaction.account_id)
        .join(TransactionSource, TransactionSource.transaction_id == Transaction.id)
        .where(TransactionSource.file_id == file_id)
    )
    via_balance = select(Balance.account_id).where(Balance.file_id == file_id)
    return list(session.exec(select(Account).where(Account.id.in_(via_tx.union(via_balance)))).all())


def remove_file_data(session: Session, file_id: int, keep_record: bool = False) -> None:
    """Remove what a file brought: its links, the operations no other file contains, its balances."""
    tx_ids = list(session.exec(select(TransactionSource.transaction_id).where(TransactionSource.file_id == file_id)))
    session.execute(delete(TransactionSource).where(TransactionSource.file_id == file_id))
    if tx_ids:
        still_referenced = exists().where(TransactionSource.transaction_id == Transaction.id)
        session.execute(delete(Transaction).where(Transaction.id.in_(tx_ids), ~still_referenced))
    session.execute(delete(Balance).where(Balance.file_id == file_id))

    # Accounts that no longer have any data.
    used_by_tx = exists().where(Transaction.account_id == Account.id)
    used_by_balance = exists().where(Balance.account_id == Account.id)
    session.execute(delete(Account).where(~used_by_tx, ~used_by_balance))

    if not keep_record:
        record = session.get(StatementFile, file_id)
        if record is not None:
            session.delete(record)
    session.flush()
