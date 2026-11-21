"""Transaction filters shared by the list and export endpoints."""

import datetime as dt
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Query
from sqlalchemy import func
from sqlmodel import col, select

from bankparse_api.models import Account, Transaction

SortField = Literal["operation_date", "value_date", "amount", "label", "account"]


SpaceId = Annotated[int | None, Query(description="Space (one per account holder); omitted: every space")]


@dataclass
class TransactionFilters:
    space_id: int | None = None
    account_id: list[int] | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    q: str | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    direction: Literal["debit", "credit"] | None = None
    category: str | None = None
    uncategorized: bool = False
    to_review: bool = False  # proposed by the LLM and not yet validated


def transaction_filters(
    space_id: SpaceId = None,
    account_id: Annotated[list[int] | None, Query()] = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    direction: Literal["debit", "credit"] | None = None,
    category: str | None = None,
    uncategorized: bool = False,
    to_review: bool = False,
) -> TransactionFilters:
    return TransactionFilters(
        space_id,
        account_id, date_from, date_to, q, min_amount, max_amount, direction, category, uncategorized, to_review
    )


def filtered_query(f: TransactionFilters):
    """SELECT Transaction, Account with every filter applied (no ordering, no paging)."""
    stmt = select(Transaction, Account).join(Account, col(Transaction.account_id) == col(Account.id))
    if f.space_id is not None:
        stmt = stmt.where(Account.space_id == f.space_id)
    if f.account_id:
        stmt = stmt.where(col(Transaction.account_id).in_(f.account_id))
    if f.date_from:
        stmt = stmt.where(Transaction.operation_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Transaction.operation_date <= f.date_to)
    if f.q:
        for word in f.q.split():
            stmt = stmt.where(func.lower(Transaction.label).contains(word.lower()))
    if f.min_amount is not None:
        stmt = stmt.where(Transaction.amount_cents >= round(f.min_amount * 100))
    if f.max_amount is not None:
        stmt = stmt.where(Transaction.amount_cents <= round(f.max_amount * 100))
    if f.direction == "debit":
        stmt = stmt.where(Transaction.amount_cents < 0)
    elif f.direction == "credit":
        stmt = stmt.where(Transaction.amount_cents > 0)
    if f.category:
        stmt = stmt.where(Transaction.category == f.category)
    if f.uncategorized:
        stmt = stmt.where(col(Transaction.category).is_(None))
    if f.to_review:
        stmt = stmt.where(col(Transaction.category_source).in_(("llm", "memory")))
    return stmt


def order_by(stmt, sort: SortField, order: Literal["asc", "desc"]):
    column = {
        "operation_date": Transaction.operation_date,
        "value_date": Transaction.value_date,
        "amount": Transaction.amount_cents,
        "label": Transaction.label,
        "account": Account.label,
    }[sort]
    primary = col(column).desc() if order == "desc" else col(column).asc()
    tiebreak = col(Transaction.id).desc() if order == "desc" else col(Transaction.id).asc()
    return stmt.order_by(primary, tiebreak)


def account_label(account: Account) -> str:
    return account.custom_label or account.label
