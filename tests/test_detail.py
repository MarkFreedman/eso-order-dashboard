import json

import psycopg


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
