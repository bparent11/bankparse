"""Normalized, bank-agnostic output model of bankparse.

Every parser returns a :class:`ParsedStatement`. Amounts are :class:`~decimal.Decimal`
(signed: money going out of the account is negative) and dates are :class:`~datetime.date`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Account:
    account_id: str
    label: str


@dataclass(frozen=True)
class Transaction:
    account_id: str
    operation_date: date
    value_date: date | None
    label: str
    amount: Decimal  # negative = debit, positive = credit


@dataclass(frozen=True)
class BalanceSnapshot:
    account_id: str
    date: date
    amount: Decimal


@dataclass(frozen=True)
class BalanceCheck:
    """Result of ``opening + sum(transactions) == closing`` for one account."""

    account_id: str
    opening: Decimal | None
    closing: Decimal | None
    total: Decimal

    @property
    def ok(self) -> bool | None:
        """True/False when both balances are known, None when the check is not possible."""
        if self.opening is None or self.closing is None:
            return None
        return self.opening + self.total == self.closing


@dataclass
class ParsedStatement:
    bank: str  # "Crédit Agricole" | "Crédit Mutuel" | "Boursorama"
    bank_code: str  # "CA" | "CM" | "BOURSO"
    owner: str | None
    statement_date: date
    accounts: list[Account] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    balances: list[BalanceSnapshot] = field(default_factory=list)
    checks: list[BalanceCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool | None:
        """False if any account fails its balance check, None if nothing could be checked."""
        results = [c.ok for c in self.checks if c.ok is not None]
        if not results:
            return None
        return all(results)

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            return value

        data = convert(asdict(self))
        data["checks"] = [{**convert(asdict(c)), "ok": c.ok} for c in self.checks]
        data["is_consistent"] = self.is_consistent
        return data

    def to_dataframe(self):
        """Transactions as a pandas DataFrame (one row per operation)."""
        import pandas as pd

        labels = {a.account_id: a.label for a in self.accounts}
        rows = [
            {
                "bank": self.bank,
                "account_id": t.account_id,
                "account_label": labels.get(t.account_id, ""),
                "operation_date": t.operation_date,
                "value_date": t.value_date,
                "label": t.label,
                "amount": t.amount,
            }
            for t in self.transactions
        ]
        return pd.DataFrame(
            rows,
            columns=["bank", "account_id", "account_label", "operation_date", "value_date", "label", "amount"],
        )
