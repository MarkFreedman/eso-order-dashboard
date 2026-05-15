"""Tests for the daily order-count report (/report)."""

import base64

import pytest

from order_dashboard import create_app, db

AUTH = {"Authorization": "Basic " + base64.b64encode(b"tester:testpw").decode()}


def _seed(conn):
    """Three submitted orders (two on 2026-05-14, one on 2026-05-12) plus one
    still-extracted order that the report must exclude."""
    conn.executescript(
        """
        INSERT INTO orders (id, customer_no, customer_name, order_source,
            order_date, po_number, status, submitted_at, reviewed_by)
        VALUES
          (1, 'TX365-T', 'Dept of Veterans Affairs', 'FAX',
           '2026-05-13', 'PO-AAA', 'submitted', '2026-05-14T09:15:00Z', 'Lauren'),
          (2, 'MI413', 'Michigan Commission for the Blind', 'EMAIL',
           '2026-05-13', 'PO-BBB', 'submitted', '2026-05-14T14:40:00Z', 'Dana'),
          (3, 'CA201', 'California Dept of Rehabilitation', 'FAX',
           '2026-05-11', 'PO-CCC', 'submitted', '2026-05-12T11:00:00Z', 'Lauren'),
          (4, 'NY100', 'New York State Agency', 'EMAIL',
           '2026-05-13', 'PO-DDD', 'extracted', NULL, NULL);

        INSERT INTO line_items (order_id, line_number, item_code, quantity_ordered, unit_price)
        VALUES (1, 1, 'X1', 1, 10.0), (1, 2, 'X2', 2, 5.0), (2, 1, 'Y1', 1, 9.0);
        """
    )
    conn.commit()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGING_DB_PATH", str(tmp_path / "staging.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BASIC_AUTH_USER", "tester")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "testpw")

    app = create_app()
    with app.app_context():
        _seed(db.get_db())  # get_db() auto-creates the schema on a fresh file
    return app.test_client()


def test_report_counts_submitted_orders_by_day(client):
    resp = client.get("/report?start=2026-05-01&end=2026-05-31", headers=AUTH)
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


def test_report_date_filter_excludes_out_of_range(client):
    resp = client.get("/report?start=2026-05-13&end=2026-05-31", headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # Order submitted 2026-05-12 falls outside the range.
    assert "PO-CCC" not in body
    assert "PO-AAA" in body
    assert "2 orders" in body


def test_report_empty_range_shows_message(client):
    resp = client.get("/report?start=2026-01-01&end=2026-01-31", headers=AUTH)
    assert resp.status_code == 200
    assert "No orders were submitted" in resp.get_data(as_text=True)


def test_report_default_range_renders(client):
    resp = client.get("/report", headers=AUTH)
    assert resp.status_code == 200
    assert "Order Report" in resp.get_data(as_text=True)


def test_report_swaps_reversed_dates(client):
    # start later than end should be treated as a valid (swapped) range.
    resp = client.get("/report?start=2026-05-31&end=2026-05-01", headers=AUTH)
    assert resp.status_code == 200
    assert "PO-AAA" in resp.get_data(as_text=True)
