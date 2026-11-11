import datetime as dt
from typing import Literal

from pydantic import BaseModel


class ImportResultOut(BaseModel):
    filename: str
    status: Literal["imported", "already_imported", "failed", "unsupported", "rejected"]
    file_id: int | None = None
    bank: str | None = None
    statement_date: dt.date | None = None
    accounts: list[str] = []
    inserted: int = 0
    duplicates: int = 0
    check_ok: bool | None = None
    error: str | None = None
    warnings: list[str] = []


class AccountOut(BaseModel):
    id: int
    bank_code: str
    bank: str
    account_number: str
    label: str
    statement_label: str
    owner: str | None
    transaction_count: int
    first_operation: dt.date | None
    last_operation: dt.date | None
    last_balance: float | None
    last_balance_date: dt.date | None


class AccountUpdate(BaseModel):
    label: str | None = None  # None or "" resets to the label read on the statements


class BalanceOut(BaseModel):
    date: dt.date
    amount: float


class TransactionOut(BaseModel):
    id: int
    account_id: int
    account_label: str
    bank_code: str
    operation_date: dt.date
    value_date: dt.date | None
    label: str
    amount: float
    category: str | None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
    total_credit: float
    total_debit: float


class FileOut(BaseModel):
    id: int
    filename: str
    uploaded_at: dt.datetime
    size: int
    status: str
    error: str | None
    bank_code: str | None
    statement_date: dt.date | None
    check_ok: bool | None
    transaction_count: int


class MonthTotal(BaseModel):
    month: str  # YYYY-MM
    credit: float
    debit: float


class Summary(BaseModel):
    accounts: int
    transactions: int
    files: int  # statements read (status "parsed")
    files_total: int  # every uploaded file, including unsupported or failed ones
    first_operation: dt.date | None
    last_operation: dt.date | None
    months: list[MonthTotal]
