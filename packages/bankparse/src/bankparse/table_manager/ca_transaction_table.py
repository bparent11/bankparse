import re
import warnings
from datetime import date

from bankparse.table_manager.base_table import BankTransactionTable
from bankparse.utils import infer_year, matches

_DDMM = re.compile(r"^\d{2}\.\d{2}$")
_BALANCE = re.compile(r"(?i)solde\s+(cr[ée]diteur|d[ée]biteur)\s+au\s+(\d{2}\.\d{2}\.\d{4})")


class CABankTransactionTable(BankTransactionTable):
    def __init__(self, content: list[list[str]], owner: str, extraction_date: str, accountId: str):
        if not isinstance(content, list):
            raise TypeError("content must be a list of rows")
        super().__init__()
        self.accountId = accountId
        self.content = content
        self.sourceBankLabel = "Crédit Agricole"
        self.owner = owner
        self.extraction_date = extraction_date  # file edition date, yyyy-mm-dd
        self._statement_lines_indexes = []

        self.mergeTransactionLabel(inplace=True)

    @property
    def statement_lines_indexes(self):
        """Indexes of the balance rows ("Ancien/Nouveau solde ...") within the content. Read-only."""
        return self._statement_lines_indexes

    def mergeTransactionLabel(self, inplace: bool = False):
        """Merge label continuation rows (no date, no amount) into the previous operation."""
        output = [list(row) for row in self.content]  # deep enough copy: never alter the source rows
        merged = []
        for row in output:
            is_continuation = (
                merged and not row[0] and not row[1] and row[2] and not row[-1] and not row[-2]
            )
            if is_continuation:
                merged[-1][2] = f"{merged[-1][2]} {row[2]}"
            else:
                merged.append(row)
        for row in merged:
            row[2] = re.sub(r"\s+", " ", row[2] or "").strip()

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
            if _BALANCE.search(line[2] or ""):
                stage_output.append(line)
                self._statement_lines_indexes.append(i)

        return [
            {
                "source_bank": self.sourceBankLabel,
                "owner": self.owner,
                "file_extraction_date": self.extraction_date,
                "accountId": str(self.accountId),
                "statement_date": _BALANCE.search(state[2]).group(2).replace(".", "/"),
                "balance": (
                    float(state[-1].replace(".", "").replace(",", ".").replace(" ", ""))
                    if state[-1] != ""
                    else -float(state[-2].replace(".", "").replace(",", ".").replace(" ", ""))
                ),
            }
            for state in stage_output
        ]

    def dropBalanceStatements(self, inplace: bool = True) -> list[list[str]] | None:
        if self._statement_lines_indexes == -1:
            return None

        indexes = [i for i, line in enumerate(self.content) if _BALANCE.search(line[2] or "")]
        temp_table = [line for i, line in enumerate(self.content) if i not in indexes]

        if inplace:
            self._statement_lines_indexes = -1
            self.content = temp_table
            return None
        return temp_table

    def ddmm_date_to_yyyymmdd(self, ddmm_date: str) -> str:
        """'31.12' -> '2024-12-31' for a statement edited on 2025-01-06."""
        dd, mm = ddmm_date.split(".")
        reference = date.fromisoformat(self.extraction_date)
        return infer_year(int(dd), int(mm), reference).isoformat()

    def get_dict(self):
        """Operations only (balance and empty rows are excluded), dates as yyyy-mm-dd."""
        header = self.content[0]
        rows = [row for row in self.content[1:] if _DDMM.match(str(row[0]).strip())]
        output = {key: [row[i] for row in rows] for i, key in enumerate(header)}

        key1, key2 = list(output.keys())[:2]
        output[key1] = [self.ddmm_date_to_yyyymmdd(v) for v in output[key1]]
        output[key2] = [self.ddmm_date_to_yyyymmdd(v) if matches(r"^\d{2}\.\d{2}$", v) else "" for v in output[key2]]

        key1, key2 = list(output.keys())[-2:]
        output[key1] = [v.replace(" ", "").replace(",", ".") for v in output[key1]]
        output[key2] = [v.replace(" ", "").replace(",", ".") for v in output[key2]]
        return output

    def get_dataframe(self):
        return super().get_dataframe()
