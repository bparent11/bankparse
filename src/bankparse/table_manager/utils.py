def ddmmyyyy_date_to_yyyymmdd(date):
    """
    Utils function to convert date from dd/mm/yyyy to yyyy-mm-dd.

    Args:
        - date (str): date under dd/mm/yyyy format.

    Return:
        date under yyyy-mm-dd format.
    """
    dd, mm, yyyy = date.split('/')
    return '-'.join((yyyy, mm, dd))