from bankparse.file_manager.base_statement_file import AccountExtractionFile
from bankparse.table_manager import BoursoBankTransactionTable
import re, pdfplumber
from typing import Tuple, List, Dict

class BoursoAccountExtractionFile(AccountExtractionFile):
    """
    Class for extraction file from Bourso Bank.
    Inherits from abstract base class AccountExtractionFile.

    Attributes:
    - all the attributes from the base class.

    Methods :
    - get_owner_and_extract_date
    - get_transaction_tables
    - accountIds_NamesMatching
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
                    extraction_date = self.extraction_date,
                    file_path=file_path
                )
            ]

    def get_transaction_tables(self, file_path:str) -> List[List[str]] | None:
        """
        Instance method to retrieve transaction tables within the file.
        Particularly used when the class is instancied.
        We consider here that there will be a unique transaction table in each statement file for Bourso.
        
        With the pdf.pages.extract_tables() method, it is impossible to differentiate credits and debits.

        Args:
            - file_path (str) : path of the file containing the transaction table.

        Returns:
            A list containing all of the rows. We assumed that each extraction file contains a unique table.
            A table contains rows. A table is represented by a list of lists containing strings.
            A row if represented by a list of strings.
            The first row of a table represents the headers.
        """
        with pdfplumber.open(file_path) as pdf:
            words = {}
            for i, page in enumerate(pdf.pages):
                words_in_page = page.extract_words(
                    use_text_flow=False,
                    keep_blank_chars=True,
                    x_tolerance=1
                )

                words[f"page_{i+1}"] = words_in_page

        mouvements_en_eur_found = False
        date_ope_found = False
        first_date_valeur_found = False
        ref_found = False

        output = {
            "Date opération":[],
            "Libellé":[],
            "Valeur":[],
            "Débit":[],
            "Crédit":[]
        }

        for page, words_list in words.items():
            mouvements_en_eur_found = False
            for i, word in enumerate(words_list):
                # Find "MOUVEMENTS EN EUR" to know that we can check for transactions.
                if all((word['text'] == 'MOUVEMENTS', word['x0'] > 360)):
                    mouvements_en_eur_found = True
                    continue

                # Check if we found a date (after MOUVEMENTS, and in Date opération or Date valeur)
                is_date = re.match(r'(\d{2}+/\d{2}+/\d{4}+)', word['text'])
                if all((mouvements_en_eur_found, is_date, any((word['x0'] < 90, word['x0'] > 370)))): # to avoid retrieving date within Libellé
                    # Check if we have a "Date opération"
                    if (word['x0'] < 90):
                        output['Date opération'].append(is_date.group())
                        output['Libellé'].append('')
                        date_ope_found = True
                        date_ope_index = i

                        if first_date_valeur_found and not ref_found:
                            output['Libellé'][-2] += ' '.join([''] + [word['text'] for word in words_list[transaction_amount_index+1:i]])
                        
                        ref_found = False

                    # Check if we have a "Date valeur"
                    elif all((word['x0'] > 370, date_ope_found)):
                        output['Libellé'][-1] += ' '.join([''] + [word['text'] for word in words_list[date_ope_index+1:i]]).strip()
                        output['Valeur'].append(word['text'])

                        transaction_amount = words_list[i+1]
                        transaction_amount_index = i+1

                        if transaction_amount['x0'] < 500:
                            output['Débit'].append(transaction_amount['text'])
                            output['Crédit'].append('')
                        else:
                            output['Débit'].append('')
                            output['Crédit'].append(transaction_amount['text'])

                        date_ope_found = False
                        first_date_valeur_found = True
                    
                    continue

                elif any(('RŁf' == word['text'], ('Nouveau' == word['text'] and word['x0'] > 683.0), ('A' == word['text'] and word['x0'] > 739.0))):
                    window_size = 2 if words_list[i+1]['text'] != ':' else 3
                    output['Libellé'][-1] += ' '.join([''] + [word['text'] for word in words_list[transaction_amount_index+1:i+window_size]])
                    ref_found = True

        headers = list(output.keys())
        values = list(output.values())
        output = []

        for i in range(len(values[0])):
            output.append([val[i] for val in values])

        output.insert(0, headers)
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