import pdfplumber
from typing import List

def get_text_lines_from_pdf_file(path: str) -> List[str]:
    """
    Retrieve lines of text from the pdf file.

    Args:
        - path: path of the pdf file.

    Returns:
        - List containing the lines, None if there isn't any
    """

    with pdfplumber.open(path) as pdf:
        text = ""
        for page in pdf.pages:
            # tables_content = pdf.pages[0].extract_tables() # We can't retrieve the account number with this method
            text += page.extract_text() # it's harder, but we have both tables and accounts data.

    if text=="":
        return None
    return text.split('\n')