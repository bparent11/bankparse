"""Crédit Agricole account statements ("RELEVE DE COMPTES")."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bankparse.detect import BANK_NAMES, CA
from bankparse.errors import ParseError
from bankparse.models import Account, ParsedStatement, Transaction
from bankparse.parsers._common import Document, balance_check, cell, find_owner, snapshots
from bankparse.utils import clean_label, find_french_long_date, infer_year, parse_fr_amount

_STATEMENT_DATE = re.compile(r"Date d.arr\S*t\S*\s*:\s*(.+)", re.IGNORECASE)
_ACCOUNT_LINE = re.compile(r"^(?P<label>.*?)\s*\bn\S?\s*(?P<id>\d{11})\b", re.IGNORECASE)
_DDMM = re.compile(r"^(\d{2})\.(\d{2})$")
_BALANCE = re.compile(
    r"(?P<kind>Ancien|Nouveau)\s+solde\s+(?P<sign>cr\S*diteur|d\S*biteur)\s+au\s+(?P<date>\d{2}\.\d{2}\.\d{4})",
    re.IGNORECASE,
)


def _statement_date(doc: Document) -> date:
    for line in doc.pages[0].lines:
        m = _STATEMENT_DATE.search(line.text)
        if m and (d := find_french_long_date(m.group(1))):
            return d
    raise ParseError("Crédit Agricole: statement date ('Date d'arrêté') not found.")


def _account_headers(doc: Document) -> list[tuple[int, float, Account]]:
    headers = []
    for page in doc.pages:
        for line in page.lines:
            m = _ACCOUNT_LINE.search(line.text)
            if not m or "FRAIS" in line.text.upper():
                continue
            label = m.group("label")
            if " - " in label:  # "M. Jean Dupont - Compte Chèque"
                label = label.split(" - ", 1)[1]
            headers.append((page.number, line.top, Account(account_id=m.group("id"), label=clean_label(label))))
    return headers


def _ddmm(text: str, reference: date) -> date | None:
    m = _DDMM.match(text.strip())
    if not m:
        return None
    return infer_year(int(m.group(1)), int(m.group(2)), reference)


def parse_ca(doc: Document) -> ParsedStatement:
    statement_date = _statement_date(doc)
    headers = _account_headers(doc)
    if not headers:
        raise ParseError("Crédit Agricole: no account number found.")

    accounts: dict[str, Account] = {}
    for _, _, acc in headers:
        accounts.setdefault(acc.account_id, acc)

    ops: list[dict] = []
    opening: dict[str, tuple[date, Decimal]] = {}
    closing: dict[str, tuple[date, Decimal]] = {}
    warnings: list[str] = []
    current: str | None = None

    for page in doc.pages:
        for table in sorted(page.tables, key=lambda t: t.top):
            if not table.rows or len(table.rows[0]) < 5 or not cell(table.rows[0], 0).startswith("Date"):
                continue
            above = [h for h in headers if h[0] == page.number and h[1] < table.top]
            if above:
                current = max(above, key=lambda h: h[1])[2].account_id
            if current is None:
                current = headers[0][2].account_id

            for row in table.rows:
                first, label_cell = cell(row, 0), cell(row, 2)
                debit, credit = parse_fr_amount(cell(row, 3)), parse_fr_amount(cell(row, 4))
                if first.startswith("Date") or label_cell.startswith("Total des op"):
                    continue

                if m := _BALANCE.search(label_cell):
                    amount = credit if credit is not None else -(debit or Decimal(0))
                    if m.group("sign").lower().startswith("d") and amount > 0:
                        amount = -amount
                    dd, mm, yyyy = m.group("date").split(".")
                    entry = (date(int(yyyy), int(mm), int(dd)), amount)
                    if m.group("kind").lower() == "ancien":
                        opening.setdefault(current, entry)
                    else:
                        closing[current] = entry
                    continue

                op_date = _ddmm(first, statement_date)
                if op_date is not None:
                    if debit is None and credit is None:
                        warnings.append(f"Operation without amount ignored: {first} {label_cell!r}")
                        continue
                    amount = (credit or Decimal(0)) - (debit or Decimal(0))
                    ops.append(
                        {
                            "account_id": current,
                            "operation_date": op_date,
                            "value_date": _ddmm(cell(row, 1), statement_date),
                            "label": clean_label(label_cell),
                            "amount": amount,
                        }
                    )
                elif label_cell and debit is None and credit is None and ops and ops[-1]["account_id"] == current:
                    ops[-1]["label"] = clean_label(ops[-1]["label"] + " " + label_cell)

    transactions = [Transaction(**op) for op in ops]
    balances, checks = [], []
    for acc_id in accounts:
        o, c = opening.get(acc_id), closing.get(acc_id)
        balances += snapshots(acc_id, o or (None, None), c or (None, None))
        checks.append(balance_check(acc_id, o[1] if o else None, c[1] if c else None, transactions))

    return ParsedStatement(
        bank=BANK_NAMES[CA],
        bank_code=CA,
        owner=find_owner(doc.first_page_text),
        statement_date=statement_date,
        accounts=list(accounts.values()),
        transactions=transactions,
        balances=balances,
        checks=checks,
        warnings=warnings,
    )
