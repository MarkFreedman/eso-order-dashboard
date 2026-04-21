"""Order queue and detail routes — reads from the staging database."""

from __future__ import annotations

import os
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from . import mapping, queries

bp = Blueprint("queue", __name__)

CONF_GREEN = 0.85
CONF_YELLOW = 0.60

STATUS_LABELS = {
    "extracted": "Extracted",
    "in_review": "In Review",
    "submitted": "Submitted",
    "error": "Error",
}


def _conf_band(score: float | None) -> str:
    if score is None:
        return "red"
    if score >= CONF_GREEN:
        return "green"
    if score >= CONF_YELLOW:
        return "yellow"
    return "red"


def _field(value, score: float) -> dict:
    missing = value is None or value == ""
    return {
        "value": "" if missing else value,
        "score": score,
        "band": "missing" if missing else _conf_band(score),
        "missing": missing,
    }


def _decorate_order(detail: dict) -> dict:
    fc = detail["field_confidence"]
    ship = detail["ship_to"]
    return {
        **detail,
        "status_label": STATUS_LABELS.get(detail["status"], detail["status"]),
        "status_class": detail["status"].replace("_", "-"),
        "f": {
            "order_number": _field(detail["order_number"], fc.get("order_number", 1.0)),
            "po_number": _field(detail["po_number"], fc.get("po_number", 1.0)),
            "order_date": _field(detail["order_date"], fc.get("order_date", 1.0)),
            "order_type": _field(detail["order_type"], fc.get("order_type", 1.0)),
            "customer_no": _field(detail["customer_no"], fc.get("customer_no", 1.0)),
            "customer_name": _field(detail["customer_name"], fc.get("customer_name", 1.0)),
            "ship_to_name": _field(ship["name"], fc.get("ship_to_name", 1.0)),
            "ship_to_line1": _field(ship["line1"], fc.get("ship_to_line1", 1.0)),
            "ship_to_line2": _field(ship["line2"], fc.get("ship_to_line2", 1.0)),
            "ship_to_city": _field(ship["city"], fc.get("ship_to_city", 1.0)),
            "ship_to_state": _field(ship["state"], fc.get("ship_to_state", 1.0)),
            "ship_to_zip": _field(ship["zip"], fc.get("ship_to_zip", 1.0)),
            "terms": _field(detail["payment"]["terms"], fc.get("terms", 1.0)),
            "subtotal": _field(detail["totals"]["subtotal"], fc.get("subtotal", 1.0)),
            "tax": _field(detail["totals"]["tax"], fc.get("tax", 1.0)),
            "freight": _field(detail["totals"]["freight"], fc.get("freight", 1.0)),
            "total": _field(detail["totals"]["total"], fc.get("total", 1.0)),
        },
    }


# ---------------------------------------------------------------------------
# Queue view
# ---------------------------------------------------------------------------

@bp.get("/")
def index():
    rows = queries.list_orders()
    orders = [
        {
            **row,
            "customer_name": row.get("customer_name") or row.get("customer_no") or f"Order #{row['id']}",
            "conf_band": _conf_band(row.get("overall_confidence")),
            "status_label": STATUS_LABELS.get(row["status"], row["status"]),
            "status_class": row["status"].replace("_", "-"),
        }
        for row in rows
    ]
    return render_template("queue.html", orders=orders)


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------

@bp.get("/orders/<int:order_id>")
def detail(order_id: int):
    order = queries.get_order(order_id)
    if order is None:
        abort(404)
    line_items = queries.get_line_items(order_id)
    sources = queries.get_sources(order_id)
    detail_dict = mapping.db_to_detail(order, line_items, sources)
    return render_template("detail.html", order=_decorate_order(detail_dict))


# ---------------------------------------------------------------------------
# Save / Submit / Error actions
# ---------------------------------------------------------------------------

@bp.post("/orders/<int:order_id>")
def save(order_id: int):
    action = request.form.get("action", "save")

    # Handle needs-review resolution
    resolved = request.form.get("resolved_order_number", "").strip()
    if resolved:
        placeholders = queries.resolve_needs_review(order_id, resolved)
        _rename_placeholders(placeholders, resolved)
        flash(f"Order number set to {resolved}")
        return redirect(url_for("queue.detail", order_id=order_id))

    if action == "save":
        _save_draft(order_id)
        flash("Draft saved")
        return redirect(url_for("queue.detail", order_id=order_id))

    if action == "submit":
        return _submit_to_sage(order_id)

    if action == "error":
        queries.mark_error(order_id, "Flagged by reviewer")
        flash("Order flagged as error")
        return redirect(url_for("queue.index"))

    return redirect(url_for("queue.detail", order_id=order_id))


def _save_draft(order_id: int) -> None:
    form = request.form
    fields = {
        "customer_no": form.get("customer_no", "").strip(),
        "customer_name": form.get("customer_name", "").strip(),
        "order_date": form.get("order_date", "").strip(),
        "po_number": form.get("po_number", "").strip(),
        "order_type": form.get("order_type", "").strip(),
        "ship_to_name": form.get("ship_to_name", "").strip(),
        "ship_to_address1": form.get("ship_to_line1", "").strip(),
        "ship_to_address2": form.get("ship_to_line2", "").strip(),
        "ship_to_city": form.get("ship_to_city", "").strip(),
        "ship_to_state": form.get("ship_to_state", "").strip(),
        "ship_to_zip": form.get("ship_to_zip", "").strip(),
    }
    queries.update_order_fields(order_id, fields)

    # Parse line items from form
    items = []
    i = 1
    while f"li_{i}_item" in form:
        items.append({
            "line_number": i,
            "item_code": form.get(f"li_{i}_item", "").strip(),
            "item_description": form.get(f"li_{i}_desc", "").strip(),
            "quantity_ordered": _to_float(form.get(f"li_{i}_qty")),
            "unit_price": _to_float(form.get(f"li_{i}_unit")),
        })
        i += 1
    if items:
        queries.update_line_items(order_id, items)


def _submit_to_sage(order_id: int):
    order = queries.get_order(order_id)
    if order is None:
        abort(404)
    line_items = queries.get_line_items(order_id)
    sources = queries.get_sources(order_id)

    vi_dict = mapping.detail_to_vi(order, line_items, sources)

    try:
        from vi_export_generator import order_to_csv_rows, write_csv
    except ImportError:
        flash("VI export generator not installed — cannot submit to Sage")
        return redirect(url_for("queue.detail", order_id=order_id))

    from datetime import date
    rows, warnings = order_to_csv_rows(vi_dict, processing_date=date.today())
    if rows is None:
        flash(f"VI export failed: {warnings}")
        return redirect(url_for("queue.detail", order_id=order_id))

    # Write the CSV
    output_dir = Path(os.environ.get("VI_OUTPUT_DIR", "tmp/vi-output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"order_{order_id}.csv"
    output_path = output_dir / filename
    write_csv(rows, output_path)

    queries.submit_order(order_id, str(output_path))
    if warnings:
        flash(f"Submitted to Sage with warnings: {'; '.join(warnings)}")
    else:
        flash(f"Submitted to Sage — VI file: {filename}")
    return redirect(url_for("queue.index"))


# ---------------------------------------------------------------------------
# Batch submit
# ---------------------------------------------------------------------------

@bp.post("/batch-submit")
def batch_submit():
    order_ids = request.form.getlist("order_ids", type=int)
    if not order_ids:
        flash("No orders selected")
        return redirect(url_for("queue.index"))

    try:
        from vi_export_generator import order_to_csv_rows, write_csv
    except ImportError:
        flash("VI export generator not installed — cannot submit to Sage")
        return redirect(url_for("queue.index"))

    from datetime import date

    all_rows = []
    errors = []
    submitted_ids = []

    for oid in order_ids:
        order = queries.get_order(oid)
        if order is None or order["status"] == "submitted":
            continue
        line_items = queries.get_line_items(oid)
        sources = queries.get_sources(oid)
        vi_dict = mapping.detail_to_vi(order, line_items, sources)
        rows, warnings = order_to_csv_rows(vi_dict, processing_date=date.today())
        if rows is None:
            errors.append(f"Order {oid}: {warnings}")
            continue
        all_rows.extend(rows)
        submitted_ids.append(oid)

    if not all_rows:
        flash(f"No orders exported. Errors: {'; '.join(errors)}")
        return redirect(url_for("queue.index"))

    output_dir = Path(os.environ.get("VI_OUTPUT_DIR", "tmp/vi-output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"batch_{timestamp}.csv"
    output_path = output_dir / filename
    write_csv(all_rows, output_path)

    for oid in submitted_ids:
        queries.submit_order(oid, str(output_path))

    msg = f"Submitted {len(submitted_ids)} orders to Sage — {filename}"
    if errors:
        msg += f" ({len(errors)} failed: {'; '.join(errors)})"
    flash(msg)
    return redirect(url_for("queue.index"))


# ---------------------------------------------------------------------------
# Source PDF serving
# ---------------------------------------------------------------------------

@bp.get("/sources/<int:source_id>/file")
def source_file(source_id: int):
    from .db import get_db
    db = get_db()
    row = db.execute(
        "SELECT gdrive_path, original_filename FROM sources WHERE id = ?",
        (source_id,),
    ).fetchone()
    if row is None or not row["gdrive_path"]:
        abort(404)

    storage_root = Path(os.environ.get("FILE_STORAGE_ROOT", "../intake-service")).resolve()
    full_path = (storage_root / row["gdrive_path"]).resolve()
    # Finding 7: ensure the resolved path stays within the storage root.
    if not full_path.is_relative_to(storage_root):
        abort(403)
    if not full_path.exists():
        abort(404)

    return send_file(
        str(full_path),
        mimetype="application/pdf",
        download_name=row["original_filename"] or "source.pdf",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rename_placeholders(placeholders: list[dict], order_number: str) -> None:
    """Rename needs-review placeholder files on disk."""
    # Finding 2: sanitize user-supplied order number before using it in a
    # file rename, and verify the result stays within the storage root.
    safe = "".join(c for c in order_number if c.isalnum() or c in "-_.")
    storage_root = Path(os.environ.get("FILE_STORAGE_ROOT", "../intake-service")).resolve()
    for p in placeholders:
        old_path = (storage_root / p["gdrive_path"]).resolve()
        if not old_path.is_relative_to(storage_root):
            continue
        if old_path.exists():
            new_path = (old_path.parent / f"{safe}.pdf").resolve()
            if not new_path.is_relative_to(storage_root):
                continue
            old_path.rename(new_path)
            from .db import get_db
            db = get_db()
            db.execute(
                """UPDATE sources
                   SET gdrive_path = ?, gdrive_filename = ?,
                       is_placeholder = 0
                   WHERE id = ?""",
                (str(Path(p["gdrive_path"]).parent / new_name), new_name, p["id"]),
            )
            db.commit()


def _to_float(v: str | None) -> float | None:
    if not v:
        return None
    try:
        return float(v.strip())
    except (ValueError, AttributeError):
        return None
