"""Shared fixtures: an isolated database per test and a fake statement parser."""

from datetime import date
from decimal import Decimal

import bankparse
import pytest
from bankparse.models import Account, BalanceSnapshot, ParsedStatement, Transaction
from bankparse_api import config, db, ingest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BANKPARSE_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    db.reset_engine()
    from bankparse_api.main import app

    with TestClient(app) as c:
        yield c
    db.reset_engine()
    config.get_settings.cache_clear()


def tx(day: date, label: str, amount: str) -> Transaction:
    return Transaction("12345678901", day, day, label, Decimal(amount))


COFFEE = tx(date(2025, 1, 10), "CARTE CAFE DU COIN", "-3.50")
RENT = tx(date(2025, 1, 12), "VIR SEPA LOYER", "-500.00")
SALARY = tx(date(2025, 2, 1), "VIR SALAIRE", "2000.00")

STATEMENTS = {
    # January statement: two identical coffees the same day are two real operations.
    b"%PDF-A": [COFFEE, COFFEE, RENT],
    # Overlapping statement: repeats one coffee and the rent, adds the salary.
    b"%PDF-B": [COFFEE, RENT, SALARY],
}


@pytest.fixture
def fake_parser(monkeypatch):
    def fake_parse(content: bytes) -> ParsedStatement:
        if content == b"%PDF-unsupported":
            raise bankparse.UnsupportedStatementError("not a statement")
        ops = STATEMENTS[content]
        return ParsedStatement(
            bank="Crédit Mutuel",
            bank_code="CM",
            owner="Jane Doe",
            statement_date=max(t.operation_date for t in ops),
            accounts=[Account("12345678901", "C/C EUROCOMPTE")],
            transactions=ops,
            balances=[BalanceSnapshot("12345678901", max(t.operation_date for t in ops), Decimal(1000))],
        )

    monkeypatch.setattr(ingest.bankparse, "parse", fake_parse)


