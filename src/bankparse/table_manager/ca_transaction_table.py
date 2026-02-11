from bankparse.table_manager.base_table import BankTransactionTable
from bankparse.utils import matches
import re

class CABankTransactionTable(BankTransactionTable):
    def __init__(self, content: list[str], owner: str, extraction_date: str, accountId: str):
        assert type(content) == list
        super().__init__()
        self.accountId = accountId
        self.content = content
        self.sourceBankLabel = 'Crédit Agricole'
        self.owner = owner
        self.extraction_date = extraction_date # file edition date
        self._statement_lines_indexes = []

        self.mergeTransactionLabel(inplace=True)
    
    @property
    def statement_lines_indexes(self):
        """
        Declaration of statement_lines_indexes as a property.
        """
        return self.statement_lines_indexes
    
    @statement_lines_indexes.setter
    def statement_lines_indexes(self, value):
        print("You can't set this value.")

    def mergeTransactionLabel(self, inplace:bool=False):
        line_to_del = []
        output = self.content.copy()
        for i, line in enumerate(output):
            if (line[-1] == '') and (line[-2] == ''):
                output[i-1][2] += ' ' + line[2]
                line_to_del.insert(0, i)
        
        for i in line_to_del:
            del output[i]
        
        if inplace==False:
            return output
        self.content = output

    def getBalanceStatements(self):
        if self._statement_lines_indexes == -1:
            print('Balance statements have been dropped.')
            return None
        
        stage_output = []
        for i, line in enumerate(self.content):
            if matches(r"(?i)solde\s+cr[ée]diteur\s+au\s+(\d{2}\.\d{2}\.\d{4})", line[2]):
                stage_output.insert(-1, line)
                self._statement_lines_indexes.append(i)
            else:
                pass
        
        return [
            {
                "source_bank":self.sourceBankLabel,
                "owner":self.owner,
                "file_extraction_date":self.extraction_date,
                "accountId": str(self.accountId),
                "statement_date": re.search(r"\d{2}\.\d{2}\.\d{4}", state[2]).group().replace('.', '/'),
                "balance": (
                        float(state[-1].replace('.', '').replace(',', '.').replace(" ", ""))
                        if state[-1] != ""
                        else -float(state[-2].replace('.', '').replace(',', '.').replace(" ", ""))
                )
            }
            for state in stage_output
        ]
    
    def dropBalanceStatements(self, inplace:str=True) -> list[list[str]] | None:
        if self._statement_lines_indexes == -1:
            print('Statements lines have already been dropped.')
            return None

        if self._statement_lines_indexes == []:
            for i, line in enumerate(self.content):
                if matches(r"\b\d{2}/\d{2}/\d{4}\b", line[0]) and 'solde' in line[0].lower():
                    self._statement_lines_indexes.append(i)

        temp_table = self.content.copy()
        self._statement_lines_indexes.sort(reverse=True)
        for index in self._statement_lines_indexes:
            del temp_table[index]

        if inplace==True:
            self._statement_lines_indexes = -1
            self.content = temp_table
            return None
        else:
            print(temp_table)

    def str_month_to_int(self, ddmm_date):
        month = ddmm_date.split('.')[-1].lstrip("0")
        
        return int(month)
    
    def ddmm_date_to_yyyymmdd(self, ddmm_date):
        if self.str_month_to_int(ddmm_date=ddmm_date) < 12:
            year = self.extraction_date.split('-')[0]
        else:
            year = str(int(self.extraction_date.split('-')[0]) - 1)

        dd, mm = ddmm_date.split('.')

        return "-".join((year, mm, dd))

    def get_dict(self):
        stage_output = super().get_dict()
        key1, key2 = list(stage_output.keys())[:2]
        stage_output[key1] = list(map(self.ddmm_date_to_yyyymmdd, stage_output[key1]))
        stage_output[key2] = list(map(self.ddmm_date_to_yyyymmdd, stage_output[key2]))

        key1, key2 = list(stage_output.keys())[-2:]
        stage_output[key1] = list(map(lambda x: x.replace(' ', '').replace(',', '.'), stage_output[key1]))
        stage_output[key2] = list(map(lambda x: x.replace(' ', '').replace(',', '.'), stage_output[key2]))

        return stage_output

    def get_dataframe(self):
        return super().get_dataframe()