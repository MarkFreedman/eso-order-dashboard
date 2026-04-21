"""Database connection for the staging SQLite DB.

The DB is owned by the intake-service. This app connects read/write
for order review, field edits, and status updates.

On first connect, auto-initializes the schema if the orders table does
not yet exist (e.g., fresh Fly volume on first deploy).
"""

import os
import sqlite3
from pathlib import Path

from flask import Flask, g

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_no         TEXT,
    customer_name       TEXT,
    bill_to_name        TEXT,
    bill_to_address1    TEXT,
    bill_to_address2    TEXT,
    bill_to_city        TEXT,
    bill_to_state       TEXT,
    bill_to_zip         TEXT,
    ship_to_name        TEXT,
    ship_to_address1    TEXT,
    ship_to_address2    TEXT,
    ship_to_city        TEXT,
    ship_to_state       TEXT,
    ship_to_zip         TEXT,
    order_date          TEXT,
    po_number           TEXT,
    order_source        TEXT CHECK (order_source IN ('FAX', 'EMAIL')),
    order_type          TEXT DEFAULT 'S' CHECK (order_type IN ('S', 'Q')),
    deposit_payment_type TEXT DEFAULT 'Check' CHECK (deposit_payment_type IN ('Check', 'Credit Card')),
    status              TEXT NOT NULL DEFAULT 'extracted'
                        CHECK (status IN ('extracted', 'in_review', 'submitted', 'error')),
    error_message       TEXT,
    sage_order_no       TEXT,
    vi_file_path        TEXT,
    overall_confidence  REAL,
    field_confidence    TEXT,
    needs_review_reason TEXT,
    reviewed_by         TEXT,
    reviewed_at         TEXT,
    email_message_id    TEXT,
    email_received_at   TEXT,
    email_subject       TEXT,
    email_sender        TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    submitted_at        TEXT
);

CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_email_message_id ON orders(email_message_id);
CREATE INDEX idx_orders_created_at ON orders(created_at);

CREATE TABLE line_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    line_number         INTEGER NOT NULL,
    item_code           TEXT,
    item_description    TEXT,
    quantity_ordered    REAL,
    unit_price          REAL,
    unit_of_measure     TEXT,
    price_level         TEXT,
    comment_text        TEXT,
    field_confidence    TEXT,
    price_flagged       INTEGER NOT NULL DEFAULT 0,
    price_flag_reason   TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_line_items_order_id ON line_items(order_id);

CREATE TABLE sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id            INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    source_type         TEXT NOT NULL CHECK (source_type IN ('attachment', 'email_body')),
    original_filename   TEXT,
    content_type        TEXT,
    gdrive_path         TEXT,
    gdrive_filename     TEXT,
    extraction_status   TEXT NOT NULL DEFAULT 'pending'
                        CHECK (extraction_status IN ('pending', 'extracted', 'no_order_data', 'error')),
    extracted_order_no  TEXT,
    extraction_confidence REAL,
    extraction_result   TEXT,
    extraction_error    TEXT,
    is_placeholder      INTEGER NOT NULL DEFAULT 0,
    placeholder_name    TEXT,
    email_message_id    TEXT,
    email_received_at   TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_sources_order_id ON sources(order_id);
CREATE INDEX idx_sources_extraction_status ON sources(extraction_status);
CREATE INDEX idx_sources_email_message_id ON sources(email_message_id);

CREATE TABLE email_watermark (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    last_message_id         TEXT,
    last_received_at        TEXT,
    last_poll_at            TEXT,
    messages_processed      INTEGER NOT NULL DEFAULT 0,
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO email_watermark (id) VALUES (1);

CREATE TRIGGER trg_orders_updated_at AFTER UPDATE ON orders
BEGIN
    UPDATE orders SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_line_items_updated_at AFTER UPDATE ON line_items
BEGIN
    UPDATE line_items SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_sources_updated_at AFTER UPDATE ON sources
BEGIN
    UPDATE sources SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER trg_email_watermark_updated_at AFTER UPDATE ON email_watermark
BEGIN
    UPDATE email_watermark SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = os.environ.get(
            "STAGING_DB_PATH",
            os.path.join(os.path.dirname(__file__), "../../intake-service/staging.db"),
        )
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(Path(db_path).expanduser()))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        _ensure_schema(g.db)
    return g.db


def _ensure_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
    ).fetchone()
    if row is None:
        conn.executescript(_SCHEMA)


def init_app(app: Flask) -> None:
    app.teardown_appcontext(_close_db)


def _close_db(exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
