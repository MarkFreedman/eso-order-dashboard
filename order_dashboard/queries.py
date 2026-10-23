"""SQL queries against the staging database."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import get_db


_STATUS_RANK = """CASE o.status
                WHEN 'extracted' THEN 1
                WHEN 'in_review' THEN 2
                WHEN 'error' THEN 3
                WHEN 'submitted' THEN 4
                WHEN 'skipped' THEN 5
            END"""

# Queue columns a user can sort by, and the SQL that orders each. Anything not
# in here falls back to the default order, so a tampered query string cannot
# reach the SQL.
QUEUE_SORTS: dict[str, str] = {
    "status": _STATUS_RANK,
    "customer": "lower(COALESCE(o.customer_name, o.customer_no, ''))",
    "po": "lower(COALESCE(o.po_number, ''))",
    "order_date": "o.order_date",
    "items": "COUNT(li.id)",
    "confidence": "o.overall_confidence",
    "flags": "(o.needs_review_reason IS NOT NULL OR o.skip_reason IS NOT NULL)",
}


def list_orders(sort: str | None = None, direction: str = "asc") -> list[dict[str, Any]]:
    """The queue. Default order: work that needs attention first (by status),
    newest first within a status. ``sort`` names a column from QUEUE_SORTS;
    blanks sort last either way, and ties keep the newest first."""
    db = get_db()
    if sort in QUEUE_SORTS:
        way = "DESC" if direction == "desc" else "ASC"
        order_by = f"{QUEUE_SORTS[sort]} {way} NULLS LAST, o.created_at DESC"
    else:
        order_by = f"{_STATUS_RANK}, o.created_at DESC"
    rows = db.execute(
        f"""
        SELECT o.id, o.status, o.customer_name, o.customer_no, o.po_number,
               o.order_date, o.overall_confidence, o.needs_review_reason,
               o.order_source, o.created_at, o.skip_reason,
               COUNT(li.id) AS item_count
        FROM orders o
        LEFT JOIN line_items li ON li.order_id = o.id
        GROUP BY o.id
        ORDER BY {order_by}
        """
    ).fetchall()
    return [dict(r) for r in rows]


def submitted_orders_in_range(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Orders submitted to Sage between two dates (inclusive), newest first.

    Feeds the daily order-count report. start_date and end_date are
    'YYYY-MM-DD' strings. submitted_at is stored as an ISO 8601 string, so its
    first 10 characters are the submission date; comparing those substrings
    lexically is a correct date-range filter and avoids depending on SQLite's
    datetime parsing.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT o.id, o.po_number, o.customer_name, o.customer_no,
               o.order_date, o.order_source, o.submitted_at,
               o.sage_order_no, o.reviewed_by,
               substr(o.submitted_at, 1, 10) AS submitted_day,
               COUNT(li.id) AS item_count
        FROM orders o
        LEFT JOIN line_items li ON li.order_id = o.id
        WHERE o.status = 'submitted'
          AND o.submitted_at IS NOT NULL
          AND substr(o.submitted_at, 1, 10) BETWEEN %s AND %s
        GROUP BY o.id
        ORDER BY o.submitted_at DESC
        """,
        (start_date, end_date),
    ).fetchall()
    return [dict(r) for r in rows]


def get_order(order_id: int) -> dict[str, Any] | None:
    db = get_db()
    row = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def get_line_items(order_id: int) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM line_items WHERE order_id = %s ORDER BY line_number",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_sources(order_id: int) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM sources WHERE order_id = %s ORDER BY id",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# The reader's banner line for a document with no order number. Must match
# NO_ORDER_NUMBER_REASON in intake-service/intake_service/orchestrator.py. It
# contains a semicolon of its own, so it shows as two banner lines.
NO_ORDER_NUMBER_REASON = (
    "No PO or order number found on the document; enter it to file the PDF under it"
)
_NO_ORDER_NUMBER_PARTS = {p.strip() for p in NO_ORDER_NUMBER_REASON.split(";")}


def drop_no_order_number_line(reason: str | None) -> str | None:
    """The review reason without the reader's "no order number" line, or None
    when that was the only line."""
    if not reason:
        return None
    kept = [p.strip() for p in reason.split(";") if p.strip() and p.strip() not in _NO_ORDER_NUMBER_PARTS]
    return "; ".join(kept) or None


def update_order_fields(order_id: int, fields: dict[str, Any], reviewed_by: str | None = None) -> None:
    """Update allowed order fields. Sets status to in_review if currently extracted."""
    db = get_db()
    allowed = {
        "customer_no", "customer_name", "order_date", "po_number",
        "order_source", "order_type", "deposit_payment_type",
        "ship_to_name", "ship_to_address1", "ship_to_address2",
        "ship_to_city", "ship_to_state", "ship_to_zip",
        "needs_review_reason", "comment", "ship_via",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    current = get_order(order_id)
    if current and current["status"] == "extracted":
        updates["status"] = "in_review"
    if updates.get("po_number") and current and current.get("needs_review_reason"):
        # Typing the number into the Customer PO field settles the "no order
        # number" line the same way the Resolve box does; the reader then
        # renames the file. Other review lines stay.
        updates["needs_review_reason"] = drop_no_order_number_line(current["needs_review_reason"])
    if reviewed_by:
        updates["reviewed_by"] = reviewed_by
        updates["reviewed_at"] = _now()

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [order_id]
    db.execute(f"UPDATE orders SET {set_clause} WHERE id = %s", values)
    db.commit()


def update_line_items(order_id: int, items: list[dict[str, Any]]) -> None:
    """Update line items from form data."""
    db = get_db()
    for item in items:
        line_number = item.get("line_number")
        if line_number is None:
            continue
        db.execute(
            """UPDATE line_items
               SET item_code = %s, item_description = %s,
                   quantity_ordered = %s, unit_price = %s
               WHERE order_id = %s AND line_number = %s""",
            (
                item.get("item_code"),
                item.get("item_description"),
                item.get("quantity_ordered"),
                item.get("unit_price"),
                order_id,
                line_number,
            ),
        )
    db.commit()


def submit_order(order_id: int, vi_file_path: str | None = None) -> None:
    db = get_db()
    db.execute(
        """UPDATE orders
           SET status = 'submitted', submitted_at = %s, vi_file_path = %s
           WHERE id = %s""",
        (_now(), vi_file_path, order_id),
    )
    # The order is in Sage now and the G drive holds the permanent document,
    # so the database copy kept for the viewer can go.
    db.execute("UPDATE sources SET file_bytes = NULL WHERE order_id = %s", (order_id,))
    db.commit()


def mark_error(order_id: int, message: str) -> None:
    db = get_db()
    db.execute(
        "UPDATE orders SET status = 'error', error_message = %s WHERE id = %s",
        (message, order_id),
    )
    db.commit()


def resolve_needs_review(order_id: int, order_number: str) -> None:
    """Set the order number and clear the banner. The placeholder file keeps
    its name until the reader, which can reach the G drive, renames it on its
    next cycle (it looks for placeholder sources whose order now has a number)."""
    db = get_db()
    db.execute(
        "UPDATE orders SET po_number = %s, needs_review_reason = NULL WHERE id = %s",
        (order_number, order_id),
    )
    db.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
