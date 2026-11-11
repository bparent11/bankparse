from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

from pdfminer.pdfparser import PDFSyntaxError

from bankparse.detect import BOURSO, CA, CM, detect_bank
from bankparse.errors import ParseError, UnsupportedStatementError
from bankparse.models import ParsedStatement
from bankparse.parsers import parse_bourso, parse_ca, parse_cm
from bankparse.parsers._common import load_document, open_pdf

_PARSERS = {CA: parse_ca, CM: parse_cm, BOURSO: parse_bourso}


def parse(source: str | Path | bytes | BinaryIO) -> ParsedStatement:
    """
    Parse a bank statement PDF.

    Args:
        source: a path, the raw bytes of the PDF, or a binary file-like object.

    Returns:
        A :class:`ParsedStatement` with accounts, transactions, balances and balance checks.

    Raises:
        UnsupportedStatementError: not a PDF, or a bank/document type that is not supported.
        ParseError: the bank was recognized but the statement could not be read.
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    if isinstance(source, Path):
        source = str(source)

    try:
        pdf = open_pdf(source)
    except (PDFSyntaxError, Exception) as exc:  # pdfplumber raises several types on invalid input
        if isinstance(exc, FileNotFoundError):
            raise
        raise UnsupportedStatementError(f"Not a readable PDF file: {exc}") from exc

    with pdf:
        if not pdf.pages:
            raise UnsupportedStatementError("Empty PDF.")
        first_text = pdf.pages[0].extract_text() or ""
        bank = detect_bank(first_text)
        doc = load_document(pdf, with_words=bank == BOURSO, with_tables=bank != BOURSO)

    try:
        return _PARSERS[bank](doc)
    except ParseError:
        raise
    except Exception as exc:  # never leak an obscure IndexError to callers
        raise ParseError(f"{bank}: unexpected error while parsing ({type(exc).__name__}: {exc})") from exc
