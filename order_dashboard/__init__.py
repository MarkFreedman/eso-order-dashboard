import os
import secrets

from flask import Flask, Response, request

from . import queue


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-mockup-secret-not-for-production")
    app.register_blueprint(queue.bp)
    _install_basic_auth(app)
    return app


def _install_basic_auth(app: Flask) -> None:
    user = os.environ.get("BASIC_AUTH_USER")
    password = os.environ.get("BASIC_AUTH_PASSWORD")
    if not user or not password:
        return

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
