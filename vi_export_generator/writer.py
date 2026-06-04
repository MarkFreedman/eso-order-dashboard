"""CSV output generation for Sage 100 VI import."""

import csv
from pathlib import Path

from .extract import Warnings
from .validate import validate_order
from .mapper import map_header, map_detail_line
from .field_layouts import HEADER_FIELDS, DETAIL_FIELDS, dict_to_row


# The combined layout: all header columns, then all detail columns. The two
# fields that appear in both (SalesOrderNo, WarehouseCode) get a "Detail_"
# prefix on the detail side so column names are unique.
_DETAIL_OVERLAP = {"SalesOrderNo", "WarehouseCode"}
COMBINED_FIELDS = tuple(
    list(HEADER_FIELDS)
    + [f"Detail_{f}" if f in _DETAIL_OVERLAP else f for f in DETAIL_FIELDS]
)


def order_to_csv_rows(order, processing_date=None):
    """Convert an order dict to CSV rows (two-record-type layout).

    Produces one header row (112 cols) followed by one detail row per
    line item (74 cols). This is the legacy two-record layout.

    Returns (rows, warnings) where:
    - rows: list of lists, or None if validation errors prevent generation
    - warnings: list of warning/error strings
    """
    errors, validation_warnings = validate_order(order)
    if errors:
        return None, errors + validation_warnings

    warnings = Warnings()
    warnings.items.extend(validation_warnings)

    header_values = map_header(order, processing_date, warnings)
    header_row = dict_to_row(HEADER_FIELDS, header_values)

    detail_rows = []
    for i, item in enumerate(order.get("line_items", [])):
        detail_values = map_detail_line(order, item, i, warnings)
        detail_rows.append(dict_to_row(DETAIL_FIELDS, detail_values))

    rows = [header_row] + detail_rows
    return rows, warnings.items


def order_to_combined_rows(order, processing_date=None):
    """Convert an order dict to combined rows, one row per line item.

    Each row has all 112 header fields followed by all 74 detail fields
    (186 columns total). The header fields are duplicated on every row
    for orders with multiple line items.

    Returns (rows, warnings) where:
    - rows: list of lists (one row per line item), or None if validation fails
    - warnings: list of warning/error strings
    """
    errors, validation_warnings = validate_order(order)
    if errors:
        return None, errors + validation_warnings

    warnings = Warnings()
    warnings.items.extend(validation_warnings)

    header_values = map_header(order, processing_date, warnings)
    header_part = dict_to_row(HEADER_FIELDS, header_values)

    rows = []
    for i, item in enumerate(order.get("line_items", [])):
        detail_values = map_detail_line(order, item, i, warnings)
        detail_part = dict_to_row(DETAIL_FIELDS, detail_values)
        rows.append(list(header_part) + list(detail_part))

    return rows, warnings.items


def write_csv(rows, output_path, include_headers=False, trim_empty_columns=False):
    """Write CSV rows to a file.

    Creates parent directories if needed. If include_headers=True, writes
    the COMBINED_FIELDS column names as the first row (for the combined
    layout). If trim_empty_columns=True, drops any column that is empty
    in every data row before writing (Avron's preference so he does not
    have to count past blank fields during VI job setup).
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data_rows = list(rows)
    if include_headers:
        column_names = list(COMBINED_FIELDS)
    else:
        column_names = None

    if trim_empty_columns and data_rows:
        column_names, data_rows = _trim_empty_columns(column_names, data_rows)

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        if column_names is not None:
            writer.writerow(column_names)
        writer.writerows(data_rows)


def _trim_empty_columns(column_names, data_rows):
    """Drop columns that are empty ("") in every data row.

    Keeps columns with any non-empty value. Returns (column_names, data_rows)
    with the dropped columns removed from both. If column_names is None,
    returns None for column_names and still trims data_rows.
    """
    if not data_rows:
        return column_names, data_rows

    num_cols = len(data_rows[0])
    keep = [False] * num_cols
    for row in data_rows:
        for i, val in enumerate(row):
            if not keep[i] and val != "":
                keep[i] = True

    trimmed_rows = [
        [val for i, val in enumerate(row) if keep[i]] for row in data_rows
    ]
    trimmed_names = (
        [n for i, n in enumerate(column_names) if keep[i]]
        if column_names is not None
        else None
    )
    return trimmed_names, trimmed_rows
