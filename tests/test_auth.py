import pytest

from order_dashboard import create_app

from .conftest import basic_auth_header, ensure_schema


def test_no_env_means_no_auth(monkeypatch):
    # The app now refuses to start without auth configured (Finding 1 in
    # __init__.py) rather than silently leaving every route open, so this
    # is the current, intended behavior of "no auth env set".
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    with pytest.raises(RuntimeError, match="[Aa]uthentication"):
        create_app()


def test_auth_required_when_env_set(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BASIC_AUTH_USER", "lauren")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "hunter2")
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 401
    assert "Basic realm" in response.headers.get("WWW-Authenticate", "")


def test_auth_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BASIC_AUTH_USER", "lauren")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "hunter2")
    client = create_app().test_client()
    response = client.get("/", headers=basic_auth_header("lauren", "wrong"))
    assert response.status_code == 401


def test_auth_accepts_correct_credentials(monkeypatch, db_url):
    ensure_schema(db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BASIC_AUTH_USER", "lauren")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "hunter2")
    client = create_app().test_client()
    response = client.get("/", headers=basic_auth_header("lauren", "hunter2"))
    assert response.status_code == 200
