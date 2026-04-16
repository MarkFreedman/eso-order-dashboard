"""Database connection for the staging SQLite DB.

The DB is owned by the intake-service. This app connects read/write
for order review, field edits, and status updates.
"""

import os
import sqlite3

from flask import Flask, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = os.environ.get(
            "STAGING_DB_PATH",
            os.path.join(os.path.dirname(__file__), "../../intake-service/staging.db"),
        )
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_app(app: Flask) -> None:
    app.teardown_appcontext(_close_db)


def _close_db(exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
