"""Map extracted order data to Sage 100 VI field values.

This is the core business logic. Each function returns a dict of
Sage field names -> values. Only populated fields are included;
field_layouts.dict_to_row() fills in empties for the rest.
"""

import re
from datetime import date

from .extract import get_value, get_confidence, Warnings
from .dates import resolve_order_date, format_sage_date
from .address import parse_ship_to


def map_header(order, processing_date=None, warnings=None):
    """Map an order dict to a header values dict.

    Returns dict keyed by Sage field names (only populated fields).
    """
    if warnings is None:
        warnings = Warnings()
    if processing_date is None:
        processing_date = date.today()

    values = {}

    # SalesOrderNo: always blank — Sage auto-assigns
    values["SalesOrderNo"] = ""

    # OrderType: S (Standard) by default
    doc_type = get_value(order.get("document_type", ""))
    if isinstance(doc_type, str) and "quote" in doc_type.lower():
        values["OrderType"] = "Q"
    else:
        values["OrderType"] = "S"

    # OrderStatus: ALWAYS Hold
    values["OrderStatus"] = "H"

    # OrderDate
    is_canadian = _is_canadian(order)
    raw_date = warnings.check_confidence("order_date", order.get("order_date"))
    if not raw_date:
        raw_date = ""
    sage_date, order_date_obj = resolve_order_date(
        raw_date, is_canadian, processing_date
    )
    values["OrderDate"] = sage_date
    values["ShipExpireDate"] = sage_date

    # Customer number: split into ARDivisionNo + CustomerNo
    raw_cust = warnings.check_confidence(
        "customer_no", order.get("customer_no")
    )
    div_no, cust_no = _split_customer_no(raw_cust, warnings)
    values["ARDivisionNo"] = div_no
    values["CustomerNo"] = cust_no
    values["BillToDivisionNo"] = div_no
    values["BillToCustomerNo"] = cust_no

    # CustomerPONo
    raw_po = warnings.check_confidence(
        "customer_po", order.get("customer_po")
    )
    if not raw_po:
        values["CustomerPONo"] = (
            f"KEC Stock {processing_date.strftime('%m.%d.%y')}"
        )
    else:
        values["CustomerPONo"] = str(raw_po)[:30]  # max 30 chars

    # Ship-to address from the order document
    raw_ship = warnings.check_confidence("ship_to", order.get("ship_to"))
    if raw_ship:
        ship_parts = parse_ship_to(str(raw_ship))
        values.update(ship_parts)

    # Payment
    payment_type_str, payment_ref = _resolve_payment(order, warnings)
    values["PaymentType"] = payment_type_str
    if payment_ref:
        values["OtherPaymentTypeRefNo"] = payment_ref

    # UDF: OrderSource — FAX or EMAIL
    source = _resolve_order_source(order)
    values["UDF_OrderSource"] = source

    # UDF: DepositPaymentType
    raw_payment = get_value(order.get("payment_type", ""), "")
    if isinstance(raw_payment, str) and "credit" in raw_payment.lower():
        values["UDF_DepositPaymentType"] = "Credit Card"
    else:
        values["UDF_DepositPaymentType"] = "Check"

    return values


def map_detail_line(order, line_item, line_index, warnings=None):
    """Map a single line item to a detail values dict.

    line_index is 0-based; LineKey will be (line_index+1) zero-filled to 6 digits.
    """
    if warnings is None:
        warnings = Warnings()

    values = {}
    values["SalesOrderNo"] = ""
    values["LineKey"] = f"{(line_index + 1):06d}"

    item_code = get_value(line_item.get("item_code", ""))
    values["ItemCode"] = str(item_code)[:30]  # max 30 chars

    # ItemType: 1 = Regular item
    values["ItemType"] = "1"

    description = get_value(line_item.get("description", ""))
    if description:
        values["ItemCodeDesc"] = str(description)[:30]

    qty = line_item.get("quantity")
    if qty is not None:
        values["QuantityOrdered"] = str(qty)

    price = line_item.get("unit_price")
    if price is not None:
        # Canadian orders may use comma decimals
        price_str = str(price)
        if "," in price_str:
            price_str = price_str.replace(",", ".")
        values["UnitPrice"] = price_str
    else:
        warnings.add(
            f"Line {line_index + 1} ({item_code}): "
            "unit_price is missing; must pull from Sage catalog"
        )

    # Check line item confidence
    conf = line_item.get("confidence", "HIGH")
    if conf in ("LOW", "MISSING"):
        warnings.add(
            f"Line {line_index + 1} ({item_code}): confidence={conf}"
        )

    return values


# --- Internal helpers ---


def _is_canadian(order):
    """Check if this is a Canadian order."""
    doc_type = get_value(order.get("document_type", ""), "")
    if isinstance(doc_type, str) and "canadian" in doc_type.lower():
        return True
    currency = get_value(order.get("currency", ""), "")
    if isinstance(currency, str) and currency.upper() == "CAD":
        return True
    return False


def _split_customer_no(raw, warnings):
    """Split a customer number into (ARDivisionNo, CustomerNo).

    Expected format: "51-0K824" where "51" is the 2-digit division.
    Handles partial numbers like "CA924" (no division prefix, defaults to "00").
    Handles multiple entries like "TX365-T (W-TX222)" (takes first).

    Avron confirmed 2026-04-23 that ARDivisionNo must be "00" when there is no
    division prefix, since division and customer number are paired in Sage and
    "00" is the default division.
    """
    if not raw:
        return "", ""

    raw = str(raw).strip()

    # If multiple account numbers in parens, take the first one
    # e.g., "TX365-T (W-TX222)" -> "TX365-T"
    paren_match = re.match(r"^([^(]+)", raw)
    if paren_match:
        raw = paren_match.group(1).strip()

    # Try to split on dash: "51-0K824" -> div="51", cust="0K824"
    parts = raw.split("-", 1)
    if len(parts) == 2:
        potential_div = parts[0].strip()
        # Division must be exactly 2 digits
        if re.match(r"^\d{2}$", potential_div):
            return potential_div, parts[1].strip()[:20]

    # No valid division prefix found, default to "00"
    if warnings:
        warnings.add(
            f"customer_no '{raw}' has no 2-digit division prefix; "
            "ARDivisionNo defaulted to '00'"
        )
    return "00", raw[:20]


def _resolve_payment(order, warnings):
    """Determine PaymentType and OtherPaymentTypeRefNo.

    Returns (payment_type: str, payment_ref: str or None).
    """
    payment = get_value(order.get("payment_type", ""), "")

    if isinstance(payment, str) and "credit" in payment.lower():
        # Credit card payment — build reference from last 4 digits
        last4_field = order.get("credit_card_last4")
        last4 = get_value(last4_field, "")
        if last4:
            ref = f"VISA*{last4}"
        else:
            ref = None
            warnings.add(
                "Payment is Credit Card but credit_card_last4 is missing"
            )
        return "Credit Card", ref

    # Default to Check
    return "Check", None


def _resolve_order_source(order):
    """Map order_source or document_type to FAX or EMAIL."""
    source = get_value(order.get("order_source", ""), "")
    if isinstance(source, str):
        upper = source.upper()
        if "FAX" in upper:
            return "FAX"
        if "EMAIL" in upper:
            return "EMAIL"

    # Fall back to document_type
    doc_type = get_value(order.get("document_type", ""), "")
    if isinstance(doc_type, str):
        upper = doc_type.upper()
        if "EMAIL" in upper:
            return "EMAIL"
        # Most faxed documents are purchase orders / authorizations
        if any(kw in upper for kw in ("PURCHASE", "AUTHORIZATION", "FAX")):
            return "FAX"

    return "FAX"  # safe default — fax is the primary channel
