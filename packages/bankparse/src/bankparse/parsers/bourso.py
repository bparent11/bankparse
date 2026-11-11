"""Boursorama / BoursoBank account statements ("Extrait de votre compte en EUR").

The statement has no ruled table, so operations are rebuilt from word positions:
operation date (x < 90), label (90 <= x < 370), value date (370 <= x < 430), amount (x >= 430);
an amount whose right edge is left of the "Crédit" column is a debit.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bankparse.detect import BANK_NAMES, BOURSO
from bankparse.errors import ParseError
from bankparse.models import Account, ParsedStatement, Transaction
from bankparse.parsers._common import Document, balance_check, find_owner, snapshots
from bankparse.utils import clean_label, parse_ddmmyyyy, parse_fr_amount

_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_PERIOD = re.compile(r"du\s*(\d{2}/\d{2}/\d{4})\s*au\s*(\d{2}/\d{2}/\d{4})")
_RIB = re.compile(r"\b\d{5}\s+\d{5}\s+(\d{11})\s+\d{2}\b")

LABEL_X, VALUE_X, AMOUNT_X = 90, 370, 430
CREDIT_RIGHT_EDGE = 495  # amounts ending left of this are in the "Débit" column
FOOTER_TOP = 735
LINE_TOLERANCE = 2.5


# Some Boursorama fonts map accented letters to wrong glyphs ("dØlai", "ClientŁle", "RŁf").
_GLYPH_FIX = str.maketrans({"Ø": "é", "Ł": "è"})


def _fix_glyphs(text: str) -> str:
    return text.translate(_GLYPH_FIX).replace("Rèf", "Réf")


def _group_lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _signed(word: dict) -> Decimal | None:
    amount = parse_fr_amount(word["text"])
    if amount is None:
        return None
    return -amount if word["x1"] < CREDIT_RIGHT_EDGE else amount


def parse_bourso(doc: Document) -> ParsedStatement:
    text = doc.first_page_text
    period = _PERIOD.search(text)
    if not period:
        raise ParseError("Boursorama: statement period ('du ... au ...') not found.")
    statement_date = parse_ddmmyyyy(period.group(2))

    rib = _RIB.search(text)
    if not rib:
        raise ParseError("Boursorama: account number not found.")
    account = Account(account_id=rib.group(1), label="Compte bancaire")

    ops: list[dict] = []
    opening: tuple[date, Decimal] | None = None
    closing: tuple[date, Decimal] | None = None
    finished = False

    for page in doc.pages:
        if finished:
            break
        lines = _group_lines(page.words)
        start = next(
            (i for i, ln in enumerate(lines) if any(w["text"] == "MOUVEMENTS" for w in ln)),
            None,
        )
        if start is None:
            continue

        for line in lines[start + 1 :]:
            top = line[0]["top"]
            if top >= FOOTER_TOP:
                break
            texts = [w["text"] for w in line]

            if "Nouveau" in texts:
                nearby = [
                    w for w in page.words if abs(w["top"] - top) <= 4 and w["x0"] >= AMOUNT_X
                ]
                amounts = [a for w in nearby if (a := _signed(w)) is not None]
                if amounts:
                    closing = (statement_date, amounts[0])
                finished = True
                break

            if "SOLDE" in texts and opening is None:
                d = next((w["text"] for w in line if _DATE.match(w["text"])), None)
                amount = next((a for w in line if w["x0"] >= AMOUNT_X and (a := _signed(w)) is not None), None)
                if d and amount is not None:
                    opening = (parse_ddmmyyyy(d), amount)
                continue

            first = line[0]
            if first["x0"] < LABEL_X and _DATE.match(first["text"]):
                label = " ".join(w["text"] for w in line if LABEL_X <= w["x0"] < VALUE_X)
                value = next(
                    (w["text"] for w in line if VALUE_X <= w["x0"] < AMOUNT_X and _DATE.match(w["text"])), None
                )
                amount = next((a for w in line if w["x0"] >= AMOUNT_X and (a := _signed(w)) is not None), None)
                if amount is None:
                    continue
                ops.append(
                    {
                        "account_id": account.account_id,
                        "operation_date": parse_ddmmyyyy(first["text"]),
                        "value_date": parse_ddmmyyyy(value) if value else None,
                        "label": clean_label(_fix_glyphs(label)),
                        "amount": amount,
                    }
                )
            elif ops and all(LABEL_X <= w["x0"] < VALUE_X for w in line):
                ops[-1]["label"] = clean_label(ops[-1]["label"] + " " + _fix_glyphs(" ".join(texts)))

    transactions = [Transaction(**op) for op in ops]
    return ParsedStatement(
        bank=BANK_NAMES[BOURSO],
        bank_code=BOURSO,
        owner=find_owner(text),
        statement_date=statement_date,
        accounts=[account],
        transactions=transactions,
        balances=snapshots(account.account_id, opening or (None, None), closing or (None, None)),
        checks=[
            balance_check(
                account.account_id, opening[1] if opening else None, closing[1] if closing else None, transactions
            )
        ],
    )
