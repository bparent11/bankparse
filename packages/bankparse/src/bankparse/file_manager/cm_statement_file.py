from bankparse.file_manager.base_statement_file import AccountExtractionFile
from bankparse.table_manager import CMBankTransactionTable, CMBankStatementTable, CMCreditStatementTable
from bankparse.errors import ParseError
from bankparse.parsers._common import find_owner
from bankparse.utils import find_french_long_date, matches
import re, pdfplumber
from typing import Tuple, List, Dict

class CMAccountExtractionFile(AccountExtractionFile):
    """
    Class for extraction file from Bourso Bank.
    Inherits from abstract base class AccountExtractionFile.

    Attributes:
    - all the attributes from the base class.

    Methods :
    - get_owner_and_extract_date
    - get_transaction_tables
    - get_statement_tables
    - get_credit_tables
    - accountIds_NamesMatching
    """
    def __init__(self, file_path:str):
        super().__init__(file_path=file_path)
        self.owner, self.extraction_date = self.get_owner_and_extract_date(pdf_lines=self.content)
        accountIds_NamesMatching_results = self.accountIds_NamesMatching()
        self.transaction_tables = [
                CMBankTransactionTable(
                    content = table,
                    owner = self.owner,
                    accountId = accountIds_NamesMatching_results[i]['accountId'],
                    extraction_date = self.extraction_date
                ) for i, table in enumerate(self.get_transaction_tables(self.file_path))
            ]
        self.statement_tables = [
                CMBankStatementTable(
                    content = table,
                    owner = self.owner,
                    accountId = table[1][0],
                    extraction_date = self.extraction_date
                ) for table in self.get_statement_tables(self.file_path)
            ]
        self.credit_tables = [
                CMCreditStatementTable(
                    content = table,
                    owner = self.owner,
                    accountId = table[1][0],
                    extraction_date = self.extraction_date
                ) for table in self.get_credit_tables(self.file_path)
            ]

    def get_transaction_tables(self, file_path:str) -> List[List[List[str]]] | None:
        """
        Instance method to retrieve transaction tables within the file.
        Particularly used when the class is instancied.
        
        Args:
            - file_path (str) : path of the file containing the transaction tables.

        Returns:
            A list containing all of the tables.
            A table contains rows. A table is represented by a list of lists containing strings.
            A row if represented by a list of strings.
            The first row of a table represents the headers.
        """
        with pdfplumber.open(file_path) as pdf:
            transaction_tables = []
            for page in pdf.pages:
                transaction_tables += page.extract_tables()
        
        return [table for table in transaction_tables if (table[0][0] == 'Date')]

    def get_statement_tables(self, path:str) -> List[List[List[str]]] | None:
        """
        Instance method to retrieve statement tables within the file.
        Particularly used when the class is instancied.
        
        Args:
            - file_path (str) : path of the file containing the transaction tables.

        Returns:
            A list containing all of the tables.
            A table contains rows. A table is represented by a list of lists containing strings.
            A row if represented by a list of strings.
            The first row of a table represents the headers.
        """
        with pdfplumber.open(path) as pdf:
            statement_tables = []
            for page in pdf.pages:
                statement_tables += page.extract_tables()
        
        return [table for table in statement_tables if (table[0][0] != 'Date') and (len(table[0]) == 3)]
    
    def get_credit_tables(self, path:str) -> List[List[List[str]]] | None:
        """
        Instance method to retrieve credit tables within the file.
        Particularly used when the class is instancied.
        
        Args:
            - file_path (str) : path of the file containing the credit tables.

        Returns:
            A list containing all of the tables.
            A table contains rows. A table is represented by a list of lists containing strings.
            A row if represented by a list of strings.
            The first row of a table represents the headers.
        """
        with pdfplumber.open(path) as pdf:
            statement_tables = []
            for page in pdf.pages:
                statement_tables += page.extract_tables()
        
        return [table for table in statement_tables if (table[0][0] != 'Date') and (len(table[0]) == 4)]

    def get_owner_and_extract_date(self, pdf_lines:List[str]) -> Tuple[str, str]:
        """
        Instance method to retrieve the owner and the extract date of the file.
        Particularly used when the class is instancied.
        
        Args:
            - pdf_lines (List[str]) : File's lines.

        Returns:
            - Tuple[owner (str), extract_date (str)] : the owner and the extract date.
        """
        text = "\n".join(pdf_lines or [])
        owner = find_owner(text)
        for line in pdf_lines or []:
            # The statement date is alone on its line, e.g. "31 octobre 2025".
            if re.fullmatch(r"\s*\d{1,2}(?:er)?\s+\S+\s+\d{4}\s*", line) and (d := find_french_long_date(line)):
                return owner, d.isoformat()
        raise ParseError("Crédit Mutuel: statement date not found.")

    def accountIds_NamesMatching(self, pdf_lines: List[str] = None) -> List[Dict[str, str]]:
        """
        Instance method to retrieve the account ids of the statements tables within the file.
        Particularly used when the class is instancied.
        
        Args:
            - pdf_lines (List[str]) : File's lines.

        Returns:
            - List[Dict[str, str]] containing, for each match found, the accountId, the accountLabel and the owner.            
        """
        def accountIdsLines(text_lines: List[str]):
            # Filter into a new list: never mutate self.content.
            return [line for line in text_lines if matches(r"(?:N°\s*)\d{11}", line) and "FRAIS" not in line]

        if not pdf_lines:
            pdf_lines = self.content
        cleaned_lines = accountIdsLines(pdf_lines)

        return [
            dict(
                {
                    'accountId' : re.search(r"\d{11}", line_text).group(),
                    'accountLabel' : line_text.split(' N° ')[0] if '°' in line_text else re.sub(r"\d{11}", string = line_text.split(' EUR')[0], repl="").strip(),
                    'owner' : self.owner
                }
            )
            for line_text in cleaned_lines
        ]