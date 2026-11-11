"""Regression tests on real statements.

Real statements contain personal data, so they are never committed. Tests run on:
- tests/fixtures/*.pdf (gitignored), and
- every PDF under the folders listed in the BANKPARSE_STATEMENTS env var (os.pathsep separated).
Tests are skipped when no statement is available.
"""

import os
from pathlib import Path

import bankparse
import pytest
from bankparse.file_manager import FileFactory

FIXTURES = Path(__file__).parent / "fixtures"


def _statements() -> list[Path]:
    folders = [FIXTURES] + [Path(p) for p in os.environ.get("BANKPARSE_STATEMENTS", "").split(os.pathsep) if p]
    files = {p.resolve() for folder in folders if folder.exists() for p in folder.rglob("*.pdf")}
    return sorted(files)


STATEMENTS = _statements()
pytestmark = pytest.mark.skipif(not STATEMENTS, reason="no private statement PDF available")


def _is_brokerage(path: Path) -> bool:
    return path.name.startswith(("Relevés-", "Relevé-"))  # Bourso 'espèces' / 'titres': not supported yet


@pytest.mark.parametrize("path", STATEMENTS, ids=lambda p: p.name)
def test_statement_parses_and_balances(path: Path):
    if _is_brokerage(path):
        with pytest.raises(bankparse.UnsupportedStatementError):
            bankparse.parse(path)
        return

    statement = bankparse.parse(path)

    assert statement.accounts, "at least one account"
    assert statement.checks, "at least one balance check"
    failing = [c for c in statement.checks if c.ok is False]
    assert not failing, f"opening + operations != closing: {failing}"
    for t in statement.transactions:
        assert t.label
        assert t.amount != 0
        assert t.operation_date <= statement.statement_date


@pytest.mark.parametrize("path", STATEMENTS, ids=lambda p: p.name)
def test_parse_from_bytes_equals_parse_from_path(path: Path):
    if _is_brokerage(path):
        pytest.skip("unsupported document")
    assert bankparse.parse(path.read_bytes()).to_dict() == bankparse.parse(path).to_dict()


@pytest.mark.parametrize("path", STATEMENTS, ids=lambda p: p.name)
def test_legacy_api_still_works(path: Path):
    extraction_file = FileFactory.handle_file(str(path))
    if _is_brokerage(path):
        assert extraction_file is None
        return
    for table in extraction_file.transaction_tables:
        table.get_dataframe()
