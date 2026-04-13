import base64

from order_dashboard import create_app


def _client_with_auth(monkeypatch, user="lauren", password="hunter2"):
    monkeypatch.setenv("BASIC_AUTH_USER", user)
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", password)
    return create_app().test_client()


def _basic(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_no_env_means_no_auth():
    response = create_app().test_client().get("/")
    assert response.status_code == 200


def test_auth_required_when_env_set(monkeypatch):
    client = _client_with_auth(monkeypatch)
    response = client.get("/")
    assert response.status_code == 401
    assert "Basic realm" in response.headers.get("WWW-Authenticate", "")


def test_auth_rejects_wrong_password(monkeypatch):
    client = _client_with_auth(monkeypatch)
    response = client.get("/", headers=_basic("lauren", "wrong"))
    assert response.status_code == 401


def test_auth_accepts_correct_credentials(monkeypatch):
    client = _client_with_auth(monkeypatch)
    response = client.get("/", headers=_basic("lauren", "hunter2"))
    assert response.status_code == 200
