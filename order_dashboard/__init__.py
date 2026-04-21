import os
import secrets
from pathlib import Path

from flask import Flask, Response, request
from flask_wtf.csrf import CSRFProtect

from . import db, queue

# Dev secrets live outside Dropbox. Production uses env vars directly (no .env file).
_USER_ENV = Path.home() / ".config" / "order-dashboard" / ".env"

_csrf = CSRFProtect()


def _load_env() -> None:
    """Load .env from ~/.config/order-dashboard/ if present (dev only)."""
    if _USER_ENV.exists():
        from dotenv import load_dotenv
        load_dotenv(_USER_ENV, override=False)


def create_app() -> Flask:
    _load_env()
    app = Flask(__name__)

    # Finding 3: fail loudly if SECRET_KEY is not set rather than using a
    # hardcoded fallback that is visible in source control.
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable must be set")
    app.secret_key = secret_key

    db.init_app(app)
    _csrf.init_app(app)
    app.register_blueprint(queue.bp)
    _install_basic_auth(app)
    _install_security_headers(app)
    return app


def _install_basic_auth(app: Flask) -> None:
    user = os.environ.get("BASIC_AUTH_USER")
    password = os.environ.get("BASIC_AUTH_PASSWORD")

    # Finding 1: refuse to start without auth rather than silently leaving
    # all routes open. Remove this check once Entra ID SSO is wired up.
    if not user or not password:
        raise RuntimeError(
            "No authentication configured — set BASIC_AUTH_USER and BASIC_AUTH_PASSWORD "
            "(or implement Entra ID SSO)"
        )

    @app.before_request
    def _require_basic_auth():
        sent = request.authorization
        if (
            sent is not None
            and sent.username is not None
            and sent.password is not None
            and secrets.compare_digest(sent.username, user)
            and secrets.compare_digest(sent.password, password)
        ):
            return None
        return Response(
            "Authentication required",
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Eschenbach Order Review"'},
        )


def _install_security_headers(app: Flask) -> None:
    # Finding 6: add baseline security headers to every response.
    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-src 'self'; style-src 'self' 'unsafe-inline'"
        )
        return response
