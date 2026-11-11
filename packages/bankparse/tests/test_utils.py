from datetime import date
from decimal import Decimal

import pytest
from bankparse.models import BalanceCheck
from bankparse.utils import find_french_long_date, infer_year, month_from_name, parse_fr_amount


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1 234,56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("+10.979,67", Decimal("10979.67")),
        ("-27.900,00", Decimal("-27900.00")),
        ("1 000,00 €", Decimal("1000.00")),
        ("3,50", Decimal("3.50")),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_parse_fr_amount(text, expected):
    assert parse_fr_amount(text) == expected


def test_month_from_name_is_accent_and_case_insensitive():
    assert month_from_name("Décembre") == "12"
    assert month_from_name("aout") == "08"
    with pytest.raises(KeyError):
        month_from_name("Lidl")


def test_find_french_long_date_skips_words_that_are_not_months():
    # Regression: old code took "4 Lidl 2025" for a date and crashed.
    assert find_french_long_date("Carte 4 Lidl 2025 puis le 06 Novembre 2025") == date(2025, 11, 6)
    assert find_french_long_date("1er mars 2024") == date(2024, 3, 1)
    assert find_french_long_date("rien ici") is None


@pytest.mark.parametrize(
    "day, month, reference, expected",
    [
        (31, 12, date(2025, 1, 6), date(2024, 12, 31)),  # December operation on a January statement
        (22, 10, date(2025, 11, 6), date(2025, 10, 22)),
        (6, 11, date(2025, 11, 6), date(2025, 11, 6)),
    ],
)
def test_infer_year(day, month, reference, expected):
    assert infer_year(day, month, reference) == expected


def test_balance_check():
    ok = BalanceCheck("1", Decimal(100), Decimal("80.5"), Decimal("-19.5"))
    ko = BalanceCheck("1", Decimal(100), Decimal(80), Decimal("-19.5"))
    unknown = BalanceCheck("1", None, Decimal(80), Decimal(-20))
    assert ok.ok is True
    assert ko.ok is False
    assert unknown.ok is None
