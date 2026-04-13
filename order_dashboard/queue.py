from flask import Blueprint, abort, flash, redirect, render_template, url_for

bp = Blueprint("queue", __name__)

CONF_GREEN = 0.85
CONF_YELLOW = 0.60

SAMPLE_ORDERS = [
    {
        "id": 1001,
        "status": "extracted",
        "customer_name": "VA Medical Center - Palo Alto",
        "order_date": "2026-04-11",
        "item_count": 3,
        "overall_confidence": 0.94,
        "needs_review_reason": None,
    },
    {
        "id": 1002,
        "status": "extracted",
        "customer_name": "Eyecare Associates of Tulsa",
        "order_date": "2026-04-11",
        "item_count": 3,
        "overall_confidence": 0.72,
        "needs_review_reason": None,
    },
    {
        "id": 1003,
        "status": "extracted",
        "customer_name": "Unknown (fax header unreadable)",
        "order_date": "2026-04-11",
        "item_count": 2,
        "overall_confidence": 0.48,
        "needs_review_reason": "No order number found on document",
    },
    {
        "id": 1004,
        "status": "in_review",
        "customer_name": "Low Vision Center of Dallas",
        "order_date": "2026-04-10",
        "item_count": 5,
        "overall_confidence": 0.88,
        "needs_review_reason": None,
    },
    {
        "id": 1005,
        "status": "in_review",
        "customer_name": "VA Medical Center - Phoenix",
        "order_date": "2026-04-10",
        "item_count": 7,
        "overall_confidence": 0.66,
        "needs_review_reason": None,
    },
    {
        "id": 1006,
        "status": "error",
        "customer_name": "Optical Shoppe of Boise",
        "order_date": "2026-04-09",
        "item_count": 2,
        "overall_confidence": 0.55,
        "needs_review_reason": "Price mismatch on line 2 exceeds tolerance",
    },
    {
        "id": 1007,
        "status": "submitted",
        "customer_name": "Hadley Institute for the Blind",
        "order_date": "2026-04-08",
        "item_count": 4,
        "overall_confidence": 0.97,
        "needs_review_reason": None,
    },
    {
        "id": 1008,
        "status": "submitted",
        "customer_name": "VA Medical Center - Bay Pines",
        "order_date": "2026-04-08",
        "item_count": 1,
        "overall_confidence": 0.91,
        "needs_review_reason": None,
    },
]


SAMPLE_ORDER_DETAILS = {
    1001: {
        "id": 1001,
        "status": "extracted",
        "is_va": True,
        "source_type": "EMAIL",
        "order_type": "S",
        "order_number": "VA-2026-0411-A",
        "po_number": "PO-998877",
        "order_date": "2026-04-11",
        "reviewed_by": None,
        "reviewed_at": None,
        "needs_review_reason": None,
        "source_filename": "va_palo_alto_20260411.pdf",
        "source_pages": 2,
        "sample_pdf": "samples/va-sample.pdf",
        "customer_no": "VA0042",
        "customer_name": "VA Medical Center - Palo Alto",
        "ship_to": {
            "name": "Veteran M. Torres",
            "line1": "3801 Miranda Ave",
            "line2": "Blind Rehab Unit",
            "city": "Palo Alto",
            "state": "CA",
            "zip": "94304",
        },
        "payment": {
            "terms": "Net 30",
            "card_masked": None,
        },
        "totals": {
            "subtotal": "412.00",
            "tax": "0.00",
            "freight": "12.50",
            "total": "424.50",
        },
        "line_items": [
            {
                "line": 1,
                "item_number": "1661-3",
                "description": "MAXI PLUS 3x Hand Magnifier",
                "quantity": 2,
                "unit_price": "89.00",
                "expected_price": "89.00",
                "extended_price": "178.00",
                "price_flagged": False,
            },
            {
                "line": 2,
                "item_number": "1511-1",
                "description": "Mobilent Monocular 4x12",
                "quantity": 1,
                "unit_price": "134.00",
                "expected_price": "134.00",
                "extended_price": "134.00",
                "price_flagged": False,
            },
            {
                "line": 3,
                "item_number": "2655-K",
                "description": "Smartlux Digital Handheld Video Magnifier",
                "quantity": 1,
                "unit_price": "100.00",
                "expected_price": "112.00",
                "extended_price": "100.00",
                "price_flagged": False,
            },
        ],
        "field_confidence": {
            "order_number": 0.98,
            "po_number": 0.91,
            "order_date": 0.99,
            "order_type": 0.97,
            "customer_no": 0.96,
            "customer_name": 0.99,
            "ship_to_name": 0.88,
            "ship_to_line1": 0.93,
            "ship_to_line2": 0.71,
            "ship_to_city": 0.94,
            "ship_to_state": 0.98,
            "ship_to_zip": 0.97,
            "terms": 0.92,
            "subtotal": 0.99,
            "tax": 0.99,
            "freight": 0.88,
            "total": 0.99,
        },
    },
    1002: {
        "id": 1002,
        "status": "extracted",
        "is_va": False,
        "source_type": "FAX",
        "order_type": "S",
        "order_number": "TUL-88241",
        "po_number": "",
        "order_date": "2026-04-11",
        "reviewed_by": None,
        "reviewed_at": None,
        "needs_review_reason": None,
        "source_filename": "fax_tulsa_20260411.pdf",
        "source_pages": 1,
        "sample_pdf": "samples/mi413-sample.pdf",
        "customer_no": "EYE0118",
        "customer_name": "Eyecare Associates of Tulsa",
        "ship_to": {
            "name": "Mrs. Helen Ramsey",
            "line1": "2210 E 21st St",
            "line2": "",
            "city": "Tulsa",
            "state": "OK",
            "zip": "74114",
        },
        "payment": {
            "terms": "",
            "card_masked": "VISA*1024",
        },
        "totals": {
            "subtotal": "327.00",
            "tax": "27.80",
            "freight": "9.75",
            "total": "364.55",
        },
        "line_items": [
            {
                "line": 1,
                "item_number": "1661-3",
                "description": "MAXI PLUS 3x Hand Magnifier",
                "quantity": 1,
                "unit_price": "89.00",
                "expected_price": "89.00",
                "extended_price": "89.00",
                "price_flagged": False,
            },
            {
                "line": 2,
                "item_number": "1511-1",
                "description": "Mobilent Monocular 4x12",
                "quantity": 1,
                "unit_price": "98.00",
                "expected_price": "134.00",
                "extended_price": "98.00",
                "price_flagged": True,
            },
            {
                "line": 3,
                "item_number": "2655-K",
                "description": "Smartlux Digital Handheld Video Magnifier",
                "quantity": 1,
                "unit_price": "140.00",
                "expected_price": "112.00",
                "extended_price": "140.00",
                "price_flagged": True,
            },
        ],
        "field_confidence": {
            "order_number": 0.82,
            "po_number": 0.0,
            "order_date": 0.95,
            "order_type": 0.94,
            "customer_no": 0.78,
            "customer_name": 0.93,
            "ship_to_name": 0.68,
            "ship_to_line1": 0.79,
            "ship_to_line2": 0.0,
            "ship_to_city": 0.88,
            "ship_to_state": 0.92,
            "ship_to_zip": 0.55,
            "terms": 0.0,
            "subtotal": 0.96,
            "tax": 0.88,
            "freight": 0.52,
            "total": 0.96,
        },
    },
}


STATUS_LABELS = {
    "extracted": "Extracted",
    "in_review": "In Review",
    "submitted": "Submitted",
    "error": "Error",
}


def _conf_band(score: float) -> str:
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
            "order_number": _field(detail["order_number"], fc["order_number"]),
            "po_number": _field(detail["po_number"], fc["po_number"]),
            "order_date": _field(detail["order_date"], fc["order_date"]),
            "order_type": _field(detail["order_type"], fc["order_type"]),
            "customer_no": _field(detail["customer_no"], fc["customer_no"]),
            "customer_name": _field(detail["customer_name"], fc["customer_name"]),
            "ship_to_name": _field(ship["name"], fc["ship_to_name"]),
            "ship_to_line1": _field(ship["line1"], fc["ship_to_line1"]),
            "ship_to_line2": _field(ship["line2"], fc["ship_to_line2"]),
            "ship_to_city": _field(ship["city"], fc["ship_to_city"]),
            "ship_to_state": _field(ship["state"], fc["ship_to_state"]),
            "ship_to_zip": _field(ship["zip"], fc["ship_to_zip"]),
            "terms": _field(detail["payment"]["terms"], fc["terms"]),
            "subtotal": _field(detail["totals"]["subtotal"], fc["subtotal"]),
            "tax": _field(detail["totals"]["tax"], fc["tax"]),
            "freight": _field(detail["totals"]["freight"], fc["freight"]),
            "total": _field(detail["totals"]["total"], fc["total"]),
        },
    }


@bp.get("/")
def index():
    orders = [
        {
            **row,
            "conf_band": _conf_band(row["overall_confidence"]),
            "status_label": STATUS_LABELS.get(row["status"], row["status"]),
            "status_class": row["status"].replace("_", "-"),
        }
        for row in SAMPLE_ORDERS
    ]
    return render_template("queue.html", orders=orders)


@bp.get("/orders/<int:order_id>")
def detail(order_id: int):
    detail = SAMPLE_ORDER_DETAILS.get(order_id) or SAMPLE_ORDER_DETAILS.get(1001)
    if detail is None:
        abort(404)
    return render_template("detail.html", order=_decorate_order(detail))


@bp.post("/orders/<int:order_id>")
def save(order_id: int):
    flash(f"Saved order {order_id} (mockup — no DB writes yet)")
    return redirect(url_for("queue.index"))
