from order_dashboard import create_app


def test_queue_page_renders():
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Order Queue" in body
    assert "VA Medical Center - Palo Alto" in body
    assert "Needs Review" in body
