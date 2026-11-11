from abc import ABC, abstractmethod
import pandas as pd

class Table(ABC):
    """
    Class for table within the extraction files.
    Each subclass must implement a method to export the
    content of the table to a dict or a pandas DataFrame.

    Attributes:
    - sourceBankLabel (str): Name of the bank from which the table comes from.
    - accountId (str): Account's id from which the table comes from.
    - owner (str): Account's owner.
    - extraction_date (str): File's extraction date.
    - content (list[list[str]]): Table's content.

    Methods:
    - get_dict: return table's content as a dict
    - get_dataframe: return table's content as a pandas DataFrame.

    Comments:
    - Different kind of tables wouldn't be available depending of the files that the dev 
    have at hand. Therefore, it may happen that some subclasses and/or methods are
    unavailable at this moment.
    """
    def __init__(self):
        self.sourceBankLabel = None
        self.accountId = None
        self.owner = None
        self.extraction_date = None
        self.content = None

    @abstractmethod
    def get_dict(self):
        """
        Method returning table's content as a python dict.
        """
        output = {}
        keys = self.content[0]
        values = self.content[1:]

        for i, key in enumerate(keys):
            output[key] = [val[i] for val in values]

        return output
    
    @abstractmethod
    def get_dataframe(self):
        """
        Method returning table's content as a pandas DataFrame.
        """
        output = pd.DataFrame(
            data=self.get_dict()
        )

        return output
    
    def mergeTransactionLabel(self, inplace:bool=False):
        """
        Some label are too long to fit in a unique cell within the pdf.
        This function merge the split label into one unique.
        
        The merging should be done automatically when the transaction table is instanciated.
        """
        pass

    def getBalanceStatements(self):
        """
        Method to retrieve balance statements directly from the file.

        Returns:
            - list[dict[str, str]]
            keys: (source_bank, owner, extraction_date, 
            accountId, statement_date, balance.)
        """
        pass

    def dropBalanceStatements(self, inplace:str=True) -> list[list[str]] | None:
        """ 
        
        """
        pass

class BankTransactionTable(Table):
    def __init__(self):
        super().__init__()

class BalanceStatementTable(Table):
    def __init__(self):
        super().__init__()

class CreditStatementTable(Table):
    def __init__(self):
        super().__init__()