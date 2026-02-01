import pdfplumber
from typing import List

def get_text_lines_from_pdf_file(path: str) -> List[str]:
    """
    Retrieve lines of text from the pdf file.

    Args:
        - path: path of the pdf file.

    Returns:
        List containing the lines, None if there isn't any
    """

    with pdfplumber.open(path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()

    if text=="":
        return None
    return text.split('\n')