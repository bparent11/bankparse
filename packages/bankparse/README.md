# bankparse

**bankparse** extracts your **own** bank data from the PDF statements French banks send every month: operations, accounts and balances, as Python objects, JSON or a pandas DataFrame.

Supported statements:

| Bank | Document | Notes |
|---|---|---|
| Crédit Agricole | Relevé de comptes | one account per statement, labels on several lines are merged |
| Crédit Mutuel | Relevé et informations bancaires | several accounts per statement, savings and loans summary |
| Boursorama / BoursoBank | Relevé de compte | brokerage *espèces* / *titres* statements are not supported yet |

Every statement is **self-checked**: for each account, `opening balance + Σ operations == closing balance`. If an operation is missed or misread, the check fails, so you know whether you can trust the result.

## Installation

```bash
pip install bankparse      # or: uv add bankparse
```

Python ≥ 3.11.

## Examples

```python
import bankparse

statement = bankparse.parse("CM_2025-10-31.pdf")    # a path, bytes or a binary file object

statement.bank              # 'Crédit Mutuel'
statement.statement_date    # datetime.date(2025, 10, 31)
statement.is_consistent     # True -> balances match the operations

for t in statement.transactions:
    print(t.operation_date, t.account_id, t.label, t.amount)   # amount is a signed Decimal

df = statement.to_dataframe()      # pandas DataFrame, one row per operation
data = statement.to_dict()         # JSON-serializable dict
```

Errors are explicit:

```python
try:
    bankparse.parse("some.pdf")
except bankparse.UnsupportedStatementError:
    ...  # not a supported bank or document type
except bankparse.ParseError:
    ...  # bank recognized but the statement could not be read
```

### Output model

- `ParsedStatement`: `bank`, `bank_code` (`CA` | `CM` | `BOURSO`), `owner`, `statement_date`, `accounts`, `transactions`, `balances`, `checks`, `warnings`
- `Transaction`: `account_id`, `operation_date`, `value_date`, `label`, `amount` (`Decimal`, negative = debit)
- `BalanceSnapshot`: `account_id`, `date`, `amount`
- `BalanceCheck`: `opening`, `closing`, `total`, `ok`

### Legacy API

The class-based API from 0.0.x (`bankparse.file_manager.FileFactory`, `*AccountExtractionFile`, `*TransactionTable.get_dataframe()`) is still available and was fixed in 0.1.0, but `bankparse.parse()` is the recommended entry point.

## Changelog

**0.1.0**
- New `bankparse.parse()` API with a normalized, bank-agnostic output model and built-in balance checks.
- Crédit Agricole: statement date no longer confused with shop names, December operations dated in the right year, identical operations no longer dropped.
- Crédit Mutuel: balance rows no longer crash `get_dataframe()`, tables continued on the next page are attached to the right account, 2014-2016 layouts detected.
- Boursorama: rewritten line-based parser, accented letters repaired.
- Bank detection uses several signals (a statement mentioning another bank is no longer misdetected).

## Vision

Give people back their own data in an easy way. The package mainly covers the French market.

## License

MIT
