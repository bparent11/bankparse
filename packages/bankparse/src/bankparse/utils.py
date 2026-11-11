import re
from datetime import date
from decimal import Decimal, InvalidOperation

from unidecode import unidecode

MONTHS = {
    "janvier": "01",
    "fevrier": "02",
    "mars": "03",
    "avril": "04",
    "mai": "05",
    "juin": "06",
    "juillet": "07",
    "aout": "08",
    "septembre": "09",
    "octobre": "10",
    "novembre": "11",
    "decembre": "12",
}

# "06 Novembre 2025", "31 décembre 2014", "1er mars 2024"
_LONG_DATE = re.compile(r"\b(\d{1,2})(?:er)?\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})\b")


def matches(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text))


def month_from_name(month: str) -> str:
    """
    Transform french months to their associated number.

    Args:
        month: month name (case and accent insensitive)

    Returns:
        month number as a 2-chars string

    Raises:
        KeyError if the month name is unknown.
    """
    key = unidecode(month).lower()
    if key not in MONTHS:
        raise KeyError(f"Unknown month name: {month}")
    return MONTHS[key]


def find_french_long_date(text: str) -> date | None:
    """Return the first ``<day> <french month> <year>`` date found in text, ignoring non-month words."""
    for day, month, year in _LONG_DATE.findall(text):
        key = unidecode(month).lower()
        if key in MONTHS:
            try:
                return date(int(year), int(MONTHS[key]), int(day))
            except ValueError:
                continue
    return None


def parse_fr_amount(text: str | None) -> Decimal | None:
    """
    Parse a French formatted amount.

    Handles "1 234,56", "1.234,56", "+10.979,67", "-27.900,00", "1 234,56 €", non-breaking spaces.
    Returns None for empty cells.
    """
    if text is None:
        return None
    cleaned = re.sub(r"[\s  €]", "", str(text))
    if cleaned == "":
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_ddmmyyyy(text: str, sep: str = "/") -> date:
    dd, mm, yyyy = text.strip().split(sep)
    return date(int(yyyy), int(mm), int(dd))


def infer_year(day: int, month: int, reference: date) -> date:
    """
    Build a date from a day/month without year (e.g. Crédit Agricole "31.12"), using the
    statement date as reference: a month after the statement month belongs to the previous year.
    """
    year = reference.year - 1 if month > reference.month else reference.year
    return date(year, month, day)


def clean_label(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()
