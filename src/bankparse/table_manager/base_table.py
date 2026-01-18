from abc import ABC, abstractmethod

class Table(ABC):
    def __init__(self):
        self.sourceBankLabel = None
        self.accountId = None
        self.owner = None
        self.extraction_date = None

    @abstractmethod
    def mergeTransactionLabel(self):
        pass

    @abstractmethod
    def get_dict(self):
        pass

    @abstractmethod
    def get_dataframe(self):
        pass

class BankTransactionTable(Table):
    def __init__():
        pass

class BalanceStatementTable(Table):
    def __init__():
        pass

class CreditStatementTable(Table):
    def __init__():
        pass