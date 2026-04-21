"""Seed the staging database with mock orders for demo purposes.

Run on Fly.io:
    fly ssh console -C "python /app/seed.py"
"""

import json
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("STAGING_DB_PATH", "/data/staging.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")

# Wipe existing data so seed is idempotent
conn.executescript("""
    DELETE FROM sources;
    DELETE FROM line_items;
    DELETE FROM orders;
""")

# ---------------------------------------------------------------------------
# Order 1: VA fax order — extracted, high confidence, needs no changes
# ---------------------------------------------------------------------------
cur = conn.execute("""
    INSERT INTO orders (
        customer_no, customer_name,
        ship_to_name, ship_to_address1, ship_to_city, ship_to_state, ship_to_zip,
        order_date, po_number, order_source, order_type, deposit_payment_type,
        status, overall_confidence, field_confidence,
        email_message_id, email_received_at, email_subject, email_sender
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (
    "TX365-T", "DEPT OF VETERANS AFFAIRS",
    "VETERAN - JAMES R CALDWELL", "3517 SAULS DR", "AUSTIN", "TX", "78728",
    "2026-04-14", "674-6Q8041", "FAX", "S", "Credit Card",
    "extracted", 0.93,
    json.dumps({"customer_no": 0.9, "customer_po": 1.0, "order_date": 1.0, "ship_to": 0.9, "payment_type": 1.0}),
    "<msg-001@vonage.com>", "2026-04-14T09:12:00Z",
    "Fax from +15127771234 — VA Purchase Order", "fax@vonagenetworks.com",
))
order1_id = cur.lastrowid

conn.execute("""
    INSERT INTO line_items (order_id, line_number, item_code, item_description, quantity_ordered, unit_price)
    VALUES (?,?,?,?,?,?)
""", (order1_id, 1, "1602-04", "HALOGEN LAMP ESCHENBACH 1602-04", 1, 145.30))
conn.execute("""
    INSERT INTO line_items (order_id, line_number, item_code, item_description, quantity_ordered, unit_price)
    VALUES (?,?,?,?,?,?)
""", (order1_id, 2, "2652-04", "VISOLUX DIGITAL HD POCKET MAGNIFIER", 2, 229.00))

conn.execute("""
    INSERT INTO sources (order_id, source_type, original_filename, content_type,
        gdrive_path, gdrive_filename, extraction_status, extracted_order_no, extraction_confidence)
    VALUES (?,?,?,?,?,?,?,?,?)
""", (order1_id, "attachment", "674-6Q8041.pdf", "application/pdf",
      "samples/va-sample.pdf", "va-sample.pdf", "extracted", "674-6Q8041", 0.93))

# ---------------------------------------------------------------------------
# Order 2: Email order — extracted, medium confidence, needs review
# ---------------------------------------------------------------------------
cur = conn.execute("""
    INSERT INTO orders (
        customer_no, customer_name,
        ship_to_name, ship_to_address1, ship_to_city, ship_to_state, ship_to_zip,
        order_date, po_number, order_source, order_type, deposit_payment_type,
        status, overall_confidence, field_confidence, needs_review_reason,
        email_message_id, email_received_at, email_subject, email_sender
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (
    "MI413", "MICHIGAN COMMISSION FOR THE BLIND",
    "STATE OF MICHIGAN", "201 N WASHINGTON SQ", "LANSING", "MI", "48913",
    "2026-04-15", "PO-2026-0044", "EMAIL", "S", "Check",
    "extracted", 0.71,
    json.dumps({"customer_no": 0.75, "customer_po": 1.0, "order_date": 0.5, "ship_to": 0.75, "payment_type": 1.0}),
    "Order date unclear — extracted from email body, not document header",
    "<msg-002@mail.michigan.gov>", "2026-04-15T13:44:00Z",
    "Purchase Order PO-2026-0044", "purchasing@mcb.michigan.gov",
))
order2_id = cur.lastrowid

conn.execute("""
    INSERT INTO line_items (order_id, line_number, item_code, item_description, quantity_ordered, unit_price)
    VALUES (?,?,?,?,?,?)
""", (order2_id, 1, "3135", "ESCHENBACH MOBILUX LED 4X ILLUMINATED MAGNIFIER", 3, 89.50))
conn.execute("""
    INSERT INTO line_items (order_id, line_number, item_code, item_description, quantity_ordered, unit_price)
    VALUES (?,?,?,?,?,?)
""", (order2_id, 2, "1664-4", "SCALE LOUPE WITH LED 10X", 1, 67.00))
conn.execute("""
    INSERT INTO line_items (order_id, line_number, item_code, item_description, quantity_ordered, unit_price)
    VALUES (?,?,?,?,?,?)
""", (order2_id, 3, "2902-04", "FIDELIO CLIP-ON MAGNIFIER", 2, 112.00))

conn.execute("""
    INSERT INTO sources (order_id, source_type, original_filename, content_type,
        gdrive_path, gdrive_filename, extraction_status, extracted_order_no, extraction_confidence)
    VALUES (?,?,?,?,?,?,?,?,?)
""", (order2_id, "attachment", "PO-2026-0044.pdf", "application/pdf",
      "samples/mi413-sample.pdf", "mi413-sample.pdf", "extracted", "PO-2026-0044", 0.71))

# ---------------------------------------------------------------------------
# Order 3: In-review fax order
# ---------------------------------------------------------------------------
cur = conn.execute("""
    INSERT INTO orders (
        customer_no, customer_name,
        ship_to_name, ship_to_address1, ship_to_city, ship_to_state, ship_to_zip,
        order_date, po_number, order_source, order_type, deposit_payment_type,
        status, overall_confidence, field_confidence, reviewed_by, reviewed_at,
        email_message_id, email_received_at, email_subject, email_sender
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (
    "CA201", "CALIFORNIA DEPT OF REHABILITATION",
    "JOHN M TREVINO", "1515 S ST", "SACRAMENTO", "CA", "95811",
    "2026-04-13", "623-Q69123", "FAX", "S", "Check",
    "in_review", 0.88,
    json.dumps({"customer_no": 0.9, "customer_po": 1.0, "order_date": 0.9, "ship_to": 0.75, "payment_type": 1.0}),
    "Lauren Brennan", "2026-04-15T16:20:00Z",
    "<msg-003@vonage.com>", "2026-04-13T08:55:00Z",
    "Fax from +19165550198 — State Agency PO", "fax@vonagenetworks.com",
))
order3_id = cur.lastrowid

conn.execute("""
    INSERT INTO line_items (order_id, line_number, item_code, item_description, quantity_ordered, unit_price)
    VALUES (?,?,?,?,?,?)
""", (order3_id, 1, "2652-04", "VISOLUX DIGITAL HD POCKET MAGNIFIER", 1, 229.00))

conn.execute("""
    INSERT INTO sources (order_id, source_type, original_filename, content_type,
        gdrive_path, gdrive_filename, extraction_status, extracted_order_no, extraction_confidence)
    VALUES (?,?,?,?,?,?,?,?,?)
""", (order3_id, "attachment", "623-Q69123.pdf", "application/pdf",
      "samples/va-sample.pdf", "va-sample.pdf", "extracted", "623-Q69123", 0.88))

# ---------------------------------------------------------------------------
# Order 4: Needs-review — no order number found
# ---------------------------------------------------------------------------
cur = conn.execute("""
    INSERT INTO orders (
        order_source, deposit_payment_type,
        status, overall_confidence, field_confidence, needs_review_reason,
        email_message_id, email_received_at, email_subject, email_sender
    ) VALUES (?,?,?,?,?,?,?,?,?,?)
""", (
    "EMAIL", "Check",
    "extracted", 0.22,
    json.dumps({"customer_no": 0.0, "customer_po": 0.0, "order_date": 0.5, "ship_to": 0.0, "payment_type": 1.0}),
    "No order number found — document may be a cover sheet only",
    "<msg-004@gmail.com>", "2026-04-16T11:03:00Z",
    "Order attached", "purchasing.dept@visioncare-partners.com",
))
order4_id = cur.lastrowid

conn.execute("""
    INSERT INTO sources (order_id, source_type, original_filename, content_type,
        gdrive_path, gdrive_filename, extraction_status, extracted_order_no,
        extraction_confidence, is_placeholder, placeholder_name)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)
""", (order4_id, "attachment", "order-doc.pdf", "application/pdf",
      "samples/mi413-sample.pdf", "needs-review-20260416T110312.pdf",
      "extracted", None, 0.22, 1, "needs-review-20260416T110312.pdf"))

# ---------------------------------------------------------------------------
# Order 5: Submitted
# ---------------------------------------------------------------------------
cur = conn.execute("""
    INSERT INTO orders (
        customer_no, customer_name,
        ship_to_name, ship_to_address1, ship_to_city, ship_to_state, ship_to_zip,
        order_date, po_number, order_source, order_type, deposit_payment_type,
        status, overall_confidence, field_confidence,
        reviewed_by, reviewed_at, submitted_at, vi_file_path,
        email_message_id, email_received_at, email_subject, email_sender
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", (
    "TX365-T", "DEPT OF VETERANS AFFAIRS",
    "VETERAN - DOROTHY A SIMMONS", "8820 BURNET RD APT 214", "AUSTIN", "TX", "78757",
    "2026-04-10", "642-Q6G055", "FAX", "S", "Credit Card",
    "submitted", 0.97,
    json.dumps({"customer_no": 1.0, "customer_po": 1.0, "order_date": 1.0, "ship_to": 1.0, "payment_type": 1.0}),
    "Lauren Brennan", "2026-04-10T14:10:00Z",
    "2026-04-10T14:12:00Z", "/data/vi-output/order_5.csv",
    "<msg-005@vonage.com>", "2026-04-10T10:22:00Z",
    "Fax from +15127771234 — VA Purchase Order", "fax@vonagenetworks.com",
))
order5_id = cur.lastrowid

conn.execute("""
    INSERT INTO line_items (order_id, line_number, item_code, item_description, quantity_ordered, unit_price)
    VALUES (?,?,?,?,?,?)
""", (order5_id, 1, "1602-04", "HALOGEN LAMP ESCHENBACH 1602-04", 2, 145.30))

conn.execute("""
    INSERT INTO sources (order_id, source_type, original_filename, content_type,
        gdrive_path, gdrive_filename, extraction_status, extracted_order_no, extraction_confidence)
    VALUES (?,?,?,?,?,?,?,?,?)
""", (order5_id, "attachment", "642-Q6G055.pdf", "application/pdf",
      "samples/va-sample.pdf", "va-sample.pdf", "extracted", "642-Q6G055", 0.97))

conn.commit()
conn.close()

print("Seeded 5 mock orders (1 extracted VA, 1 extracted medium-confidence, 1 in-review, 1 needs-review, 1 submitted)")
