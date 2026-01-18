import re
from unidecode import unidecode

def matches(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text))

def month_from_name(month:str) -> str:
    """
    Transform french months to their associated number.

    Args:
        month: month name

    Returns:
        month number as a string
    """
    matching_table = {
        'janvier':'01',
        'fevrier':'02',
        'mars':'03',
        'avril':'04',
        'mai':'05',
        'juin':'06',
        'juillet':'07',
        'aout':'08',
        'septembre':'09',
        'octobre':'10',
        'novembre':'11',
        'decembre':'12'
    }

    key = unidecode(month).lower()
    if key not in matching_table:
        raise KeyError(f"Unknown month name: {month}")
    
    return matching_table[key]