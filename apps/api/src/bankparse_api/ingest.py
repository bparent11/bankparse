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

from bankparse_api.config import get_settings
from bankparse_api.models import (
    Account,
    Balance,
    StatementFile,
    Transaction,
    TransactionSource,
)


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


def import_pdf(session: Session, filename: str, content: bytes) -> ImportResult:
    sha = hashlib.sha256(content).hexdigest()
    record = session.exec(select(StatementFile).where(StatementFile.sha256 == sha)).first()

    if record is not None and record.status == "parsed":
        return ImportResult(
            filename=filename,
            status="already_imported",
            file_id=record.id,
            bank=BANK_NAMES.get(record.bank_code or ""),
            statement_date=record.statement_date,
            check_ok=record.check_ok,
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

    return process(session, record, content)


def process(session: Session, record: StatementFile, content: bytes) -> ImportResult:
    """(Re)parse a stored statement and write its accounts, operations and balances."""
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
        _store_statement(session, record, statement, result)

    if record.status != "parsed":
        result.status, result.error = record.status, record.error
    session.add(record)
    session.commit()
    return result


def _store_statement(
    session: Session, record: StatementFile, statement: bankparse.ParsedStatement, result: ImportResult
) -> None:
    accounts: dict[str, Account] = {}
    for acc in statement.accounts:
        account = session.exec(
            select(Account).where(Account.bank_code == statement.bank_code, Account.account_number == acc.account_id)
        ).first()
        if account is None:
            account = Account(
                bank_code=statement.bank_code,
                bank=statement.bank,
                account_number=acc.account_id,
                label=acc.label,
                owner=statement.owner,
            )
            session.add(account)
            session.flush()
        accounts[acc.account_id] = account
    result.accounts = [a.custom_label or a.label for a in accounts.values()]

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
            session.add(tx)
            session.flush()
            tx_id = existing[fp] = tx.id
            result.inserted += 1
        else:
            result.duplicates += 1
        if session.get(TransactionSource, (tx_id, record.id)) is None:
            session.add(TransactionSource(transaction_id=tx_id, file_id=record.id))

    # Balances (one per account and date)
    for b in statement.balances:
        account = accounts.get(b.account_id)
        if account is None:
            continue
        found = session.exec(select(Balance).where(Balance.account_id == account.id, Balance.date == b.date)).first()
        if found is None:
            session.add(Balance(account_id=account.id, date=b.date, amount_cents=to_cents(b.amount), file_id=record.id))


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
