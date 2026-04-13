import pytest

from order_dashboard import create_app


@pytest.fixture
def client():
    return create_app().test_client()


def test_va_detail_suppresses_price_flag(client):
    response = client.get("/orders/1001")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "VA Medical Center - Palo Alto" in body
    assert "Submit to Sage" in body
    assert "badge-price" not in body


def test_non_va_detail_shows_price_flag(client):
    response = client.get("/orders/1002")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Eyecare Associates of Tulsa" in body
    assert "badge-price" in body
    assert "VISA*1024" in body
    assert "field-missing" in body


def test_save_redirects_and_flashes(client):
    response = client.post("/orders/1002", data={"action": "save"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Saved order 1002" in response.get_data(as_text=True)
