"""Helpers shared by the bank parsers. The PDF is read once into a :class:`Document`."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

import pdfplumber
from pdfplumber.pdf import PDF

from bankparse.models import BalanceCheck, BalanceSnapshot, Transaction

_CIVILITY_NAME = re.compile(r"(?:^|\s)(?:M|Mme|Mlle|Mr)\.?\s+([A-Za-zÀ-ÖØ-öø-ÿ'-]+\s+[A-Za-zÀ-ÖØ-öø-ÿ'-]+)")


@dataclass
class Line:
    text: str
    top: float


@dataclass
class Table:
    rows: list[list[str | None]]
    top: float


@dataclass
class Page:
    number: int
    text: str
    lines: list[Line]
    tables: list[Table]
    words: list[dict] = field(default_factory=list)


@dataclass
class Document:
    pages: list[Page]

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @property
    def first_page_text(self) -> str:
        return self.pages[0].text if self.pages else ""


def load_document(pdf: PDF, with_words: bool = False, with_tables: bool = True) -> Document:
    pages = []
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        lines = [Line(text=ln["text"], top=ln["top"]) for ln in page.extract_text_lines()]
        tables = []
        if with_tables:
            for t in page.find_tables():
                rows = t.extract()
                if rows:
                    tables.append(Table(rows=rows, top=t.bbox[1]))
        words = (
            page.extract_words(use_text_flow=False, keep_blank_chars=True, x_tolerance=1) if with_words else []
        )
        pages.append(Page(number=i, text=text, lines=lines, tables=tables, words=words))
    return Document(pages=pages)


def open_pdf(source) -> PDF:
    return pdfplumber.open(source)


def find_owner(text: str) -> str | None:
    m = _CIVILITY_NAME.search(text)
    if not m:
        return None
    return " ".join(part.capitalize() for part in m.group(1).split())


def cell(row: list, idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def balance_check(
    account_id: str, opening: Decimal | None, closing: Decimal | None, transactions: list[Transaction]
) -> BalanceCheck:
    total = sum((t.amount for t in transactions if t.account_id == account_id), Decimal(0))
    return BalanceCheck(account_id=account_id, opening=opening, closing=closing, total=total)


def snapshots(account_id: str, *pairs) -> list[BalanceSnapshot]:
    """Build balance snapshots from (date, amount) pairs, skipping incomplete ones."""
    return [
        BalanceSnapshot(account_id=account_id, date=d, amount=a)
        for d, a in pairs
        if d is not None and a is not None
    ]
