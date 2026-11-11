import re
import warnings

from bankparse.table_manager.base_table import BankTransactionTable
from bankparse.table_manager.utils import ddmmyyyy_date_to_yyyymmdd

_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_BALANCE = re.compile(r"(?i)solde\s+(crediteur|debiteur|nul)\S*\s+au\s+(\d{2}/\d{2}/\d{4})")


class CMBankTransactionTable(BankTransactionTable):
    def __init__(self, content: list[list[str]], owner: str, extraction_date: str, accountId: str = "Unknown"):
        if not isinstance(content, list):
            raise TypeError("content must be a list of rows")
        super().__init__()
        self.accountId = accountId
        self.content = content
        self.sourceBankLabel = "Crédit Mutuel"
        self.owner = owner
        self.extraction_date = extraction_date
        self._statement_lines_indexes = []

        self.mergeTransactionLabel(inplace=True)

    @property
    def statement_lines_indexes(self):
        """Indexes of the balance rows ("SOLDE CREDITEUR AU ...") within the content. Read-only."""
        return self._statement_lines_indexes

    def mergeTransactionLabel(self, inplace: bool = False) -> list[list[str]] | None:
        """
        Some labels are too long to fit in a unique cell within the pdf.
        This function merges the split label into the previous operation.

        Returns:
            - None if inplace is True. The content of the table will be merged inplace.
            - The merged content if inplace is False.
        """
        merged = []
        for row in (list(r) for r in self.content):  # copy rows: never alter the source
            if (row[0] in ("", None)) and merged and row[2]:
                merged[-1][2] = f"{merged[-1][2]} {row[2]}"
            else:
                merged.append(row)

        if not inplace:
            return merged
        self.content = merged

    def getBalanceStatements(self):
        if self._statement_lines_indexes == -1:
            warnings.warn("Balance statements have been dropped.", stacklevel=2)
            return None

        stage_output = []
        self._statement_lines_indexes = []
        for i, line in enumerate(self.content):
            if _BALANCE.search(str(line[0] or "")):
                stage_output.append(line)
                self._statement_lines_indexes.append(i)

        return [
            {
                "source_bank": self.sourceBankLabel,
                "owner": self.owner,
                "file_extraction_date": self.extraction_date,
                "accountId": str(self.accountId),
                "statement_date": _BALANCE.search(state[0]).group(2),
                "balance": (
                    0.0
                    if "NUL" in state[0]
                    else (
                        float(state[-1].replace(".", "").replace(",", "."))
                        if state[-1]
                        else -float(state[-2].replace(".", "").replace(",", "."))
                    )
                ),
            }
            for state in stage_output
        ]

    def dropBalanceStatements(self, inplace: bool = True) -> list[list[str]] | None:
        if self._statement_lines_indexes == -1:
            return None

        temp_table = [line for line in self.content if not _BALANCE.search(str(line[0] or ""))]
        if inplace:
            self._statement_lines_indexes = -1
            self.content = temp_table
            return None
        return temp_table

    def get_dict(self):
        """Operations only (balance rows are excluded), dates as yyyy-mm-dd, amounts as '1234.56'."""
        header = self.content[0]
        rows = [row for row in self.content[1:] if _DATE.match(str(row[0] or "").strip())]
        output = {key: [row[i] or "" for row in rows] for i, key in enumerate(header)}

        key1, key2 = list(output.keys())[:2]
        output[key1] = list(map(ddmmyyyy_date_to_yyyymmdd, output[key1]))
        output[key2] = [ddmmyyyy_date_to_yyyymmdd(v) if _DATE.match(v) else "" for v in output[key2]]

        key1, key2 = list(output.keys())[-2:]
        output[key1] = [v.replace(".", "").replace(",", ".") for v in output[key1]]
        output[key2] = [v.replace(".", "").replace(",", ".") for v in output[key2]]
        return output

    def get_dataframe(self):
        return super().get_dataframe()
