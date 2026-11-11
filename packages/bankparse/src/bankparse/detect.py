"""Detect which bank (and which kind of document) a PDF statement comes from."""

from __future__ import annotations

import re

from unidecode import unidecode

from bankparse.errors import UnsupportedStatementError

CA = "CA"
CM = "CM"
BOURSO = "BOURSO"

BANK_NAMES = {CA: "Crédit Agricole", CM: "Crédit Mutuel", BOURSO: "Boursorama"}


def detect_bank(first_page_text: str) -> str:
    """
    Return the bank code ("CA", "CM" or "BOURSO") of a statement from the text of its first page.

    Several signals are used for each bank (name, header, BIC, IBAN bank code) because the layouts
    changed over the years (e.g. old Crédit Mutuel statements only say "CCM <city>").

    Raises:
        UnsupportedStatementError if the document is not a supported account statement.
    """
    text = unidecode(first_page_text).upper()
    compact = re.sub(r"\s+", "", text)

    # 1. Strong structural signals first: operation labels may mention other banks
    #    (e.g. "Virement BoursoBank" on a Crédit Agricole statement).
    if "CREDITAGRICOLE" in compact and "DATED'ARRETE" in compact:
        return CA
    if "BOUSFRPP" in compact and "MOUVEMENTSENEUR" in compact:
        return BOURSO
    if "RELEVEETINFORMATIONSBANCAIRES" in compact or "CMCIFR" in compact or "FR761027" in compact:
        return CM

    # 2. Weaker signals: the bank name alone.
    if "BOURSORAMA" in text or "BOURSOBANK" in text:
        raise UnsupportedStatementError(
            "Boursorama document recognized, but only account statements ('Relevé de compte') are "
            "supported for now (not brokerage 'espèces' / 'titres' statements)."
        )
    if "CREDIT MUTUEL" in text or "CREDITMUTUEL" in compact:
        return CM

    raise UnsupportedStatementError("Unrecognized document: not a Crédit Agricole, Crédit Mutuel or Boursorama statement.")
