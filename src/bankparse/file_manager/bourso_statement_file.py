from bankparse.file_manager.base_statement_file import AccountExtractionFile
from bankparse.table_manager import BoursoBankTransactionTable
from bankparse.utils import matches
import re, pdfplumber
from typing import Tuple, List, Dict

class BoursoAccountExtractionFile(AccountExtractionFile):
    """
    Class for extraction file from Crédit Agricole.
    Inherits from abstract base class AccountExtractionFile.

    Attributes :
    - file_path (str): path of the pdf file.

    Comments :
    - Devs don't have access to a Crédit Agricole's statement 
    file for a credit, therefore it's not implemented.
    - Crédit Agricole doesn't provide extract files if there 
    hasn't been any transactions during the month.
    Then BankStatement table isn't available.
    """
    def __init__(self, file_path:str):
        super().__init__(file_path=file_path)
        self.owner, self.extraction_date = self.get_owner_and_extract_date(pdf_lines=self.content)
        accountIds_NamesMatching_results = self.accountIds_NamesMatching(pdf_lines=self.content)
        
        self.transaction_tables = [
                BoursoBankTransactionTable(
                    content = self.get_transaction_tables(file_path=file_path),
                    owner = self.owner,
                    accountId = accountIds_NamesMatching_results[0]['accountId'],
                    extraction_date = self.extraction_date
                )
            ]

    def get_transaction_tables(self, file_path:str) -> List[List[str]] | None:
        """
        Instance method to retrieve transaction table within the file.
        Particularly used when the class is instancied.
        We consider here that there will be a unique transaction table in each statement file for Bourso.
        
        With the pdf.pages.extract_tables() method, it was impossible to differentiate credits and debits.

        Args:
            - file_path (str) : path of the file containing the transaction table.

        Returns:
            A list containing all of the rows. We assumed that each extraction file contains a unique table.
            A table contains rows. A table is represented by a list of lists containing strings.
            A row if represented by a list of strings.
            The first row of a table represents the headers.
        """
        operations = []
        operation = []
        extract_date_pattern = re.compile(
            r"^(\d{2}/\d{2}/\d{4}).*(\d{2}/\d{2}/\d{4})\s+\d+,\d{2}$"
        )

        # Column-based storage like
        with pdfplumber.open(file_path) as pdf: # je peux aussi récupérer les x y de chaque object, donc si je trouve les x y de chaque débit, crédit, je pourrais récup ça et l'utiliser
            transaction_tables = []
            for page in pdf.pages:
                transaction_tables += page.extract_tables()

            transaction_tables = [table for table in transaction_tables if table[0][0].startswith('Date')]

            output = []
            seen = set()
            for table in transaction_tables:
                for line in table:
                    if (str(line) in seen):
                        pass
                    else:
                        seen.add(str(line))
                        output.append(line)

        # print(f"Transaction tables for .extract_tables()")
        # print(output)
        final_statement_line = output.pop()

        debits = ""
        credits = ""
        for table_content in output[1:]:
            debits += table_content[-2] + '\n'
            credits += table_content[-1] + '\n'
        
        debits = debits.strip('\n').split('\n')
        credits = credits.strip('\n').split('\n')

        first_statement_line = credits[0]
        del credits[0]

        print("Debits and Credits")
        print(debits)
        print(credits)

        # Row-based storage like
        for line in self.content:
            date_regex = re.match(extract_date_pattern, line)

            if (date_regex): # tellement complexe, on peut pas non plus savoir si c'est un débit ou un crédit, je pense qu'on peut croiser les infos avec le .extract_table, sinon faut voir.
                # print('REGEXED')
                # print(line)
                operation = line.split(' ')
                date_regex = None
                continue
                
            if operation != []:
                operation[1] += ' ' + line

                if 'RŁf' in line:
                    operations.append(operation)
                    operation = []

        print("Opérations")
        print(operations)
        return operations # avec la méthode précédente, impossible de différence les débit des crédits.

    def get_statement_tables(self) -> None:
        """
        This method isn't used for Bourso statement files since this kind of table doesn't
        exist within the Bourso's documents.
        """
        pass
    
    def get_credit_tables(self, path:str) -> List[List[List[str]]] | None:
        """
        Instance method to retrieve credit tables within the file.
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
        
        return [table for table in statement_tables if (table[0][0] != 'Date') and (len(table[0]) == 4)]

    def get_owner_and_extract_date(self, pdf_lines:List[str]) -> Tuple[str, str]:
        """
        Instance method to retrieve the owner and the extract date of the file.
        Particularly used when the class is instancied.
        
        Args:
            - file_path (str) : path of the file containing the transaction tables.

        Returns:
            - Tuple[owner (str), extract_date (str)] : the owner and the extract date.
        """
        owner = None
        extract_date = None

        owner_pattern = re.compile(
            r"\b"
            r"(M|Mme|Mlle)\.?\s+"
            r"([A-Za-zÀ-ÖØ-öø-ÿ'-]+)\s+"
            r"([A-Za-zÀ-ÖØ-öø-ÿ'-]+)"
            r"\b"
        )

        extract_date_pattern = re.compile(
            r"\b\d{1,2}(?:\s+|/)"
            r"(?:\d{1,2}|[a-zéèêûùàâîôç]+)"
            r"(?:\s+|/)\d{4}\b",
            flags=re.IGNORECASE
        )

        for line in pdf_lines:
            if extract_date is None:
                d = extract_date_pattern.search(line)
                if d:
                    extract_date = d.group(0)

            if owner is None:
                m = owner_pattern.search(line)
                if m:
                    owner = f"{m.group(3).capitalize()} {m.group(2).capitalize()}"

            if owner and extract_date:
                return owner, extract_date

        return owner, extract_date

    def accountIds_NamesMatching(self, pdf_lines: List[str] = None) -> List[Dict[str, str]]:
        """
        Instance method to retrieve the account ids of the statement tables within the file.
        Particularly used when the class is instancied.
        
        Args:
            - file_path (str) : path of the file containing the transaction tables.

        Returns:
            - List[Dict[str, str]] containing, for each match found, the accountId, the accountLabel and the owner.
            We assumed that each extraction file contains a unique table.
        """
        for line in pdf_lines:
            rib = re.search(r"\bFR(?:\s?\d){25}\b", line)
            if rib:
                break

        return [
            dict(
                {
                    'accountId' : rib.group(),
                    'accountLabel' : "Compte espèces",
                    'owner' : self.owner
                }
            )
        ]