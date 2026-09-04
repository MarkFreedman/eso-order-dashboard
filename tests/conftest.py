"""Shared pytest fixtures for the order-dashboard suite.

Tests run against a real Postgres database (the neondb_test database),
never SQLite and never the production neondb database. Set
TEST_DATABASE_URL before running the suite (built from the intake-service
.env by swapping the database name to neondb_test); any test that needs a
database is skipped, not failed, when it is unset.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
import pytest

import order_dashboard
from order_dashboard import create_app

# ---------------------------------------------------------------------------
# Basic auth test credentials
# ---------------------------------------------------------------------------

AUTH_USER = "tester"
AUTH_PASSWORD = "testpw"


def basic_auth_header(user: str = AUTH_USER, password: str = AUTH_PASSWORD) -> dict[str, str]:
    """Build a Basic auth header dict for the given credentials."""
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


AUTH = basic_auth_header()


# ---------------------------------------------------------------------------
# Hermetic environment
# ---------------------------------------------------------------------------
# create_app() loads ~/.config/order-dashboard/.env (dev convenience) with
# override=False, which means a developer's own local secrets can silently
# fill in SECRET_KEY/BASIC_AUTH_* for a test that meant to test their
# absence. Point that path at nothing for every test so results only ever
# depend on what a test explicitly sets.
@pytest.fixture(autouse=True)
def _no_local_dotenv(monkeypatch):
    monkeypatch.setattr(order_dashboard, "_USER_ENV", Path("/nonexistent/order-dashboard.env"))


# ---------------------------------------------------------------------------
# Postgres test database
# ---------------------------------------------------------------------------

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "intake-service" / "db" / "schema_pg.sql"
)


@pytest.fixture(scope="session")
def db_url() -> str:
    """URL of the neondb_test Postgres database used for tests.

    Never the production neondb database: tests that need a database are
    skipped (not failed) when TEST_DATABASE_URL is not set, and this fixture
    refuses to run against anything that isn't explicitly the _test database.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; skipping tests that need Postgres")
    if "/neondb_test" not in url:
        pytest.fail(
            "TEST_DATABASE_URL does not point at neondb_test; refusing to run "
            "tests against it (never run tests against neondb)"
        )
    return url


def ensure_schema(db_url: str) -> None:
    """Create the schema in the test database if the orders table is missing."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.orders')")
            (exists,) = cur.fetchone()
        if exists is None:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_PATH.read_text())


@pytest.fixture
def client(db_url, monkeypatch):
    """Flask test client wired to the Postgres test database.

    Sends the basic auth header (tester/testpw) on every request by
    default, and disables CSRF so tests can post plain form data without
    fetching a token first.
    """
    ensure_schema(db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BASIC_AUTH_USER", AUTH_USER)
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", AUTH_PASSWORD)

    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    test_client = app.test_client()
    test_client.environ_base["HTTP_AUTHORIZATION"] = AUTH["Authorization"]
    return test_client


# ---------------------------------------------------------------------------
# Seeded orders
# ---------------------------------------------------------------------------

_INSERT_ORDER_SQL = """
    INSERT INTO orders (
        id, customer_no, customer_name,
        ship_to_name, ship_to_address1, ship_to_address2,
        ship_to_city, ship_to_state, ship_to_zip,
        order_date, po_number, order_source, order_type, deposit_payment_type,
        status, overall_confidence, field_confidence, needs_review_reason,
        reviewed_by, reviewed_at, submitted_at
    ) OVERRIDING SYSTEM VALUE VALUES (
        %(id)s, %(customer_no)s, %(customer_name)s,
        %(ship_to_name)s, %(ship_to_address1)s, %(ship_to_address2)s,
        %(ship_to_city)s, %(ship_to_state)s, %(ship_to_zip)s,
        %(order_date)s, %(po_number)s, %(order_source)s, %(order_type)s, %(deposit_payment_type)s,
        %(status)s, %(overall_confidence)s, %(field_confidence)s, %(needs_review_reason)s,
        %(reviewed_by)s, %(reviewed_at)s, %(submitted_at)s
    )
"""


@pytest.fixture
def seed_orders(client, db_url) -> dict[str, Any]:
    """Truncate orders/line_items/sources and insert a small, realistic set.

    - 1001: VA order, extracted, two clean line items and one source.
    - 1002: non-VA order, extracted, one line item flagged for a price
      mismatch, one source with a credit card last 4 (so the masked card
      renders), and a blank ship-to line 2 (so a "not in document" field
      renders).
    - 1003: submitted yesterday.
    - 1004: needs-review order (no order number found yet) so the queue's
      "Needs Review" badge has something to show.
    """
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE orders, line_items, sources RESTART IDENTITY CASCADE")
            cur.execute(
                "UPDATE email_watermark SET last_message_id = NULL, last_received_at = NULL, "
                "last_poll_at = NULL, messages_processed = 0 WHERE id = 1"
            )

            # Order 1001: VA fax order, extracted, two clean line items.
            cur.execute(
                _INSERT_ORDER_SQL,
                {
                    "id": 1001,
                    "customer_no": "VA0042",
                    "customer_name": "VA Medical Center - Palo Alto",
                    "ship_to_name": "VETERAN - JAMES R CALDWELL",
                    "ship_to_address1": "3517 SAULS DR",
                    "ship_to_address2": "",
                    "ship_to_city": "AUSTIN",
                    "ship_to_state": "TX",
                    "ship_to_zip": "78728",
                    "order_date": "2026-04-14",
                    "po_number": "PO-998877",
                    "order_source": "FAX",
                    "order_type": "S",
                    "deposit_payment_type": "Check",
                    "status": "extracted",
                    "overall_confidence": 0.93,
                    "field_confidence": json.dumps(
                        {
                            "customer_no": 0.9,
                            "customer_po": 1.0,
                            "order_date": 1.0,
                            "ship_to": 0.9,
                            "payment_type": 1.0,
                        }
                    ),
                    "needs_review_reason": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "submitted_at": None,
                },
            )
            # Plain execute() per row rather than executemany(): psycopg3's
            # executemany() runs under an implicit pipeline, where an error
            # partway through can roll back rows that already looked
            # inserted, which is worth avoiding for test fixtures.
            for row in [
                (1001, 1, "1602-04", "HALOGEN LAMP ESCHENBACH 1602-04", 1, 145.30, 0),
                (1001, 2, "2652-04", "VISOLUX DIGITAL HD POCKET MAGNIFIER", 2, 229.00, 0),
            ]:
                cur.execute(
                    "INSERT INTO line_items (order_id, line_number, item_code, "
                    "item_description, quantity_ordered, unit_price, price_flagged) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    row,
                )
            cur.execute(
                "INSERT INTO sources (order_id, source_type, original_filename, content_type, "
                "gdrive_path, gdrive_filename, extraction_status, extracted_order_no, "
                "extraction_confidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    1001,
                    "attachment",
                    "PO-998877.pdf",
                    "application/pdf",
                    "samples/va-sample.pdf",
                    "va-sample.pdf",
                    "extracted",
                    "PO-998877",
                    0.93,
                ),
            )

            # Order 1002: non-VA order, extracted, one price-flagged line,
            # a credit card payment, blank ship-to line 2.
            cur.execute(
                _INSERT_ORDER_SQL,
                {
                    "id": 1002,
                    "customer_no": "EYE0118",
                    "customer_name": "Eyecare Associates of Tulsa",
                    "ship_to_name": "EYECARE ASSOCIATES OF TULSA",
                    "ship_to_address1": "4444 S HARVARD AVE",
                    "ship_to_address2": "",
                    "ship_to_city": "TULSA",
                    "ship_to_state": "OK",
                    "ship_to_zip": "74135",
                    "order_date": "2026-04-11",
                    "po_number": "TUL-88241",
                    "order_source": "FAX",
                    "order_type": "S",
                    "deposit_payment_type": "Credit Card",
                    "status": "extracted",
                    "overall_confidence": 0.72,
                    "field_confidence": json.dumps(
                        {
                            "customer_no": 0.75,
                            "customer_po": 1.0,
                            "order_date": 0.75,
                            "ship_to": 0.75,
                            "payment_type": 1.0,
                        }
                    ),
                    "needs_review_reason": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "submitted_at": None,
                },
            )
            cur.execute(
                "INSERT INTO line_items (order_id, line_number, item_code, item_description, "
                "quantity_ordered, unit_price, price_flagged, price_flag_reason) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    1002,
                    1,
                    "1661-3",
                    "MAXI PLUS 3x Hand Magnifier",
                    1,
                    99.00,
                    1,
                    "Extracted price differs from expected price level",
                ),
            )
            cur.execute(
                "INSERT INTO sources (order_id, source_type, original_filename, content_type, "
                "gdrive_path, gdrive_filename, extraction_status, extracted_order_no, "
                "extraction_confidence, extraction_result) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    1002,
                    "attachment",
                    "TUL-88241.pdf",
                    "application/pdf",
                    "samples/mi413-sample.pdf",
                    "mi413-sample.pdf",
                    "extracted",
                    "TUL-88241",
                    0.72,
                    json.dumps({"credit_card_last4": {"value": "1024", "confidence": "HIGH"}}),
                ),
            )

            # Order 1003: submitted yesterday.
            cur.execute(
                _INSERT_ORDER_SQL,
                {
                    "id": 1003,
                    "customer_no": "CA201",
                    "customer_name": "California Dept of Rehabilitation",
                    "ship_to_name": "JOHN M TREVINO",
                    "ship_to_address1": "1515 S ST",
                    "ship_to_address2": "",
                    "ship_to_city": "SACRAMENTO",
                    "ship_to_state": "CA",
                    "ship_to_zip": "95811",
                    "order_date": "2026-04-13",
                    "po_number": "623-Q69123",
                    "order_source": "FAX",
                    "order_type": "S",
                    "deposit_payment_type": "Check",
                    "status": "submitted",
                    "overall_confidence": 0.88,
                    "field_confidence": json.dumps(
                        {
                            "customer_no": 0.9,
                            "customer_po": 1.0,
                            "order_date": 0.9,
                            "ship_to": 0.75,
                            "payment_type": 1.0,
                        }
                    ),
                    "needs_review_reason": None,
                    "reviewed_by": "Lauren Brennan",
                    "reviewed_at": yesterday,
                    "submitted_at": yesterday,
                },
            )
            cur.execute(
                "INSERT INTO line_items (order_id, line_number, item_code, item_description, "
                "quantity_ordered, unit_price, price_flagged) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (1003, 1, "2652-04", "VISOLUX DIGITAL HD POCKET MAGNIFIER", 1, 229.00, 0),
            )

            # Order 1004: needs-review (no order number found yet).
            cur.execute(
                _INSERT_ORDER_SQL,
                {
                    "id": 1004,
                    "customer_no": None,
                    "customer_name": None,
                    "ship_to_name": None,
                    "ship_to_address1": None,
                    "ship_to_address2": None,
                    "ship_to_city": None,
                    "ship_to_state": None,
                    "ship_to_zip": None,
                    "order_date": None,
                    "po_number": None,
                    "order_source": "EMAIL",
                    "order_type": "S",
                    "deposit_payment_type": "Check",
                    "status": "extracted",
                    "overall_confidence": 0.22,
                    "field_confidence": json.dumps(
                        {
                            "customer_no": 0.0,
                            "customer_po": 0.0,
                            "order_date": 0.5,
                            "ship_to": 0.0,
                            "payment_type": 1.0,
                        }
                    ),
                    "needs_review_reason": "No order number found - document may be a cover sheet only",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "submitted_at": None,
                },
            )

    return {
        "va_order_id": 1001,
        "flagged_order_id": 1002,
        "submitted_order_id": 1003,
        "needs_review_order_id": 1004,
    }
