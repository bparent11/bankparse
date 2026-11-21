"""Spaces: one per account holder, so several people can share the app without mixing their data.

A statement is routed to a space by the holder name read on it. Banks write it in different orders
("PARENT Benjamin" at Crédit Agricole, "Benjamin PARENT" at Crédit Mutuel), so the key ignores case,
accents and word order. Categories are shared; accounts, operations, files, rules, corrections and
categorization runs belong to a space.
"""

from __future__ import annotations

import re

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select
from unidecode import unidecode

from bankparse_api.models import (
    Account,
    Balance,
    CategorizationJob,
    Correction,
    MerchantRule,
    Space,
    StatementFile,
    Transaction,
    TransactionSource,
)

UNKNOWN_KEY = "__unknown__"
UNKNOWN_NAME = "Titulaire inconnu"


def owner_key(owner: str | None) -> str | None:
    """'Parent Benjamin' and 'Benjamin PARENT' give the same key: 'benjamin parent'."""
    words = re.findall(r"[a-z]+", unidecode(owner or "").lower())
    return " ".join(sorted(words)) or None


def get_or_create_space(session: Session, owner: str | None) -> tuple[Space, bool]:
    """The space of this holder (the "unknown holder" space when the name could not be read)."""
    key = owner_key(owner) or UNKNOWN_KEY
    space = session.exec(select(Space).where(Space.owner_key == key)).first()
    if space is not None:
        return space, False
    space = Space(owner_key=key, name=owner.strip() if key != UNKNOWN_KEY and owner else UNKNOWN_NAME)
    session.add(space)
    session.flush()
    return space, True


def move_account(session: Session, account: Account, space_id: int) -> None:
    """Put an account in another space. Its statement files follow it (no commit)."""
    account.space_id = space_id
    session.add(account)
    file_ids = select(Balance.file_id).where(Balance.account_id == account.id).union(
        select(TransactionSource.file_id)
        .join(Transaction, col(Transaction.id) == col(TransactionSource.transaction_id))
        .where(Transaction.account_id == account.id)
    )
    for record in session.exec(select(StatementFile).where(col(StatementFile.id).in_(file_ids))).all():
        record.space_id = space_id
        session.add(record)


class SpaceError(ValueError):
    """Invalid user (space) operation, with a message for the user."""


def create_space(session: Session, name: str) -> Space:
    """A user added by hand, before importing their statements (no commit)."""
    name = " ".join((name or "").split())
    key = owner_key(name)
    if key is None or len(name) > 60:
        raise SpaceError("Le nom doit contenir des lettres (60 caractères au plus).")
    existing = session.exec(select(Space).where(Space.owner_key == key)).first()
    if existing is not None:
        raise SpaceError(f"L'utilisateur « {existing.name} » existe déjà.")
    space = Space(owner_key=key, name=name, manual=True)
    session.add(space)
    session.flush()
    return space


def learn_holder(session: Session, space: Space, owner: str | None) -> None:
    """A statement was imported by hand into an empty space: the holder read on it now leads to this space, so
    later statements of the same person are recognized automatically (e.g. a user created as "Marie" whose
    statements say "Marie DUPONT"). Only for a space without accounts, and when no other space has that holder."""
    key = owner_key(owner)
    if key is None or key == space.owner_key:
        return
    if session.exec(select(Account.id).where(Account.space_id == space.id)).first() is not None:
        return
    if session.exec(select(Space.id).where(Space.owner_key == key)).first() is not None:
        return
    space.owner_key = key
    session.add(space)


def space_of_transaction(session: Session, transaction_id: int | None) -> int | None:
    if transaction_id is None:
        return None
    return session.exec(
        select(Account.space_id).join(Transaction, col(Transaction.account_id) == col(Account.id))
        .where(Transaction.id == transaction_id)
    ).first()


# ---------------------------------------------------------------- upgrade of databases created before spaces
def migrate(engine: Engine) -> None:
    """Idempotent: give every existing row a space, and make merchant rules unique per space."""
    with engine.begin() as conn:
        indexes = {row[1]: row[2] for row in conn.exec_driver_sql('PRAGMA index_list("merchantrule")')}
        if indexes.get("ix_merchantrule_merchant_key") == 1:  # was unique across the whole database
            conn.exec_driver_sql("DROP INDEX ix_merchantrule_merchant_key")
            conn.exec_driver_sql("CREATE INDEX ix_merchantrule_merchant_key ON merchantrule (merchant_key)")
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_merchantrule_space_key ON merchantrule (space_id, merchant_key)"
            )

    with Session(engine) as session:
        for account in session.exec(select(Account).where(col(Account.space_id).is_(None))).all():
            account.space_id = get_or_create_space(session, account.owner)[0].id
            session.add(account)
        session.flush()

        first = session.exec(select(Space.id).order_by(Space.id)).first()
        for record in session.exec(select(StatementFile).where(col(StatementFile.space_id).is_(None))).all():
            # A file always belongs to one user: files that brought no account (unreadable, empty) and were
            # imported before users existed go to the first one.
            record.space_id = file_space(session, record.id) or record.chosen_space_id or first
            if record.space_id is not None:
                session.add(record)

        if first is not None:
            for c in session.exec(select(Correction).where(col(Correction.space_id).is_(None))).all():
                c.space_id = space_of_transaction(session, c.transaction_id) or first
                session.add(c)
            for model in (MerchantRule, CategorizationJob):
                for row in session.exec(select(model).where(col(model.space_id).is_(None))).all():
                    row.space_id = first
                    session.add(row)
        session.commit()


def file_space(session: Session, file_id: int | None) -> int | None:
    """Space of the accounts a statement file brought (through its operations, else its balances)."""
    if file_id is None:
        return None
    via_tx = session.exec(
        select(Account.space_id)
        .join(Transaction, col(Transaction.account_id) == col(Account.id))
        .join(TransactionSource, col(TransactionSource.transaction_id) == col(Transaction.id))
        .where(TransactionSource.file_id == file_id)
    ).first()
    if via_tx is not None:
        return via_tx
    return session.exec(
        select(Account.space_id).join(Balance, col(Balance.account_id) == col(Account.id))
        .where(Balance.file_id == file_id)
    ).first()
