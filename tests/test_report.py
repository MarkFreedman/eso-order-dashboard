"""Tests for the daily order-count report (/report)."""

import psycopg
import pytest

_INSERT_ORDER_SQL = """
    INSERT INTO orders (
        id, customer_no, customer_name, order_source,
        order_date, po_number, status, submitted_at, reviewed_by
    ) OVERRIDING SYSTEM VALUE VALUES (
        %(id)s, %(customer_no)s, %(customer_name)s, %(order_source)s,
        %(order_date)s, %(po_number)s, %(status)s, %(submitted_at)s, %(reviewed_by)s
    )
"""


def _seed(db_url):
    """Three submitted orders (two on 2026-05-14, one on 2026-05-12) plus one
    still-extracted order that the report must exclude."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE orders, line_items, sources RESTART IDENTITY CASCADE")
            # Plain execute() per row rather than executemany(): psycopg3's
            # executemany() runs under an implicit pipeline, where an error
            # partway through can roll back rows that already looked
            # inserted, which is worth avoiding for test fixtures.
            for row in [
                    {
                        "id": 1,
                        "customer_no": "TX365-T",
                        "customer_name": "Dept of Veterans Affairs",
                        "order_source": "FAX",
                        "order_date": "2026-05-13",
                        "po_number": "PO-AAA",
                        "status": "submitted",
                        "submitted_at": "2026-05-14T09:15:00Z",
                        "reviewed_by": "Lauren",
                    },
                    {
                        "id": 2,
                        "customer_no": "MI413",
                        "customer_name": "Michigan Commission for the Blind",
                        "order_source": "EMAIL",
                        "order_date": "2026-05-13",
                        "po_number": "PO-BBB",
                        "status": "submitted",
                        "submitted_at": "2026-05-14T14:40:00Z",
                        "reviewed_by": "Dana",
                    },
                    {
                        "id": 3,
                        "customer_no": "CA201",
                        "customer_name": "California Dept of Rehabilitation",
                        "order_source": "FAX",
                        "order_date": "2026-05-11",
                        "po_number": "PO-CCC",
                        "status": "submitted",
                        "submitted_at": "2026-05-12T11:00:00Z",
                        "reviewed_by": "Lauren",
                    },
                    {
                        "id": 4,
                        "customer_no": "NY100",
                        "customer_name": "New York State Agency",
                        "order_source": "EMAIL",
                        "order_date": "2026-05-13",
                        "po_number": "PO-DDD",
                        "status": "extracted",
                        "submitted_at": None,
                        "reviewed_by": None,
                    },
                ]:
                cur.execute(_INSERT_ORDER_SQL, row)
            for row in [
                (1, 1, "X1", 1, 10.0),
                (1, 2, "X2", 2, 5.0),
                (2, 1, "Y1", 1, 9.0),
            ]:
                cur.execute(
                    "INSERT INTO line_items (order_id, line_number, item_code, "
                    "quantity_ordered, unit_price) VALUES (%s,%s,%s,%s,%s)",
                    row,
                )


@pytest.fixture
def report_seed(client, db_url):
    _seed(db_url)


def test_report_counts_submitted_orders_by_day(client, report_seed):
    resp = client.get("/report?start=2026-05-01&end=2026-05-31")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    assert "Order Report" in body
    assert "orders submitted" in body
    # 2026-05-14 has two orders, 2026-05-12 has one.
    assert "2 orders" in body
    assert "1 order" in body
    assert "May 14, 2026" in body
    # Submitted orders are listed; the still-extracted order is not.
    assert "PO-AAA" in body
    assert "PO-BBB" in body
    assert "PO-CCC" in body
    assert "PO-DDD" not in body


def test_report_date_filter_excludes_out_of_range(client, report_seed):
    resp = client.get("/report?start=2026-05-13&end=2026-05-31")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # Order submitted 2026-05-12 falls outside the range.
    assert "PO-CCC" not in body
    assert "PO-AAA" in body
    assert "2 orders" in body


def test_report_empty_range_shows_message(client, report_seed):
    resp = client.get("/report?start=2026-01-01&end=2026-01-31")
    assert resp.status_code == 200
    assert "No orders were submitted" in resp.get_data(as_text=True)


def test_report_default_range_renders(client, report_seed):
    resp = client.get("/report")
    assert resp.status_code == 200
    assert "Order Report" in resp.get_data(as_text=True)


def test_report_swaps_reversed_dates(client, report_seed):
    # start later than end should be treated as a valid (swapped) range.
    resp = client.get("/report?start=2026-05-31&end=2026-05-01")
    assert resp.status_code == 200
    assert "PO-AAA" in resp.get_data(as_text=True)
