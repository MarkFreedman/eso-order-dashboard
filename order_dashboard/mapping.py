"""Map DB rows to the dict shapes that templates and vi-export-generator expect.

Two separate mappings:
  db_to_detail()   — DB rows → template detail dict (for _decorate_order)
  detail_to_vi()   — DB rows → vi-export-generator order dict
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# DB → Template detail dict
# ---------------------------------------------------------------------------

def db_to_detail(
    order: dict[str, Any],
    line_items: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert DB rows into the dict shape that _decorate_order() expects."""

    fc = _parse_confidence(order.get("field_confidence"))

    # Detect VA from extraction result or customer_no pattern
    is_va = _detect_va(order, sources)

    # Primary source for the viewer
    primary_source = next(
        (s for s in sources if s.get("source_type") == "attachment" and s.get("gdrive_path")),
        sources[0] if sources else None,
    )

    # Build line items for template
    template_items = []
    for li in line_items:
        qty = li.get("quantity_ordered") or 0
        price = li.get("unit_price") or 0
        template_items.append({
            "line": li["line_number"],
            "item_number": li.get("item_code") or "",
            "description": li.get("item_description") or "",
            "quantity": qty,
            "unit_price": f"{price:.2f}" if price else "",
            "expected_price": f"{price:.2f}" if price else "",
            "extended_price": f"{qty * price:.2f}" if qty and price else "",
            "price_flagged": bool(li.get("price_flagged")),
        })

    return {
        "id": order["id"],
        "status": order["status"],
        "is_va": is_va,
        "source_type": order.get("order_source") or "EMAIL",
        "order_type": order.get("order_type") or "S",
        "order_number": order.get("po_number") or "",
        "po_number": order.get("po_number") or "",
        "order_date": order.get("order_date") or "",
        "reviewed_by": order.get("reviewed_by"),
        "reviewed_at": order.get("reviewed_at"),
        "needs_review_reason": order.get("needs_review_reason"),
        "source_filename": primary_source.get("original_filename") or primary_source.get("gdrive_filename") or "" if primary_source else "",
        "source_id": primary_source["id"] if primary_source else None,
        "customer_no": order.get("customer_no") or "",
        "customer_name": order.get("customer_name") or "",
        "ship_to": {
            "name": order.get("ship_to_name") or "",
            "line1": order.get("ship_to_address1") or "",
            "line2": order.get("ship_to_address2") or "",
            "city": order.get("ship_to_city") or "",
            "state": order.get("ship_to_state") or "",
            "zip": order.get("ship_to_zip") or "",
        },
        "payment": {
            "terms": order.get("deposit_payment_type") or "Check",
            "card_masked": None,
        },
        "totals": _compute_totals(line_items),
        "line_items": template_items,
        "field_confidence": _expand_confidence(fc),
    }


# ---------------------------------------------------------------------------
# DB → vi-export-generator order dict
# ---------------------------------------------------------------------------

def detail_to_vi(
    order: dict[str, Any],
    line_items: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the order dict that vi-export-generator's order_to_csv_rows() expects.

    The vi-export-generator expects fields with {value, confidence} wrappers.
    """
    # Try to get the full extraction result for fields not stored in the order table
    extraction = _get_extraction_result(sources)

    def wrap(value, confidence="HIGH"):
        return {"value": value, "confidence": confidence}

    vi_items = []
    for li in line_items:
        vi_items.append({
            "item_number": li.get("line_number"),
            "item_code": li.get("item_code") or "",
            "description": li.get("item_description") or "",
            "quantity": li.get("quantity_ordered") or 0,
            "unit": li.get("unit_of_measure") or "EA",
            "unit_price": li.get("unit_price") or 0,
            "amount": (li.get("quantity_ordered") or 0) * (li.get("unit_price") or 0),
            "confidence": "HIGH",
        })

    # Reconstruct ship_to as a single string (vi-export-generator parses it)
    ship_parts = [
        order.get("ship_to_name") or "",
        order.get("ship_to_address1") or "",
        order.get("ship_to_address2") or "",
    ]
    city_state_zip = ", ".join(filter(None, [
        order.get("ship_to_city"),
        order.get("ship_to_state"),
        order.get("ship_to_zip"),
    ]))
    if city_state_zip:
        ship_parts.append(city_state_zip)
    ship_to_str = ", ".join(p for p in ship_parts if p)

    # Detect document type from extraction result
    doc_type = extraction.get("document_type", "Customer Purchase Order") if extraction else "Customer Purchase Order"

    return {
        "document_type": doc_type,
        "order_source": order.get("order_source") or "EMAIL",
        "customer_po": wrap(order.get("po_number")),
        "customer_no": wrap(order.get("customer_no")),
        "order_date": wrap(_db_date_to_us(order.get("order_date"))),
        "ship_to": wrap(ship_to_str),
        "payment_type": order.get("deposit_payment_type") or "Check",
        "credit_card_last4": wrap(extraction.get("credit_card_last4", {}).get("value") if extraction else None),
        "line_items": vi_items,
        "flags": [],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_confidence(raw: str | dict | None) -> dict[str, float]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _expand_confidence(fc: dict[str, float]) -> dict[str, float]:
    """Expand condensed field confidence into the granular keys the template expects."""
    ship_score = fc.get("ship_to", 1.0)
    return {
        "order_number": fc.get("customer_po", 1.0),
        "po_number": fc.get("customer_po", 1.0),
        "order_date": fc.get("order_date", 1.0),
        "order_type": 1.0,
        "customer_no": fc.get("customer_no", 1.0),
        "customer_name": fc.get("customer_no", 1.0),
        "ship_to_name": ship_score,
        "ship_to_line1": ship_score,
        "ship_to_line2": ship_score,
        "ship_to_city": ship_score,
        "ship_to_state": ship_score,
        "ship_to_zip": ship_score,
        "terms": fc.get("payment_type", 1.0),
        "subtotal": 1.0,
        "tax": 1.0,
        "freight": 1.0,
        "total": 1.0,
    }


def _compute_totals(line_items: list[dict[str, Any]]) -> dict[str, str]:
    subtotal = sum(
        (li.get("quantity_ordered") or 0) * (li.get("unit_price") or 0)
        for li in line_items
    )
    return {
        "subtotal": f"{subtotal:.2f}",
        "tax": "0.00",
        "freight": "0.00",
        "total": f"{subtotal:.2f}",
    }


def _detect_va(order: dict[str, Any], sources: list[dict[str, Any]]) -> bool:
    """Detect if this is a VA order from extraction result or customer data."""
    for s in sources:
        raw = s.get("extraction_result")
        if raw:
            try:
                result = json.loads(raw) if isinstance(raw, str) else raw
                doc_type = result.get("document_type", "")
                if "VA" in doc_type.upper():
                    return True
            except (json.JSONDecodeError, TypeError):
                pass
    name = (order.get("customer_name") or "").upper()
    return "VA " in name or name.startswith("VA")


def _db_date_to_us(date_str: str | None) -> str | None:
    """Convert YYYY-MM-DD (DB format) to MM/DD/YYYY (vi-export-generator format)."""
    if not date_str:
        return None
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return date_str


def _get_extraction_result(sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Get the primary extraction result from sources."""
    for s in sources:
        raw = s.get("extraction_result")
        if raw:
            try:
                return json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                pass
    return None
