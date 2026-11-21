"""Transaction filters shared by the list and export endpoints."""

import datetime as dt
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Query
from sqlalchemy import func
from sqlmodel import col, select

from bankparse_api.models import Account, Transaction

SortField = Literal["operation_date", "value_date", "amount", "label", "account"]

NO_CATEGORY = "__none__"  # in ``category``: operations without a category
# ``source`` values: who chose the category. "none" = no category yet; "llm" also covers the older "memory".
Source = Literal["user", "rule", "llm", "validated", "none"]


SpaceId = Annotated[int | None, Query(description="Space (one per account holder); omitted: every space")]


@dataclass
class TransactionFilters:
    space_id: int | None = None
    account_id: list[int] | None = None
    bank_code: list[str] | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    q: str | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    direction: Literal["debit", "credit"] | None = None
    category: list[str] | None = None  # NO_CATEGORY for operations without a category
    uncategorized: bool = False
    to_review: bool = False  # proposed by the LLM and not yet validated
    source: list[str] | None = None


def transaction_filters(
    space_id: SpaceId = None,
    account_id: Annotated[list[int] | None, Query()] = None,
    bank_code: Annotated[list[str] | None, Query()] = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    direction: Literal["debit", "credit"] | None = None,
    category: Annotated[
        list[str] | None, Query(description=f"Category names; {NO_CATEGORY!r} for operations without one")
    ] = None,
    uncategorized: bool = False,
    to_review: bool = False,
    source: Annotated[list[Source] | None, Query(description="Who chose the category")] = None,
) -> TransactionFilters:
    """Every list filter keeps the operations matching ANY of its values (several accounts, every category but
    one…); the filters themselves combine with AND."""
    return TransactionFilters(
        space_id=space_id,
        account_id=account_id,
        bank_code=bank_code,
        date_from=date_from,
        date_to=date_to,
        q=q,
        min_amount=min_amount,
        max_amount=max_amount,
        direction=direction,
        category=category,
        uncategorized=uncategorized,
        to_review=to_review,
        source=list(source) if source else None,
    )


def filtered_query(f: TransactionFilters):
    """SELECT Transaction, Account with every filter applied (no ordering, no paging)."""
    stmt = select(Transaction, Account).join(Account, col(Transaction.account_id) == col(Account.id))
    if f.space_id is not None:
        stmt = stmt.where(Account.space_id == f.space_id)
    if f.account_id:
        stmt = stmt.where(col(Transaction.account_id).in_(f.account_id))
    if f.bank_code:
        stmt = stmt.where(col(Account.bank_code).in_(f.bank_code))
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
        names = [c for c in f.category if c != NO_CATEGORY]
        condition = col(Transaction.category).in_(names)
        if NO_CATEGORY in f.category:
            condition = condition | col(Transaction.category).is_(None)
        stmt = stmt.where(condition)
    if f.uncategorized:
        stmt = stmt.where(col(Transaction.category).is_(None))
    if f.to_review:
        stmt = stmt.where(col(Transaction.category_source).in_(("llm", "memory")))
    if f.source:
        sources = [s for s in f.source if s != "none"] + (["memory"] if "llm" in f.source else [])
        condition = col(Transaction.category_source).in_(sources)
        if "none" in f.source:
            condition = condition | col(Transaction.category).is_(None)
        stmt = stmt.where(condition)
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
