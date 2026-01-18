from bankparse.table_manager import BankTransactionTable
from bankparse.utils import matches
import re
from typing import List

class CMBankTransactionTable(BankTransactionTable):
    def __init__(self, content: list[str], owner: str, extraction_date: str, accountId:str = 'Unknown'):
        assert type(content) == list
        super().__init__()
        self.accountId = accountId
        self.content = content
        self.sourceBankLabel = 'Crédit Mutuel'
        self.owner = owner
        self.extraction_date = extraction_date # file edition date
        self._statement_lines_indexes = []
    
    @property
    def statement_lines_indexes(self):
        """
        Declaration of statement_lines_indexes as a property, to protect
        """
        return self._statement_lines_indexes
    
    @statement_lines_indexes.setter
    def statement_lines_indexes(self, value):
        print("You can't set this value.")

    def mergeTransactionLabel(self, inplace:bool=False) -> List[List[List[str]]] | None:
        """
        Some label are too long to fit in a unique cell within the pdf.
        This function merge the split label into one unique.

        Returns:
            - None if inplace is True. The content of the table will be merged inplace.
            - The merged content if inplace is False. 
        """
        line_to_del = []
        output = self.content.copy()
        for i, line in enumerate(output):
            if line[0] == '':
                output[i-1][2] += ' ' + line[2]
                line_to_del.insert(0, i)
        
        for i in line_to_del:
            del output[i]
        
        if inplace==False:
            return self.content
        self.content = output

    def getBalanceStatements(self):
        if self._statement_lines_indexes == -1:
            print('Balance statements have been dropped.')
            return None
        
        stage_output = []
        for i, line in enumerate(self.content):
            if matches(r"\b\d{2}/\d{2}/\d{4}\b", line[0]) and 'SOLDE' in line[0]:
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
                "statement_date": re.search(r"\b\d{2}/\d{2}/\d{4}\b", state[0]).group(),
                "balance": (
                    0.0
                    if "NUL" in state[0]
                    else (
                        float(state[-1].replace('.', '').replace(',', '.'))
                        if state[-1] != ""
                        else -float(state[-2].replace('.', '').replace(',', '.'))
                    )
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
                if matches(r"\b\d{2}/\d{2}/\d{4}\b", line[0]) and 'SOLDE' in line[0]:
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

    def get_dict(self):
        return super().get_dict()
    
    def get_dataframe(self):
        return super().get_dataframe()