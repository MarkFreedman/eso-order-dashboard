"""SQL queries against the staging database."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import get_db


def list_orders() -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT o.id, o.status, o.customer_name, o.customer_no, o.po_number,
               o.order_date, o.overall_confidence, o.needs_review_reason,
               o.order_source, o.created_at,
               COUNT(li.id) AS item_count
        FROM orders o
        LEFT JOIN line_items li ON li.order_id = o.id
        GROUP BY o.id
        ORDER BY
            CASE o.status
                WHEN 'extracted' THEN 1
                WHEN 'in_review' THEN 2
                WHEN 'error' THEN 3
                WHEN 'submitted' THEN 4
            END,
            o.created_at DESC
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
          AND substr(o.submitted_at, 1, 10) BETWEEN ? AND ?
        GROUP BY o.id
        ORDER BY o.submitted_at DESC
        """,
        (start_date, end_date),
    ).fetchall()
    return [dict(r) for r in rows]


def get_order(order_id: int) -> dict[str, Any] | None:
    db = get_db()
    row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def get_line_items(order_id: int) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM line_items WHERE order_id = ? ORDER BY line_number",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_sources(order_id: int) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM sources WHERE order_id = ? ORDER BY id",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_order_fields(order_id: int, fields: dict[str, Any], reviewed_by: str | None = None) -> None:
    """Update allowed order fields. Sets status to in_review if currently extracted."""
    db = get_db()
    allowed = {
        "customer_no", "customer_name", "order_date", "po_number",
        "order_source", "order_type", "deposit_payment_type",
        "ship_to_name", "ship_to_address1", "ship_to_address2",
        "ship_to_city", "ship_to_state", "ship_to_zip",
        "needs_review_reason",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    current = get_order(order_id)
    if current and current["status"] == "extracted":
        updates["status"] = "in_review"
    if reviewed_by:
        updates["reviewed_by"] = reviewed_by
        updates["reviewed_at"] = _now()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [order_id]
    db.execute(f"UPDATE orders SET {set_clause} WHERE id = ?", values)
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
               SET item_code = ?, item_description = ?,
                   quantity_ordered = ?, unit_price = ?
               WHERE order_id = ? AND line_number = ?""",
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
           SET status = 'submitted', submitted_at = ?, vi_file_path = ?
           WHERE id = ?""",
        (_now(), vi_file_path, order_id),
    )
    db.commit()


def mark_error(order_id: int, message: str) -> None:
    db = get_db()
    db.execute(
        "UPDATE orders SET status = 'error', error_message = ? WHERE id = ?",
        (message, order_id),
    )
    db.commit()


def resolve_needs_review(order_id: int, order_number: str) -> list[dict[str, Any]]:
    """Set the order number and return placeholder sources for renaming."""
    db = get_db()
    db.execute(
        "UPDATE orders SET po_number = ?, needs_review_reason = NULL WHERE id = ?",
        (order_number, order_id),
    )
    placeholders = db.execute(
        "SELECT id, gdrive_path, placeholder_name FROM sources WHERE order_id = ? AND is_placeholder = 1",
        (order_id,),
    ).fetchall()
    db.commit()
    return [dict(r) for r in placeholders]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
