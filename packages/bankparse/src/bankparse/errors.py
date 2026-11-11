class BankParseError(Exception):
    """Base class for every error raised by bankparse."""


class UnsupportedStatementError(BankParseError):
    """The PDF is not a statement format bankparse knows how to read."""


class ParseError(BankParseError):
    """The bank was recognized but the statement could not be read."""
