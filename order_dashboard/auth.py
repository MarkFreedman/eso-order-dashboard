"""Who is using the dashboard.

Two ways in:

* Microsoft sign-in (Entra ID), on when ENTRA_TENANT_ID, ENTRA_CLIENT_ID and
  ENTRA_CLIENT_SECRET are all set. Lauren's team signs in with their own
  Eschenbach Microsoft accounts. Microsoft's msal library runs the
  authorization-code flow; only the identity token is used, no Graph calls.
* The shared username and password (BASIC_AUTH_USER / BASIC_AUTH_PASSWORD).
  With Microsoft sign-in off it guards every page directly, exactly as it
  always did. With Microsoft sign-in on it is reachable only at
  /auth/shared, for Mark until he has a guest account, and it disappears
  when those two settings are removed.

Either way a successful sign-in stores a small "user" dict in the session:
{"label": ..., "method": "microsoft" | "shared"}. The label is the email
for Microsoft sign-ins and the literal "shared login" otherwise. It shows in
the header, in the access log, and in orders.reviewed_by.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import timedelta

import msal
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)

bp = Blueprint("auth", __name__, url_prefix="/auth")

SESSION_LIFETIME = timedelta(hours=12)
_ACCESS_LOG = logging.getLogger("order_dashboard.access")
# INFO would otherwise be dropped in production (root level is WARNING). The
# lines propagate to Flask's "order_dashboard" logger, which writes to stderr.
_ACCESS_LOG.setLevel(logging.INFO)

SHARED_LABEL = "shared login"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def microsoft_configured() -> bool:
    return all(os.environ.get(k) for k in ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"))


def shared_credentials() -> tuple[str, str] | None:
    user = os.environ.get("BASIC_AUTH_USER")
    password = os.environ.get("BASIC_AUTH_PASSWORD")
    if user and password:
        return user, password
    return None


def _build_msal_app() -> msal.ConfidentialClientApplication:
    tenant = os.environ["ENTRA_TENANT_ID"]
    return msal.ConfidentialClientApplication(
        os.environ["ENTRA_CLIENT_ID"],
        client_credential=os.environ["ENTRA_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{tenant}",
    )


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def current_user() -> dict | None:
    return session.get("user")


def current_label() -> str | None:
    user = current_user()
    return user["label"] if user else None


def _sign_in(label: str, method: str, name: str | None = None) -> None:
    session.clear()
    session["user"] = {"label": label, "method": method, "name": name or label}
    session.permanent = True


def shared_login_matches(auth) -> bool:
    """True when the Basic auth header carries the shared username and password."""
    creds = shared_credentials()
    if creds is None or auth is None or auth.username is None or auth.password is None:
        return False
    user, password = creds
    return secrets.compare_digest(auth.username, user) and secrets.compare_digest(auth.password, password)


def shared_login_challenge() -> Response:
    return Response(
        "Authentication required",
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="Eschenbach Order Review"'},
    )


def log_access(label: str) -> None:
    _ACCESS_LOG.info("user=%s %s %s", label, request.method, request.path)


# ---------------------------------------------------------------------------
# Routes (only registered when Microsoft sign-in is on)
# ---------------------------------------------------------------------------

@bp.get("/login")
def login():
    flow = _build_msal_app().initiate_auth_code_flow(
        scopes=[], redirect_uri=url_for("auth.callback", _external=True)
    )
    session["auth_flow"] = flow
    return redirect(flow["auth_uri"])


@bp.get("/callback")
def callback():
    flow = session.pop("auth_flow", None) or {}
    try:
        result = _build_msal_app().acquire_token_by_auth_code_flow(flow, request.args.to_dict())
    except ValueError:
        # No flow in the session, or the state does not match: a stale or
        # forged callback. Start over.
        abort(400, "Sign-in did not start here. Please try again.")
    if "error" in result:
        current_app.logger.warning(
            "Microsoft sign-in refused: %s %s", result.get("error"), result.get("error_description")
        )
        abort(403, "Microsoft did not complete the sign-in.")
    claims = result.get("id_token_claims") or {}
    email = claims.get("preferred_username") or claims.get("email") or claims.get("oid")
    if not email:
        abort(403, "Microsoft did not say who signed in.")
    _sign_in(email, "microsoft", name=claims.get("name"))
    return redirect(url_for("queue.index"))


@bp.get("/shared")
def shared():
    if shared_credentials() is None:
        abort(404)
    if not shared_login_matches(request.authorization):
        return shared_login_challenge()
    _sign_in(SHARED_LABEL, "shared")
    return redirect(url_for("queue.index"))


@bp.get("/logout")
def logout():
    session.clear()
    return render_template_string(
        "<!doctype html><title>Signed out</title>"
        "<p style='font-family:sans-serif;margin:40px'>Signed out. "
        "<a href='{{ url_for(\"auth.login\") }}'>Sign in again</a></p>"
    )
