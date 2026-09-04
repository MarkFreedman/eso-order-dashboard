def test_queue_page_renders(client, seed_orders):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Order Queue" in body
    assert "VA Medical Center - Palo Alto" in body
    assert "Needs Review" in body


def test_queue_shows_skipped_order_label_and_reason(client, seed_orders):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Skipped (custom order)" in body
    assert "Custom prescription eyeglass order" in body
