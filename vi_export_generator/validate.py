"""Pre-generation validation for order data.

Returns errors (block CSV generation) and warnings (proceed but flag).
"""

import re

from .extract import get_value, get_confidence


# Pattern for detecting full credit card numbers (13-19 consecutive digits)
CC_PATTERN = re.compile(r"\b\d{13,19}\b")


def validate_order(order):
    """Validate an order dict before CSV generation.

    Returns (errors: list[str], warnings: list[str]).
    Errors prevent generation. Warnings allow it but flag issues.
    """
    errors = []
    warnings = []

    # Line items required
    line_items = order.get("line_items")
    if not line_items:
        errors.append("No line_items in order")
    else:
        for i, item in enumerate(line_items):
            if not item.get("item_code"):
                errors.append(f"Line item {i + 1}: missing item_code")
            if item.get("quantity") is None:
                errors.append(f"Line item {i + 1}: missing quantity")

    # Order date. Not a hard error here because the mapper falls back to the
    # processing date when this is missing, so the output always has a value.
    raw_date = get_value(order.get("order_date"))
    if not raw_date:
        warnings.append("order_date is missing; will use processing date")

    # Customer number. This one IS required for Sage VI import (Avron confirmed
    # 2026-04-23 that rows with blank CustomerNo fail outright). Elevated to an
    # error so the CSV is never generated with a blank customer number.
    cust_conf = get_confidence(order.get("customer_no"))
    cust_val = get_value(order.get("customer_no"))
    if not cust_val:
        errors.append(
            "customer_no is required (Sage VI import will reject rows without "
            "a customer number). Please look up and enter the customer number."
        )
    elif cust_conf in ("LOW", "MISSING"):
        warnings.append(f"customer_no confidence is {cust_conf}: {cust_val!r}")

    # Payment type
    payment = order.get("payment_type")
    if not payment:
        warnings.append("payment_type is missing; defaulting to Check")

    # PCI safety: scan all string values for full credit card numbers
    _pci_check(order, errors)

    # Check confidence on key fields
    for field_name in ("customer_po", "order_date", "ship_to"):
        field_data = order.get(field_name)
        if field_data:
            conf = get_confidence(field_data)
            if conf in ("LOW", "MISSING"):
                val = get_value(field_data)
                warnings.append(f"{field_name}: confidence={conf}, value={val!r}")

    # Line item confidence
    if line_items:
        for i, item in enumerate(line_items):
            conf = item.get("confidence", "HIGH")
            if conf in ("LOW", "MISSING"):
                warnings.append(f"Line item {i + 1}: confidence={conf}")

    return errors, warnings


def _pci_check(order, errors):
    """Scan order values for anything that looks like a full credit card number.

    Only checks fields that would appear in output (value fields),
    not extraction metadata (source, notes, confidence).
    """
    # Metadata keys to skip — these contain extraction context, not output data
    METADATA_KEYS = {"source", "notes", "confidence", "customer_po_notes",
                     "ship_to_notes", "payment_type_notes", "credit_card_notes",
                     "customer_no_notes", "item_code_notes", "order_date_notes",
                     "total_notes"}
    _scan_value(order, "", errors, METADATA_KEYS)


def _scan_value(obj, path, errors, skip_keys):
    """Recursively scan a value for credit card number patterns."""
    if isinstance(obj, str):
        if CC_PATTERN.search(obj):
            errors.append(
                f"PCI violation: possible full credit card number at {path}"
            )
    elif isinstance(obj, dict):
        for key, val in obj.items():
            if key in skip_keys:
                continue
            _scan_value(val, f"{path}.{key}" if path else key, errors, skip_keys)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            _scan_value(val, f"{path}[{i}]", errors, skip_keys)
