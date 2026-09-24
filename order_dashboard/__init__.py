import logging
import os
from pathlib import Path

from flask import Flask, redirect, request, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from . import auth, db, queue

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

    # Fly's proxy terminates HTTPS, so trust its forwarded scheme and host:
    # the Microsoft sign-in redirect URI must be built as https://orders...
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["PERMANENT_SESSION_LIFETIME"] = auth.SESSION_LIFETIME
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "1") == "1"

    db.init_app(app)
    _csrf.init_app(app)
    app.register_blueprint(queue.bp)
    _install_auth(app)
    _install_security_headers(app)
    return app


def _install_auth(app: Flask) -> None:
    """Guard every page.

    Microsoft sign-in on (ENTRA_* set): pages need a signed-in session; a
    visitor without one is sent to /auth/login. The shared login, if still
    configured, is reachable only at /auth/shared.

    Microsoft sign-in off: the shared username and password guard every page
    directly, as they always did, and the /auth routes do not exist.
    """
    microsoft = auth.microsoft_configured()
    shared = auth.shared_credentials()

    # Finding 1: refuse to start without auth rather than silently leaving
    # all routes open.
    if not microsoft and not shared:
        raise RuntimeError(
            "No authentication configured: set ENTRA_TENANT_ID, ENTRA_CLIENT_ID and "
            "ENTRA_CLIENT_SECRET (Microsoft sign-in), or BASIC_AUTH_USER and "
            "BASIC_AUTH_PASSWORD (shared login)"
        )

    # Touching app.logger attaches Flask's stderr handler, which the
    # order_dashboard.access logger propagates to; without it the per-request
    # "user=..." lines never reach the server output.
    app.logger.setLevel(logging.INFO)

    if microsoft:
        app.register_blueprint(auth.bp)

    @app.before_request
    def _require_sign_in():
        if request.endpoint == "static" or (request.blueprint == "auth"):
            return None
        if microsoft:
            user = auth.current_user()
            if user is None:
                return redirect(url_for("auth.login"))
            auth.log_access(user["label"])
            return None
        # Shared login only: the header must be on every request.
        if not auth.shared_login_matches(request.authorization):
            return auth.shared_login_challenge()
        auth.log_access(request.authorization.username)
        return None

    @app.context_processor
    def _inject_user():
        return {"current_user": auth.current_user(), "microsoft_sign_in": microsoft}


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
