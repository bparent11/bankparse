"""Merchant key: the stable part of an operation label, used to remember a category per merchant.

"CARTE X4847 CARREFOUR MARKET 12/03"  -> "CARREFOUR MARKET"
"PAIEMENT CB 0212 57050 MET SAS METZ" -> "MET SAS METZ"
"VIR SEPA LOYER"                      -> "LOYER"
"""

import re

from unidecode import unidecode

# Words describing the payment channel, not the merchant.
_CHANNEL = {"CARTE", "CB", "PAIEMENT", "PRLV", "PRELEVEMENT", "SEPA", "VIR", "VIREMENT", "INST", "INSTANTANE"}
_STOPWORDS = {"DE", "DU", "DES", "LA", "LE", "LES", "ET", "EN", "AU", "AUX", "A", "D", "L", "M", "MR", "MME", "MLLE"}
_REFERENCE = re.compile(r"\bREF\b.*$")  # "Réf : SCT4061..." and everything after
MAX_WORDS = 3


def merchant_key_words(label: str) -> list[str]:
    """All significant words of a label, in order (channel words, numbers, references removed)."""
    text = _REFERENCE.sub(" ", unidecode(label or "").upper())
    return [
        raw
        for raw in re.split(r"[^A-Z0-9]+", text)
        if raw and not any(ch.isdigit() for ch in raw) and raw not in _CHANNEL and raw not in _STOPWORDS and len(raw) >= 2
    ]


def merchant_key(label: str) -> str:
    words = merchant_key_words(label)[:MAX_WORDS]
    if words:
        return " ".join(words)
    # Nothing meaningful left (e.g. only a reference): fall back to the cleaned label itself.
    return " ".join(unidecode(label or "").upper().split()[:MAX_WORDS]) or "?"
