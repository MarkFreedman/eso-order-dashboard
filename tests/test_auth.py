"""Sign-in tests.

Two front doors exist:

* Microsoft sign-in (Entra ID), turned on by the three ENTRA_* settings.
  Microsoft itself is never contacted here: the msal client is replaced with
  a fake so the suite runs offline.
* The shared username and password (BASIC_AUTH_*). With Microsoft sign-in
  off it guards every page as before. With Microsoft sign-in on it is only
  reachable at /auth/shared, and disappears when its two settings are
  removed.
"""

import pytest

from order_dashboard import auth, create_app

from .conftest import basic_auth_header, ensure_schema

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"


class FakeMsal:
    """Stand-in for msal.ConfidentialClientApplication."""

    def __init__(self, result=None, raise_value_error=False):
        self.result = result or {
            "id_token_claims": {"name": "Lauren Gumpel", "preferred_username": "lgumpel@eschenbach.com"}
        }
        self.raise_value_error = raise_value_error
        self.redirect_uri = None

    def initiate_auth_code_flow(self, scopes, redirect_uri=None, **kwargs):
        self.redirect_uri = redirect_uri
        return {"auth_uri": "https://login.microsoftonline.com/fake-authorize", "state": "abc"}

    def acquire_token_by_auth_code_flow(self, auth_code_flow, auth_response, scopes=None, **kwargs):
        if self.raise_value_error:
            raise ValueError("state mismatch")
        assert auth_code_flow.get("state") == "abc"
        return self.result


def _base_env(monkeypatch, db_url):
    ensure_schema(db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")


def _entra_env(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "shh")


def _shared_env(monkeypatch):
    monkeypatch.setenv("BASIC_AUTH_USER", "lauren")
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", "hunter2")


@pytest.fixture
def fake_msal(monkeypatch):
    fake = FakeMsal()
    monkeypatch.setattr(auth, "_build_msal_app", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# No sign-in configured at all
# ---------------------------------------------------------------------------

def test_no_env_means_no_auth(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    with pytest.raises(RuntimeError, match="[Aa]uthentication"):
        create_app()


# ---------------------------------------------------------------------------
# Shared login only (Microsoft sign-in off): unchanged behavior
# ---------------------------------------------------------------------------

def test_auth_required_when_env_set(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    _shared_env(monkeypatch)
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 401
    assert "Basic realm" in response.headers.get("WWW-Authenticate", "")


def test_auth_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    _shared_env(monkeypatch)
    client = create_app().test_client()
    response = client.get("/", headers=basic_auth_header("lauren", "wrong"))
    assert response.status_code == 401


def test_auth_accepts_correct_credentials(monkeypatch, db_url):
    _base_env(monkeypatch, db_url)
    _shared_env(monkeypatch)
    client = create_app().test_client()
    response = client.get("/", headers=basic_auth_header("lauren", "hunter2"))
    assert response.status_code == 200


def test_shared_route_is_absent_without_microsoft_sign_in(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    _shared_env(monkeypatch)
    client = create_app().test_client()
    response = client.get("/auth/shared", headers=basic_auth_header("lauren", "hunter2"))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Microsoft sign-in on
# ---------------------------------------------------------------------------

def test_unauthenticated_visit_redirects_to_microsoft_login(monkeypatch, db_url, fake_msal):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    client = create_app().test_client()

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")

    response = client.get("/auth/login")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://login.microsoftonline.com/fake-authorize"
    assert fake_msal.redirect_uri.endswith("/auth/callback")


def test_callback_signs_the_user_in(monkeypatch, db_url, fake_msal):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    client = create_app().test_client()

    client.get("/auth/login")
    response = client.get("/auth/callback?code=xyz&state=abc")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Lauren Gumpel" in page
    assert "Sign out" in page


def test_callback_without_a_started_flow_is_rejected(monkeypatch, db_url):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    monkeypatch.setattr(auth, "_build_msal_app", lambda: FakeMsal(raise_value_error=True))
    client = create_app().test_client()
    response = client.get("/auth/callback?code=xyz&state=abc")
    assert response.status_code == 400


def test_callback_error_from_microsoft_is_refused(monkeypatch, db_url):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    monkeypatch.setattr(
        auth, "_build_msal_app",
        lambda: FakeMsal(result={"error": "access_denied", "error_description": "nope"}),
    )
    client = create_app().test_client()
    client.get("/auth/login")
    response = client.get("/auth/callback?error=access_denied&state=abc")
    assert response.status_code == 403
    assert client.get("/").status_code == 302  # still not signed in


def test_shared_login_route_when_microsoft_sign_in_is_on(monkeypatch, db_url, fake_msal):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    _shared_env(monkeypatch)
    client = create_app().test_client()

    # The old header on a normal page no longer counts by itself.
    assert client.get("/", headers=basic_auth_header("lauren", "hunter2")).status_code == 302

    response = client.get("/auth/shared")
    assert response.status_code == 401
    assert "Basic realm" in response.headers.get("WWW-Authenticate", "")

    assert client.get("/auth/shared", headers=basic_auth_header("lauren", "wrong")).status_code == 401

    response = client.get("/auth/shared", headers=basic_auth_header("lauren", "hunter2"))
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    response = client.get("/")
    assert response.status_code == 200
    assert "shared login" in response.get_data(as_text=True)


def test_shared_login_route_vanishes_when_its_settings_are_removed(monkeypatch, db_url, fake_msal):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    client = create_app().test_client()
    response = client.get("/auth/shared", headers=basic_auth_header("lauren", "hunter2"))
    assert response.status_code == 404


def test_logout_clears_the_session(monkeypatch, db_url, fake_msal):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    client = create_app().test_client()
    client.get("/auth/login")
    client.get("/auth/callback?code=xyz&state=abc")
    assert client.get("/").status_code == 200

    response = client.get("/auth/logout")
    assert response.status_code == 200
    assert "Signed out" in response.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_each_request_logs_who_made_it(monkeypatch, db_url, fake_msal, caplog):
    _base_env(monkeypatch, db_url)
    _entra_env(monkeypatch)
    client = create_app().test_client()
    client.get("/auth/login")
    client.get("/auth/callback?code=xyz&state=abc")
    with caplog.at_level("INFO", logger="order_dashboard.access"):
        client.get("/")
    line = " ".join(r.getMessage() for r in caplog.records)
    assert "lgumpel@eschenbach.com" in line
    assert "GET /" in line
