"""Database connection for the shared Neon Postgres staging DB.

The DB is owned by the intake-service (which creates and migrates the schema).
This app connects read/write for order review, field edits, and status updates.
One Postgres connection per request, closed on teardown.
"""

import os

import psycopg
from flask import Flask, g
from psycopg.rows import dict_row


def get_db() -> psycopg.Connection:
    if "db" not in g:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL environment variable must be set")
        g.db = psycopg.connect(url, row_factory=dict_row)
    return g.db


def init_app(app: Flask) -> None:
    app.teardown_appcontext(_close_db)


def _close_db(exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
