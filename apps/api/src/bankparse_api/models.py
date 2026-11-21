"""Database schema. Amounts are stored as integer cents to avoid float rounding errors."""

import datetime as dt

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Space(SQLModel, table=True):
    """One person's space: accounts are routed to it by the account holder read on the statements."""

    id: int | None = Field(default=None, primary_key=True)
    owner_key: str = Field(unique=True, index=True)  # normalized holder name, see spaces.owner_key
    name: str  # display name, editable
    manual: bool | None = None  # added by hand ("Nouvel utilisateur"): listed even before it has accounts
    created_at: dt.datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("bank_code", "account_number"),)

    id: int | None = Field(default=None, primary_key=True)
    bank_code: str = Field(index=True)  # CA | CM | BOURSO
    bank: str
    account_number: str
    label: str  # label read on the statement
    custom_label: str | None = None  # label chosen by the user in the app
    owner: str | None = None
    space_id: int | None = Field(default=None, foreign_key="space.id", index=True)


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
    space_id: int | None = Field(default=None, index=True)  # the user it belongs to (always set by the app)
    chosen_space_id: int | None = None  # user chosen at import (wins over the holder read on the statement)


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
    category_source: str | None = None  # "user" | "rule" | "llm"
    category_model: str | None = None  # LLM that chose the category (nullable: added to existing databases)
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


class Category(SQLModel, table=True):
    """Categories the user can edit. ``is_system`` ones (Inconnu) cannot be renamed or deleted."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    position: int = 0
    is_system: bool = False
    description: str | None = None  # what the category means for the user, given to the LLM


class MerchantRule(SQLModel, table=True):
    """Category remembered for a merchant (see categorize/merchant.py), by the user, in one space."""

    __table_args__ = (UniqueConstraint("space_id", "merchant_key"),)

    id: int | None = Field(default=None, primary_key=True)
    space_id: int | None = Field(default=None, index=True)
    merchant_key: str = Field(index=True)
    category: str = Field(index=True)
    source: str  # "user" | "llm"
    example_label: str
    updated_at: dt.datetime = Field(default_factory=utcnow)


class CategorizationJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    status: str = "running"  # running | done | failed | cancelled
    include_unknown: bool = False
    mode: str | None = None  # new (never categorized) | all (everything except the user's own choices)
    model: str | None = None  # Ollama model used for this run
    batch_size: int | None = None  # 1 = precise (one per request), >1 = fast (several per request)
    date_from: dt.date | None = None  # optional period
    date_to: dt.date | None = None
    total: int = 0  # operations to categorize
    done: int = 0  # operations categorized so far
    merchants_total: int = 0  # operations sent to the LLM (historical column name)
    merchants_done: int = 0
    message: str | None = None
    cancel_requested: bool = False
    space_id: int | None = Field(default=None, index=True)
    started_at: dt.datetime = Field(default_factory=utcnow)
    finished_at: dt.datetime | None = None


class Correction(SQLModel, table=True):
    """A manual category choice, with the user's explanation. Used as guidance in the LLM prompt."""

    id: int | None = Field(default=None, primary_key=True)
    transaction_id: int | None = Field(default=None, index=True)  # no FK: kept if the operation is deleted
    space_id: int | None = Field(default=None, index=True)
    label: str
    amount_cents: int
    category: str = Field(index=True)
    reason: str | None = None
    applied_to_similar: bool = False
    created_at: dt.datetime = Field(default_factory=utcnow)
