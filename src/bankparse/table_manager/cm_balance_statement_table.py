from bankparse.table_manager import BalanceStatementTable

class CMBankStatementTable(BalanceStatementTable):
    def __init__(self, content: list[str], owner: str, extraction_date: str, accountId:str = 'Unknown'):
        assert type(content) == list
        super().__init__()
        self.accountId = accountId
        self.content = content
        self.sourceBankLabel = 'Crédit Mutuel'
        self.owner = owner
        self.extraction_date = extraction_date

        self.mergeTransactionLabel(inplace=True)

    def mergeTransactionLabel(self, inplace:bool=False) -> list[list[list[str]]] | None:
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
                output[i-1][1] += ' ' + line[1]
                line_to_del.insert(0, i)
        
        for i in line_to_del:
            del output[i]
        
        if inplace==False:
            return self.content
        self.content = output

    def get_dict(self):
        return super().get_dict()

    def get_dataframe(self):
        return super().get_dataframe()