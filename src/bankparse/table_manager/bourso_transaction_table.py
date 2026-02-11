from bankparse.table_manager.base_table import BankTransactionTable
from bankparse.table_manager.utils import ddmmyyyy_date_to_yyyymmdd
import pdfplumber

class BoursoBankTransactionTable(BankTransactionTable):
    def __init__(self, content: list[str], owner: str, extraction_date: str, accountId: str, file_path:str):
        assert type(content) == list
        super().__init__()
        self.accountId = accountId
        self.content = content
        self.sourceBankLabel = 'Bourso Bank'
        self.owner = owner
        self.extraction_date = extraction_date
        self.file_path = file_path

    def getBalanceStatements(self):
        """
        Method to retrieve balance statements directly from the file.

        Returns:
            - list[dict[str, str]]
            keys: (source_bank, owner, extraction_date, 
            accountId, statement_date, balance.)
        """
        with pdfplumber.open(self.file_path) as pdf:
            words = []
            for i, page in enumerate(pdf.pages):
                words_in_page = page.extract_words(
                    use_text_flow=False,
                    keep_blank_chars=True,
                    x_tolerance=1
                )

                words += words_in_page

        first_statement_found = False
        last_statement_found = False
        for i, word in enumerate(words):
            if not first_statement_found:
                if "SOLDE" in word['text']:
                    if words[i+4]['x0'] < 500:
                        first_statement_amount = '-' + words[i+4]['text']
                    else:
                        first_statement_amount = words[i+4]['text']
                    first_statement_date = words[i+3]['text']
                    first_statement_found = True
            if not last_statement_found:
                if "Nouveau" in word['text']:
                    if words[i+5]['x0'] < 500:
                        last_statement_amount = '-' + words[i+5]['text']
                    else:
                        last_statement_amount = words[i+5]['text']
                    last_statement_found = True
        
        output = {
            'first':[first_statement_amount, first_statement_date],
            'second':[last_statement_amount, self.extraction_date]
        }

        return [
            {
                'source_bank':'Bourso Bank',
                'owner':self.owner, 
                'extraction_date':self.extraction_date,
                'accountId':self.accountId,
                'statement_date':value[1],
                'balance':value[0].replace('.', '').replace(',', '.')
            } for value in output.values()
        ]

    def get_dict(self):
        stage_output = super().get_dict()
        key1, key2 = list(stage_output.keys())[0], list(stage_output.keys())[2]
        stage_output[key1] = list(map(ddmmyyyy_date_to_yyyymmdd, stage_output[key1]))
        stage_output[key2] = list(map(ddmmyyyy_date_to_yyyymmdd, stage_output[key2]))

        return stage_output

    def get_dataframe(self):
        return super().get_dataframe()