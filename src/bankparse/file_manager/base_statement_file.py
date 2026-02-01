from abc import ABC, abstractmethod
from bankparse.file_manager.utils import get_text_lines_from_pdf_file

class AccountExtractionFile(ABC):
    """
    Abstract base class for bank account statement extractors.

    Any subclass must:
    - Be able to read a bank account statement pdf file (self.content assignment)
    - Implement a method to get the owner and extraction date of the pdf file.
    - Implement a method to get the informations about the bank accounts involved
    in the file.

    Some subclasses will have methods that the other ones don't have, depending on 
    the format of the statement file, provided by the bank.

    Attributes :
    - file_path (str): path of the pdf file.
    - owner (str | None): Extracted owner name. None until parsing is done.
    - extraction_date (str | None): Date of issue of the bank statement
    - content (list[str]) : Content of the pdf file, automatically retrieved 
    at instantiation time. Represents the lines of the pdf file. (using pdfplumber) 
    - transaction_tables, statement_tables, credit_tables (Any): Optional parsed 
    tables contained in the pdf file. Can contain lists of strings, instances of
    concrete table classes (e.g., CABankingTransactionsTable, CMBankingTransactionsTable).

    Comments:
    - Different kind of files wouldn't be available depending of the files that the devs 
    have at hand. Therefore, it may happen that some subclasses and/or methods are
    unavailable at this moment.
    """

    def __init__(self, file_path:str):
        assert '.pdf' in file_path, f"Invalid format : {file_path} isn't a pdf file."
        self.file_path = file_path
        self.owner = None
        self.extraction_date = None
        self.content = get_text_lines_from_pdf_file(path=self.file_path)
        self.transaction_tables = None
        self.statement_tables = None
        self.credit_tables = None

    @abstractmethod
    def get_owner_and_extract_date():
        pass

    @abstractmethod
    def accountIds_NamesMatching():
        pass