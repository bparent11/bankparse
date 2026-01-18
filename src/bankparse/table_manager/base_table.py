from abc import ABC, abstractmethod
import pandas as pd

class Table(ABC):
    def __init__(self):
        self.sourceBankLabel = None
        self.accountId = None
        self.owner = None
        self.extraction_date = None
        self.content = None

    @abstractmethod
    def mergeTransactionLabel(self):
        pass

    def get_dict(self):
        output = {}
        keys = self.content[0]
        values = self.content[1:]

        for i, key in enumerate(keys):
            output[key] = [val[i] for val in values]

        return output
    
    def get_dataframe(self):
        output = pd.DataFrame(
            data=self.get_dict()
        )

        return output

class BankTransactionTable(Table):
    def __init__(self):
        super().__init__()

class BalanceStatementTable(Table):
    def __init__(self):
        super().__init__()

class CreditStatementTable(Table):
    def __init__(self):
        super().__init__()