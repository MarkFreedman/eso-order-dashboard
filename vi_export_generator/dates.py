"""Date parsing and formatting for Sage 100 VI import.

Sage requires YYYYMMDD format. Input dates come in MM/DD/YYYY (US)
or DD/MM/YYYY (Canadian). The special value "PROCESSING_DATE" means
use the current processing date.
"""

from datetime import date, datetime


def parse_date_us(date_str):
    """Parse MM/DD/YYYY -> date object."""
    return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()


def parse_date_canadian(date_str):
    """Parse DD/MM/YYYY -> date object."""
    return datetime.strptime(date_str.strip(), "%d/%m/%Y").date()


def format_sage_date(d):
    """Format a date object as YYYYMMDD for Sage import."""
    return d.strftime("%Y%m%d")


def resolve_order_date(raw_date, is_canadian=False, processing_date=None):
    """Parse a raw date string and return (sage_date_str, date_obj).

    Handles the PROCESSING_DATE sentinel by substituting the processing date.
    The processing_date parameter defaults to today if not provided (pass a
    fixed date in tests for determinism).

    Note: the extraction step may have already converted DD/MM/YYYY to
    MM/DD/YYYY. We try US format first and fall back to Canadian if that
    fails and is_canadian is True.
    """
    if processing_date is None:
        processing_date = date.today()

    if not raw_date or raw_date == "PROCESSING_DATE":
        return format_sage_date(processing_date), processing_date

    # Try US format first (extraction may have pre-converted)
    try:
        d = parse_date_us(raw_date)
        return format_sage_date(d), d
    except ValueError:
        pass

    # Fall back to Canadian DD/MM/YYYY if flagged
    if is_canadian:
        d = parse_date_canadian(raw_date)
        return format_sage_date(d), d

    # Re-raise the original error
    d = parse_date_us(raw_date)
    return format_sage_date(d), d
