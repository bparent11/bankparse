from bankparse.file_manager.base_statement_file import AccountExtractionFile
from bankparse.table_manager import CABankTransactionTable
from bankparse.utils import matches, month_from_name
import re, pdfplumber
from typing import Tuple, List, Dict

class CAAccountExtractionFile(AccountExtractionFile):
    """
    Class for extraction file from Crédit Agricole.
    Inherits from abstract base class AccountExtractionFile.

    Attributes:
    - all the attributes from the base class.

    Methods:
    - get_owner_and_extract_date
    - get_transaction_tables
    - accountIds_NamesMatching
    """
    def __init__(self, file_path:str):
        super().__init__(file_path=file_path)
        self.owner, self.extraction_date = self.get_owner_and_extract_date(pdf_lines=self.content)
        accountIds_NamesMatching_results = self.accountIds_NamesMatching()
        self.transaction_tables = [
                CABankTransactionTable(
                    content = self.get_transaction_tables(self.file_path),
                    owner = self.owner,
                    accountId = accountIds_NamesMatching_results[0]['accountId'],
                    extraction_date = self.extraction_date
                )
            ]

    def get_transaction_tables(self, file_path:str) -> List[List[str]] | None:
        """
        Instance method to retrieve transaction table within the file.
        Particularly used when the class is instancied.
        We consider here that there will be a unique transaction table in each statement file for CA.
        
        Args:
            - file_path (str) : path of the file containing the transaction table.

        Returns:
            A list containing all of the rows. We assumed that each extraction file contains a unique table.
            A table contains rows. A table is represented by a list of lists containing strings.
            A row if represented by a list of strings.
            The first row of a table represents the headers.
        """
        with pdfplumber.open(file_path) as pdf:
            transaction_tables = []
            for page in pdf.pages:
                transaction_tables += page.extract_tables()
            
            output = []
            seen = set()
            for table in transaction_tables:
                for line in table:
                    if (line[2] == 'Total des opérations') or (str(line) in seen):
                        pass
                    else:
                        seen.add(str(line))
                        output.append(line[:-1])

        return output

    def get_owner_and_extract_date(self, pdf_lines:List[str]) -> Tuple[str, str]:
        """
        Instance method to retrieve the owner and the extract date of the file.
        Particularly used when the class is instancied.
        
        Args:
            - file_path (str) : path of the file containing the transaction tables.

        Returns:
            - Tuple[owner (str), extract_date (str)] : the owner and the extract date.
        """
        owner_found=False

        for line in pdf_lines:
            owner_pattern = (
                r"(?:^|\s)"
                r"(?P<sexe>M|Mme|Mlle)\.?\s+"
                r"(?P<prenom>[A-Za-zÀ-ÖØ-öø-ÿ'-]+)\s+"
                r"(?P<nom>[A-Za-zÀ-ÖØ-öø-ÿ'-]+)"
            )
            
            extract_date_pattern = (
                r"(?P<day>\d{1,2})\s+"
                r"(?P<month>[a-zéèêûùàâîôç]+)\s+"
                r"(?P<year>\d{4})"
            )

            if not owner_found:
                m = (re.search(owner_pattern, line))
                if m:
                    owner = ' '.join([m.group("prenom").capitalize(), m.group("nom").capitalize()])
                    owner_found=True
            else:
                d = re.search(extract_date_pattern, line, flags=re.IGNORECASE)
                if d:
                    day = d.group("day").zfill(2)
                    month = month_from_name(d.group("month"))
                    year = d.group("year")
                    extract_date = f"{year}-{month}-{day}"

                    return owner, extract_date

    def accountIds_NamesMatching(self, pdf_lines: List[str] = None) -> List[Dict[str, str]]:
        """
        Instance method to retrieve the account ids of the statements tables within the file.
        Particularly used when the class is instancied.
        
        Args:
            - file_path (str) : path of the file containing the transaction tables.

        Returns:
            - List[Dict[str, str]] containing, for each match found, the accountId, the accountLabel and the owner.
            We assumed that each extraction file contains a unique table.
        """
        def accountIdsLines(text_lines: List[str]):
            for line in text_lines:
                if all(
                        (
                        matches(r"(?:n°\s*)\d{11}", line),
                        ('FRAIS' not in line)
                        )
                    ):
                    return line
                else:
                    pass

        if not pdf_lines:
            pdf_lines = self.content
        account_id_line = accountIdsLines(pdf_lines)

        return [
            dict(
                {
                    'accountId' : re.search(r"\d{11}", account_id_line).group(),
                    'accountLabel' : account_id_line.split(' n° ')[0],
                    'owner' : self.owner
                }
            )
        ]