"""Crédit Mutuel statements ("RELEVE ET INFORMATIONS BANCAIRES"), possibly with several accounts."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bankparse.detect import BANK_NAMES, CM
from bankparse.errors import ParseError
from bankparse.models import Account, BalanceSnapshot, ParsedStatement, Transaction
from bankparse.parsers._common import Document, balance_check, cell, find_owner, snapshots
from bankparse.utils import clean_label, find_french_long_date, parse_ddmmyyyy, parse_fr_amount

_DATE_ONLY_LINE = re.compile(r"^\s*\d{1,2}(?:er)?\s+\S+\s+\d{4}\s*$")
_ACCOUNT_LINE = re.compile(r"^(?P<label>.+?)\s+N\S?\s*(?P<id>\d{11})\b")
_DDMMYYYY = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_BALANCE = re.compile(r"SOLDE\s+(?P<kind>CREDITEUR|DEBITEUR|NUL)\S*\s+AU\s+(?P<date>\d{2}/\d{2}/\d{4})", re.IGNORECASE)
_ACCOUNT_ID = re.compile(r"^\d{11}$")


def _statement_date(doc: Document) -> date:
    for line in doc.pages[0].lines:
        if _DATE_ONLY_LINE.match(line.text) and (d := find_french_long_date(line.text)):
            return d
    for line in doc.pages[0].lines:  # fallback: "SITUATION ... au 31 octobre 2025"
        if "SITUATION" in line.text.upper() and (d := find_french_long_date(line.text)):
            return d
    raise ParseError("Crédit Mutuel: statement date not found.")


def _account_headers(doc: Document) -> list[tuple[int, float, Account]]:
    headers = []
    for page in doc.pages:
        for line in page.lines:
            m = _ACCOUNT_LINE.search(line.text)
            if m and "FRAIS" not in line.text.upper():
                headers.append(
                    (page.number, line.top, Account(account_id=m.group("id"), label=clean_label(m.group("label"))))
                )
    return headers


def _date(text: str) -> date | None:
    text = text.strip()
    return parse_ddmmyyyy(text) if _DDMMYYYY.match(text) else None


def parse_cm(doc: Document) -> ParsedStatement:
    statement_date = _statement_date(doc)
    headers = _account_headers(doc)

    accounts: dict[str, Account] = {}
    for _, _, acc in headers:
        accounts.setdefault(acc.account_id, acc)

    ops: list[dict] = []
    opening: dict[str, tuple[date, Decimal]] = {}
    closing: dict[str, tuple[date, Decimal]] = {}
    extra_balances: list[BalanceSnapshot] = []
    warnings: list[str] = []
    current: str | None = None

    for page in doc.pages:
        for table in sorted(page.tables, key=lambda t: t.top):
            header = [cell(table.rows[0], i) for i in range(len(table.rows[0]))]

            # "SITUATION DE VOS AUTRES COMPTES" (3 cols) and "SITUATION DE VOS CREDITS" (4 cols)
            if header and header[0].startswith("Num") and len(header) in (3, 4):
                for row in table.rows[1:]:
                    acc_id, label = cell(row, 0), clean_label(cell(row, 1))
                    amount = parse_fr_amount(cell(row, len(header) - 1))
                    if _ACCOUNT_ID.match(acc_id) and amount is not None:
                        label = re.sub(r"\s+EUR$", "", label)
                        accounts.setdefault(acc_id, Account(account_id=acc_id, label=label))
                        extra_balances.append(BalanceSnapshot(acc_id, statement_date, amount))
                continue

            if len(header) < 5 or header[0] != "Date":
                continue

            above = [h for h in headers if h[0] == page.number and h[1] < table.top]
            if above:
                current = max(above, key=lambda h: h[1])[2].account_id
            if current is None:
                raise ParseError("Crédit Mutuel: transaction table found before any account number.")

            for row in table.rows[1:]:
                first = cell(row, 0)
                debit, credit = parse_fr_amount(cell(row, 3)), parse_fr_amount(cell(row, 4))

                if m := _BALANCE.search(first):
                    kind = m.group("kind").upper()
                    if kind == "NUL":
                        amount = Decimal(0)
                    else:
                        amount = credit if credit is not None else -(debit or Decimal(0))
                        if kind == "DEBITEUR" and amount > 0:
                            amount = -amount
                    entry = (parse_ddmmyyyy(m.group("date")), amount)
                    if current not in opening:
                        opening[current] = entry
                    else:
                        closing[current] = entry
                    continue

                op_date = _date(first)
                if op_date is not None:
                    if debit is None and credit is None:
                        warnings.append(f"Operation without amount ignored: {first} {cell(row, 2)!r}")
                        continue
                    ops.append(
                        {
                            "account_id": current,
                            "operation_date": op_date,
                            "value_date": _date(cell(row, 1)),
                            "label": clean_label(cell(row, 2)),
                            "amount": (credit or Decimal(0)) - (debit or Decimal(0)),
                        }
                    )
                elif first == "" and cell(row, 2) and ops and ops[-1]["account_id"] == current:
                    ops[-1]["label"] = clean_label(ops[-1]["label"] + " " + cell(row, 2))

    if not accounts:
        raise ParseError("Crédit Mutuel: no account found.")

    transactions = [Transaction(**op) for op in ops]
    balances: list[BalanceSnapshot] = []
    checks = []
    for acc_id in accounts:
        o, c = opening.get(acc_id), closing.get(acc_id)
        balances += snapshots(acc_id, o or (None, None), c or (None, None))
        if o or c:
            checks.append(balance_check(acc_id, o[1] if o else None, c[1] if c else None, transactions))
    known = {(b.account_id, b.date) for b in balances}
    balances += [b for b in extra_balances if (b.account_id, b.date) not in known]

    return ParsedStatement(
        bank=BANK_NAMES[CM],
        bank_code=CM,
        owner=find_owner(doc.first_page_text),
        statement_date=statement_date,
        accounts=list(accounts.values()),
        transactions=transactions,
        balances=balances,
        checks=checks,
        warnings=warnings,
    )
