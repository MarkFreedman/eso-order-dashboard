import csv
import json
import re

import psycopg

from vi_export_generator.field_layouts import HEADER_FIELDS


def test_va_detail_suppresses_price_flag(client, seed_orders):
    response = client.get("/orders/1001")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "VA Medical Center - Palo Alto" in body
    assert "Submit to Sage" in body
    assert "badge-price" not in body


def test_non_va_detail_shows_price_flag(client, seed_orders):
    response = client.get("/orders/1002")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Eyecare Associates of Tulsa" in body
    assert "badge-price" in body
    assert "**** 1024" in body
    assert "field-missing" in body


def test_save_redirects_and_flashes(client, seed_orders):
    response = client.post("/orders/1002", data={"action": "save"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Draft saved" in response.get_data(as_text=True)


def test_save_draft_succeeds_with_an_empty_comment(client, seed_orders):
    # The comment textarea has no `required` attribute: both Save Draft and
    # Submit to Sage post the same form, and enforcement is a server-side
    # Submit-path concern for a later task, not a browser-level block that
    # would also stop a plain draft save.
    response = client.post(
        "/orders/1002",
        data={"action": "save", "comment": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Draft saved" in response.get_data(as_text=True)


def test_detail_shows_order_source_select_with_stored_value_selected(client, seed_orders):
    response = client.get("/orders/1001")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '<select name="order_source">' in body
    assert '<option value="FAX" selected>' in body
    assert '<option value="EMAIL" >' in body


def test_detail_shows_comment_and_ship_via_fields(client, seed_orders):
    response = client.get("/orders/1001")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '<textarea name="comment"' in body
    assert 'name="ship_via"' in body
    assert "Required before Submit" in body


def test_save_persists_order_source_comment_and_ship_via(client, seed_orders, db_url):
    response = client.post(
        "/orders/1002",
        data={
            "action": "save",
            "comment": "Dr Smith/jp",
            "ship_via": "U",
            "order_source": "FAX",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT comment, ship_via, order_source FROM orders WHERE id = %s",
                (1002,),
            )
            row = cur.fetchone()
    assert row == ("Dr Smith/jp", "U", "FAX")


def test_submit_saves_edited_fields_before_generating_the_csv(
    client, seed_orders, tmp_path, monkeypatch
):
    # Submit used to build the CSV straight from the database, so an edit
    # the reviewer just typed (but never explicitly saved) was silently
    # dropped from the Sage file. Submit must save the draft first.
    monkeypatch.setenv("VI_OUTPUT_DIR", str(tmp_path))

    # The real form always posts every field (they are all rendered as
    # inputs), so a realistic post carries order 1001's existing values
    # along with the one edited field and the required comment.
    response = client.post(
        "/orders/1001",
        data={
            "action": "submit",
            "customer_no": "VA0042",
            "customer_name": "VA Medical Center - Palo Alto",
            "order_date": "2026-04-14",
            "po_number": "PO-998877",
            "order_type": "S",
            "order_source": "FAX",
            "ship_to_name": "EDITED SHIP TO NAME",
            "ship_to_line1": "3517 SAULS DR",
            "ship_to_line2": "",
            "ship_to_city": "AUSTIN",
            "ship_to_state": "TX",
            "ship_to_zip": "78728",
            "comment": "Reviewed, matches PO",
            "ship_via": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Submitted to Sage" in response.get_data(as_text=True)

    csv_path = tmp_path / "order_1001.csv"
    with csv_path.open(newline="") as f:
        header_row = next(csv.reader(f))
    ship_to_name = header_row[HEADER_FIELDS.index("ShipToName")]
    assert ship_to_name == "EDITED SHIP TO NAME"


def test_submit_with_an_empty_comment_is_rejected_and_stays_in_review(client, seed_orders, db_url):
    response = client.post(
        "/orders/1001",
        data={"action": "submit", "comment": "   "},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Comment is required before Submit to Sage" in response.get_data(as_text=True)

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, comment FROM orders WHERE id = %s", (1001,))
            status, comment = cur.fetchone()
    assert status == "in_review"
    assert comment == ""


def test_detail_customer_name_empty_does_not_render_missing_note(client, seed_orders):
    # Order 1004 has no customer_name (Sage fills it in from the customer
    # number on import), and several other genuinely-missing fields, so the
    # "not found" placeholder legitimately appears elsewhere on the page.
    # Scope the assertion to the customer_name field itself.
    response = client.get("/orders/1004")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    match = re.search(
        r'<label class="field[^"]*">\s*<span class="field-label">Customer Name</span>.*?</label>',
        body,
        re.S,
    )
    assert match is not None
    snippet = match.group(0)
    assert "field-missing" not in snippet
    assert "Not found in the document" not in snippet
    assert "Not in document" not in snippet


def test_skipped_order_detail_shows_reason_banner_and_no_submit_button(client, seed_orders):
    response = client.get("/orders/1005")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Skipped (custom order)" in body
    assert "Custom prescription eyeglass order" in body
    assert "Submit to Sage" not in body
    assert "Save Draft" not in body


def test_submit_is_refused_for_a_skipped_order(client, seed_orders, db_url):
    response = client.post(
        "/orders/1005",
        data={"action": "submit", "comment": "Reviewed"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "This order was skipped and cannot be submitted" in response.get_data(as_text=True)

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM orders WHERE id = %s", (1005,))
            (status,) = cur.fetchone()
    assert status == "skipped"


def test_card_mask_shows_last_four_without_inventing_a_brand(client, seed_orders, db_url):
    # Seed order 1002's source with credit_card_last4 stored as a plain
    # string (not the usual {"value": ...} wrapper) to also exercise the
    # tolerant unwrap: the mask must never invent a card brand like "VISA".
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET extraction_result = %s WHERE order_id = %s",
                (json.dumps({"credit_card_last4": "3359"}), 1002),
            )

    response = client.get("/orders/1002")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "**** 3359" in body
    assert "VISA" not in body
