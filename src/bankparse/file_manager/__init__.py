import pdfplumber, re

from bankparse.file_manager.base_statement_file     import AccountExtractionFile

from bankparse.file_manager.cm_statement_file       import CMAccountExtractionFile
from bankparse.file_manager.bourso_statement_file   import BoursoAccountExtractionFile
from bankparse.file_manager.ca_statement_file       import CAAccountExtractionFile

class FileFactory():
    """
    Factory that will provide the user with the right ExtractionFile class.
    """
    @staticmethod
    def handle_file(file_path:str) -> CAAccountExtractionFile | CMAccountExtractionFile | BoursoAccountExtractionFile:
        """
        Static method returning the right ExtractionFile class.

        Args:
            file_path (str): path of the pdf file.

        Returns:
            One of the implemented class within bankparse or None if the file hasn't been recognized. 
        """
        with pdfplumber.open(file_path) as pdf:
            first_page_elems = pdf.pages[0].extract_words(
                use_text_flow=False,
                keep_blank_chars=True,
                x_tolerance=1
            )

        for elem in first_page_elems:
            if (elem['text'] == 'Boursorama') & (elem['top'] > 770):
                return BoursoAccountExtractionFile(file_path=file_path)
            elif bool(re.search('CREDIT MUTUEL', elem['text'])) & (elem['top'] > 780):
                return CMAccountExtractionFile(file_path=file_path)
            elif (elem['text'] == 'CREDIT AGRICOLE') & (elem['top'] < 30):
                return CAAccountExtractionFile(file_path=file_path)
        
        return None