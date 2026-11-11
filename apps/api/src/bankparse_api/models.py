"""Database schema. Amounts are stored as integer cents to avoid float rounding errors."""

import datetime as dt

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Account(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("bank_code", "account_number"),)

    id: int | None = Field(default=None, primary_key=True)
    bank_code: str = Field(index=True)  # CA | CM | BOURSO
    bank: str
    account_number: str
    label: str  # label read on the statement
    custom_label: str | None = None  # label chosen by the user in the app
    owner: str | None = None


class StatementFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sha256: str = Field(unique=True, index=True)
    filename: str
    stored_path: str
    size: int
    uploaded_at: dt.datetime = Field(default_factory=utcnow)
    status: str = "parsed"  # parsed | failed | unsupported
    error: str | None = None
    bank_code: str | None = None
    statement_date: dt.date | None = None
    check_ok: bool | None = None  # opening + operations == closing for every account
    parser_version: str | None = None


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    operation_date: dt.date = Field(index=True)
    value_date: dt.date | None = None
    label: str
    amount_cents: int
    fingerprint: str = Field(unique=True, index=True)
    # Reserved for the upcoming (local LLM / rules based) categorization.
    category: str | None = Field(default=None, index=True)
    category_source: str | None = None  # "rule" | "llm" | "user"
    created_at: dt.datetime = Field(default_factory=utcnow)


class TransactionSource(SQLModel, table=True):
    """Which statement files contain a transaction (overlapping statements share operations)."""

    transaction_id: int = Field(foreign_key="transaction.id", primary_key=True)
    file_id: int = Field(foreign_key="statementfile.id", primary_key=True, index=True)


class Balance(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("account_id", "date"),)

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    date: dt.date
    amount_cents: int
    file_id: int | None = Field(default=None, foreign_key="statementfile.id", index=True)
