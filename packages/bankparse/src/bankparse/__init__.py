"""bankparse - extract operations from French bank statement PDFs.

>>> import bankparse
>>> statement = bankparse.parse("Releve-compte-30-04-2025.pdf")
>>> statement.to_dataframe()
"""

from bankparse.core import parse
from bankparse.detect import detect_bank
from bankparse.errors import BankParseError, ParseError, UnsupportedStatementError
from bankparse.models import Account, BalanceCheck, BalanceSnapshot, ParsedStatement, Transaction

__version__ = "0.1.0"

__all__ = [
    "parse",
    "detect_bank",
    "Account",
    "BalanceCheck",
    "BalanceSnapshot",
    "ParsedStatement",
    "Transaction",
    "BankParseError",
    "ParseError",
    "UnsupportedStatementError",
]
