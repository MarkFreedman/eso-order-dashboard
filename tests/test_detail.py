import csv
import json
import re

import psycopg
import pytest
from psycopg.rows import dict_row

from order_dashboard import mapping
from vi_export_generator.field_layouts import HEADER_FIELDS


def test_va_detail_suppresses_price_flag(client, seed_orders):
    response = client.get("/orders/1001")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "VA Sample Clinic - Riverview" in body
    assert "Submit to Sage" in body
    assert "badge-price" not in body


def test_non_va_detail_shows_price_flag(client, seed_orders):
    response = client.get("/orders/1002")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Riverview Low Vision Clinic" in body
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


def test_detail_shows_ship_via_select_with_18_options_and_stored_value_selected(
    client, seed_orders, db_url
):
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE orders SET ship_via = %s WHERE id = %s", ("U", 1001))

    response = client.get("/orders/1001")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    match = re.search(
        r'<select name="ship_via">(.*?)</select>', body, re.S
    )
    assert match is not None
    select_body = match.group(1)
    assert select_body.count("<option") == 18
    assert '<option value="U" selected>U: UPS Ground</option>' in select_body
    assert '<option value="M" >M: Mail</option>' in select_body


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


def test_save_persists_a_valid_ship_via_code(client, seed_orders, db_url):
    response = client.post(
        "/orders/1002",
        data={"action": "save", "ship_via": "P"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ship_via FROM orders WHERE id = %s", (1002,))
            (ship_via,) = cur.fetchone()
    assert ship_via == "P"


def test_save_ignores_a_ship_via_code_not_on_sages_list(client, seed_orders, db_url):
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE orders SET ship_via = %s WHERE id = %s", ("U", 1002))

    response = client.post(
        "/orders/1002",
        data={"action": "save", "ship_via": "BOGUS"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ship_via FROM orders WHERE id = %s", (1002,))
            (ship_via,) = cur.fetchone()
    assert ship_via == "U"


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
            "customer_name": "VA Sample Clinic - Riverview",
            "order_date": "2026-04-14",
            "po_number": "PO-998877",
            "order_type": "S",
            "order_source": "FAX",
            "ship_to_name": "EDITED SHIP TO NAME",
            "ship_to_line1": "100 EXAMPLE WAY",
            "ship_to_line2": "",
            "ship_to_city": "RIVERVIEW",
            "ship_to_state": "TX",
            "ship_to_zip": "99001",
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


def test_submit_carries_comment_and_ship_via_into_the_csv(
    client, seed_orders, tmp_path, monkeypatch
):
    # Comment and Ship Via are reviewer-entered fields with no source in the
    # extracted order data, so they only reach Sage if the submit path wires
    # them into the generator's order dict.
    monkeypatch.setenv("VI_OUTPUT_DIR", str(tmp_path))

    response = client.post(
        "/orders/1001",
        data={
            "action": "submit",
            "customer_no": "VA0042",
            "customer_name": "VA Sample Clinic - Riverview",
            "order_date": "2026-04-14",
            "po_number": "PO-998877",
            "order_type": "S",
            "order_source": "FAX",
            "ship_to_name": "VA Sample Clinic - Riverview",
            "ship_to_line1": "100 Example Way",
            "ship_to_line2": "",
            "ship_to_city": "Riverview",
            "ship_to_state": "TX",
            "ship_to_zip": "99001",
            "comment": "Dr Smith/jp",
            "ship_via": "U",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Submitted to Sage" in response.get_data(as_text=True)

    csv_path = tmp_path / "order_1001.csv"
    with csv_path.open(newline="") as f:
        header_row = next(csv.reader(f))
    assert header_row[HEADER_FIELDS.index("Comment")] == "Dr Smith/jp"
    assert header_row[HEADER_FIELDS.index("ShipVia")] == "U"


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


@pytest.mark.parametrize(
    "stored_last4",
    ["3359", None],
    ids=["plain-string", "json-null"],
)
def test_submit_tolerates_a_plain_or_null_credit_card_last4(
    client, seed_orders, db_url, tmp_path, monkeypatch, stored_last4
):
    # detail_to_vi() used to reach straight into a {"value": ...} wrapper,
    # so an extraction result holding a plain string (or a JSON null) blew
    # up the submit path with an AttributeError. Both shapes must submit.
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET extraction_result = %s WHERE order_id = %s",
                (json.dumps({"credit_card_last4": stored_last4}), 1002),
            )

    monkeypatch.setenv("VI_OUTPUT_DIR", str(tmp_path))
    response = client.post(
        "/orders/1002",
        data={
            "action": "submit",
            "customer_no": "EYE0118",
            "customer_name": "Riverview Low Vision Clinic",
            "order_date": "2026-04-11",
            "po_number": "TUL-88241",
            "order_type": "S",
            "order_source": "FAX",
            "ship_to_name": "RIVERVIEW LOW VISION CLINIC",
            "ship_to_line1": "200 EXAMPLE WAY",
            "ship_to_line2": "",
            "ship_to_city": "RIVERVIEW",
            "ship_to_state": "OK",
            "ship_to_zip": "99002",
            "comment": "Reviewed/mf",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Submitted to Sage" in response.get_data(as_text=True)
    assert (tmp_path / "order_1002.csv").is_file()


def test_save_clears_ship_via_when_an_empty_value_is_posted(client, seed_orders, db_url):
    # Ship Via is optional, so the reviewer must be able to take it back off
    # an order, not just change it to another code.
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE orders SET ship_via = %s WHERE id = %s", ("U", 1002))

    response = client.post(
        "/orders/1002",
        data={"action": "save", "ship_via": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ship_via FROM orders WHERE id = %s", (1002,))
            (ship_via,) = cur.fetchone()
    assert not ship_via


def test_blank_ship_via_does_not_render_as_missing(client, seed_orders):
    response = client.get("/orders/1001")
    assert response.status_code == 200
    match = re.search(
        r'<label class="field[^"]*">\s*<span class="field-label">Ship Via</span>.*?</label>',
        response.get_data(as_text=True),
        re.S,
    )
    assert match is not None
    assert "field-missing" not in match.group(0)


def test_save_persists_terms_and_it_reaches_the_vi_payment_type(client, seed_orders, db_url):
    response = client.post(
        "/orders/1001",
        data={"action": "save", "terms": "Credit Card"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with psycopg.connect(db_url, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id = %s", (1001,))
            order = cur.fetchone()
    assert order["deposit_payment_type"] == "Credit Card"
    assert mapping.detail_to_vi(order, [], [])["payment_type"] == "Credit Card"


def test_save_ignores_a_terms_value_the_database_would_reject(client, seed_orders, db_url):
    response = client.post(
        "/orders/1001",
        data={"action": "save", "terms": "Wire Transfer"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT deposit_payment_type FROM orders WHERE id = %s", (1001,))
            (terms,) = cur.fetchone()
    assert terms == "Check"


def test_a_partial_post_leaves_fields_it_did_not_carry_alone(
    client, seed_orders, db_url, tmp_path, monkeypatch
):
    # Submit saves the draft first, so a post carrying only the comment must
    # not blank every other field on its way to the CSV.
    monkeypatch.setenv("VI_OUTPUT_DIR", str(tmp_path))
    response = client.post(
        "/orders/1001",
        data={"action": "submit", "comment": "Reviewed/mf"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Submitted to Sage" in response.get_data(as_text=True)

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT customer_no, po_number, ship_to_name, ship_to_address1, "
                "ship_to_city, ship_to_state, ship_to_zip FROM orders WHERE id = %s",
                (1001,),
            )
            row = cur.fetchone()
    assert row == (
        "VA0042",
        "PO-998877",
        "VETERAN - PAT EXAMPLE",
        "100 EXAMPLE WAY",
        "RIVERVIEW",
        "TX",
        "99001",
    )


def test_resolving_needs_review_renames_the_placeholder_file(
    client, seed_orders, db_url, tmp_path, monkeypatch
):
    # The rename used an undefined name, so resolving a needs-review order
    # with a real placeholder file on disk raised a NameError.
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    folder = tmp_path / "orders"
    folder.mkdir()
    (folder / "placeholder-1004.pdf").write_bytes(b"%PDF-1.4 test\n")

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sources (order_id, source_type, original_filename, "
                "gdrive_path, gdrive_filename, is_placeholder, placeholder_name) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    1004,
                    "attachment",
                    "placeholder-1004.pdf",
                    "orders/placeholder-1004.pdf",
                    "placeholder-1004.pdf",
                    1,
                    "placeholder-1004",
                ),
            )

    response = client.post(
        "/orders/1004",
        data={"resolved_order_number": "PO-12345"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    assert (folder / "PO-12345.pdf").is_file()
    assert not (folder / "placeholder-1004.pdf").exists()

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gdrive_path, gdrive_filename, is_placeholder "
                "FROM sources WHERE order_id = %s",
                (1004,),
            )
            row = cur.fetchone()
    assert row == ("orders/PO-12345.pdf", "PO-12345.pdf", 0)
