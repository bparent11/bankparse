"""LCL (Crédit Lyonnais) statements: current account ("RELEVE DE COMPTE") and savings accounts
("LIVRET A", "RELEVE LIVRET JEUNE", "RELEVE DE COMPTE SUR LIVRET", "RELEVE DE PLAN EPARGNE LOGEMENT").

All of them share the "ECRITURES DE LA PERIODE" layout, one account per statement. There is no ruled
table, so operations are rebuilt from word positions, using the column headers of each page:
operation date (``dd.mm``, x < LABEL_X), label (LABEL_X <= x < VALUE_X), value date (``dd.mm.yy``),
then the amount, in the "DEBIT" or "CREDIT" column depending on its right edge.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bankparse.detect import BANK_NAMES, LCL
from bankparse.errors import ParseError
from bankparse.models import Account, ParsedStatement, Transaction
from bankparse.parsers._common import Document, Page, balance_check, snapshots
from bankparse.utils import clean_label, parse_fr_amount

_PERIOD = re.compile(r"du\s*(\d{2})\.(\d{2})\.(\d{4})\s*au\s*(\d{2})\.(\d{2})\.(\d{4})")
_DDMM = re.compile(r"^(\d{2})\.(\d{2})$")
_DDMMYY = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})$")
_AMOUNT = re.compile(r"^\d{1,3}(?: \d{3})*,\d{2}$")
_PAGE_FOOTER = re.compile(r"^Page\s+\d+\s*/\s*\d+$")
# "Indicatif :1234 Compte : 123456 L" (pages 2+), "01234 654321 R" (savings, below "Indicatif N° de compte"),
# "30002 01234 0000123456L 17" (RIB of the current account).
_ACCOUNT_INLINE = re.compile(r"Indicatif\s*:\s*(\d{1,5})\s+Compte\s*:\s*(\d{1,6})\b")
_ACCOUNT_SAVINGS = re.compile(r"^(\d{5})\s+(\d{6})\s*[A-Z]$")
_ACCOUNT_RIB = re.compile(r"\b30002\s+(\d{5})\s+0*(\d{1,6})[A-Z]\s+\d{2}\b")
_CIVILITY = re.compile(r"^(?:MLLE|MME|MR|M|MONSIEUR|MADAME|MADEMOISELLE)\.?\s+(.+)$", re.IGNORECASE)

LABEL_X = 70  # the operation date ends at x ~ 65, the label starts at x ~ 75
LINE_TOLERANCE = 2.5
# Fallback column positions (x1 of the "DEBIT" header, x1 of the "CREDIT" header, x0 of "VALEUR").
DEFAULT_DEBIT_X1, DEFAULT_CREDIT_X1, DEFAULT_VALUE_X = 460, 538, 360

_LABELS = {
    "RELEVE DE COMPTE": "Compte de dépôts",
    "RELEVE DE COMPTE SUR LIVRET": "Compte sur livret",
    "RELEVE DE PLAN EPARGNE LOGEMENT": "Plan épargne logement",
    "LIVRET A": "Livret A",
    "RELEVE LIVRET JEUNE": "Livret jeune",
}


def _group_lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _text(word: dict) -> str:
    return word["text"].strip()


def _nearest(day: int, month: int, reference: date) -> date:
    """The ``day.month`` date closest to ``reference`` (the statement prints no year)."""
    candidates = []
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:  # 29.02 of a non-leap year
            continue
    return min(candidates, key=lambda d: abs(d - reference))


def _ddmm(text: str, reference: date) -> date | None:
    m = _DDMM.match(text)
    return _nearest(int(m.group(1)), int(m.group(2)), reference) if m else None


def _ddmmyy(text: str) -> date | None:
    m = _DDMMYY.match(text)
    if not m:
        return None
    return date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))


def _signed(word: dict, amount_x: float, split_x: float) -> Decimal | None:
    """The signed amount of a word of the DEBIT / CREDIT columns (debit if it ends left of ``split_x``)."""
    text = _text(word)
    if word["x0"] < amount_x or not _AMOUNT.match(text):
        return None
    amount = parse_fr_amount(text)
    return -amount if word["x1"] < split_x else amount


def _account(doc: Document) -> Account:
    title = clean_label(doc.first_page_text.splitlines()[0] if doc.first_page_text else "").upper()
    label = _LABELS.get(title, title.removeprefix("RELEVE DE ").removeprefix("RELEVE ").capitalize())
    for page in doc.pages:
        for line in page.lines:
            text = clean_label(line.text)
            m = _ACCOUNT_INLINE.search(text) or _ACCOUNT_SAVINGS.match(text) or _ACCOUNT_RIB.search(text)
            if m:
                return Account(account_id=m.group(1).zfill(5) + m.group(2).zfill(6), label=label or "Compte")
    raise ParseError("LCL: account number not found.")


def _owner(doc: Document) -> str | None:
    """The holder is printed on the line below "Titulaire du compte" (left column; the address may follow)."""
    lines = _group_lines(doc.pages[0].words)
    for i, line in enumerate(lines[:-1]):
        if any("Titulaire du compte" in w["text"] for w in line):
            header_x1 = max(w["x1"] for w in line if "Titulaire" in w["text"])
            words = [_text(w) for w in lines[i + 1] if w["x0"] < header_x1]
            m = _CIVILITY.match(" ".join(words))
            if not m:
                return None
            name = re.split(r"\s+OU\s+|\s+\d", m.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
            return " ".join(part.capitalize() for part in name.split()) or None
    return None


def _columns(page: Page) -> tuple[int, float, float, float] | None:
    """Index of the column header line, and the value-date x0 / debit x1 / credit x1 of this page."""
    lines = _group_lines(page.words)
    for i, line in enumerate(lines):
        texts = {_text(w): w for w in line}
        if "DATE" in texts and "LIBELLE" in texts:
            value_x = texts["VALEUR"]["x0"] if "VALEUR" in texts else DEFAULT_VALUE_X
            debit_x1 = texts["DEBIT"]["x1"] if "DEBIT" in texts else DEFAULT_DEBIT_X1
            credit_x1 = texts["CREDIT"]["x1"] if "CREDIT" in texts else DEFAULT_CREDIT_X1
            return i, value_x, debit_x1, credit_x1
    return None


def parse_lcl(doc: Document) -> ParsedStatement:
    period = _PERIOD.search(doc.first_page_text)
    if not period:
        raise ParseError("LCL: statement period ('du ... au ...') not found.")
    d1, m1, y1, d2, m2, y2 = (int(g) for g in period.groups())
    start, statement_date = date(y1, m1, d1), date(y2, m2, d2)
    account = _account(doc)

    ops: list[dict] = []
    opening: tuple[date, Decimal] | None = None
    closing: tuple[date, Decimal] | None = None
    warnings: list[str] = []
    finished = False

    for page in doc.pages:
        if finished:
            break
        columns = _columns(page)
        if columns is None:
            continue
        header, value_x, debit_x1, credit_x1 = columns
        split_x = (debit_x1 + credit_x1) / 2  # amounts ending left of this are debits
        amount_x = value_x + 45  # the value date ends at x ~ 401, the debit column starts at x ~ 410

        for line in _group_lines(page.words)[header + 1 :]:
            texts = [_text(w) for w in line]
            joined = " ".join(texts)
            if any(_PAGE_FOOTER.match(t) for t in texts):
                break
            first = line[0]
            amounts = [a for w in line if (a := _signed(w, amount_x, split_x)) is not None]
            labels = [_text(w) for w in line if LABEL_X <= w["x0"] < value_x and _text(w)]
            op_day = _text(first) if first["x0"] < LABEL_X and _DDMM.match(_text(first)) else None

            if "SOLDE EN EUROS" in joined:
                if amounts:
                    closing = (_ddmm(op_day, statement_date) if op_day else statement_date, amounts[0])
                finished = True
                break
            if "ANCIEN SOLDE" in joined and opening is None and not ops:
                if amounts:
                    opening = (_ddmm(op_day, start) if op_day else start, amounts[0])
                continue

            if op_day is not None:
                if not amounts:
                    warnings.append(f"Operation without amount ignored: {op_day} {' '.join(labels)!r}")
                    continue
                value = next(
                    (d for w in line if value_x - 5 <= w["x0"] < amount_x and (d := _ddmmyy(_text(w)))), None
                )
                # The operation date has no year: take the one closest to the value date (dd.mm.yy).
                op_date = _ddmm(op_day, value or statement_date)
                if op_date > statement_date and value is None:
                    op_date = op_date.replace(year=op_date.year - 1)
                ops.append(
                    {
                        "account_id": account.account_id,
                        "operation_date": op_date,
                        "value_date": value,
                        "label": clean_label(" ".join(labels)),
                        "amount": amounts[0],
                    }
                )
            elif not amounts and labels and ops and first["x0"] >= LABEL_X:
                # A line with only a label continues the previous operation ("LIBELLE:", "REF.CLIENT:"...).
                ops[-1]["label"] = clean_label(ops[-1]["label"] + " " + " ".join(labels))
            # Other lines ("TOTAUX", "SOLDE INTERMEDIAIRE A FIN MAI", "PAS DE MOUVEMENT"...) are skipped.

    transactions = [Transaction(**op) for op in ops]
    return ParsedStatement(
        bank=BANK_NAMES[LCL],
        bank_code=LCL,
        owner=_owner(doc),
        statement_date=statement_date,
        accounts=[account],
        transactions=transactions,
        balances=snapshots(account.account_id, opening or (None, None), closing or (None, None)),
        checks=[
            balance_check(
                account.account_id, opening[1] if opening else None, closing[1] if closing else None, transactions
            )
        ],
        warnings=warnings,
    )
