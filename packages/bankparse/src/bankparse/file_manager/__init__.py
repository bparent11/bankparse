"""Legacy, class-based API. Prefer :func:`bankparse.parse` which returns a normalized ParsedStatement."""

import pdfplumber

from bankparse.detect import BOURSO, CA, CM, detect_bank
from bankparse.errors import UnsupportedStatementError
from bankparse.file_manager.base_statement_file import AccountExtractionFile
from bankparse.file_manager.bourso_statement_file import BoursoAccountExtractionFile
from bankparse.file_manager.ca_statement_file import CAAccountExtractionFile
from bankparse.file_manager.cm_statement_file import CMAccountExtractionFile

_CLASSES = {CA: CAAccountExtractionFile, CM: CMAccountExtractionFile, BOURSO: BoursoAccountExtractionFile}


class FileFactory:
    """
    Factory that will provide the user with the right ExtractionFile class.
    """

    @staticmethod
    def handle_file(
        file_path: str,
    ) -> CAAccountExtractionFile | CMAccountExtractionFile | BoursoAccountExtractionFile | None:
        """
        Static method returning the right ExtractionFile class.

        Args:
            file_path (str): path of the pdf file.

        Returns:
            One of the implemented class within bankparse or None if the file hasn't been recognized.
        """
        with pdfplumber.open(file_path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
        try:
            bank = detect_bank(first_page_text)
        except UnsupportedStatementError:
            return None
        return _CLASSES[bank](file_path=file_path)


__all__ = [
    "AccountExtractionFile",
    "BoursoAccountExtractionFile",
    "CAAccountExtractionFile",
    "CMAccountExtractionFile",
    "FileFactory",
]
