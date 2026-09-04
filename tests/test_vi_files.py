"""Tests for the VI Files page (/vi-files) and CSV download."""

import pytest

from order_dashboard import create_app

from .conftest import AUTH, AUTH_PASSWORD, AUTH_USER


@pytest.fixture
def vi_dir(tmp_path):
    d = tmp_path / "vi-output"
    d.mkdir()
    return d


@pytest.fixture
def client(vi_dir, monkeypatch):
    # This page never touches the database, so it gets its own client
    # fixture (VI_OUTPUT_DIR instead of DATABASE_URL) rather than the
    # shared conftest one, reusing only the auth credentials/header.
    monkeypatch.setenv("VI_OUTPUT_DIR", str(vi_dir))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BASIC_AUTH_USER", AUTH_USER)
    monkeypatch.setenv("BASIC_AUTH_PASSWORD", AUTH_PASSWORD)
    return create_app().test_client()


def test_listing_shows_csv_files_newest_first(client, vi_dir):
    import os
    import time

    older = vi_dir / "order_1.csv"
    older.write_text("a,b\n1,2\n")
    newer = vi_dir / "batch_20260904_100000.csv"
    newer.write_text("a,b\n3,4\n")
    # Force a clear ordering regardless of filesystem timestamp resolution.
    now = time.time()
    os.utime(older, (now - 3600, now - 3600))
    os.utime(newer, (now, now))
    (vi_dir / "notes.txt").write_text("not a csv")

    resp = client.get("/vi-files", headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "VI Files" in body
    assert "batch_20260904_100000.csv" in body
    assert "order_1.csv" in body
    assert "notes.txt" not in body
    assert body.index("batch_20260904_100000.csv") < body.index("order_1.csv")
    assert "/vi-files/order_1.csv" in body


def test_listing_empty_state(client):
    resp = client.get("/vi-files", headers=AUTH)
    assert resp.status_code == 200
    assert "No VI files yet" in resp.get_data(as_text=True)


def test_download_serves_csv_as_attachment(client, vi_dir):
    (vi_dir / "order_7.csv").write_text("H,1,2\nD,3,4\n")
    resp = client.get("/vi-files/order_7.csv", headers=AUTH)
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "order_7.csv" in resp.headers["Content-Disposition"]
    assert resp.get_data(as_text=True) == "H,1,2\nD,3,4\n"


def test_download_rejects_non_csv_and_bad_names(client, vi_dir):
    (vi_dir / "secret.txt").write_text("nope")
    assert client.get("/vi-files/secret.txt", headers=AUTH).status_code == 404
    assert client.get("/vi-files/missing.csv", headers=AUTH).status_code == 404
    assert client.get("/vi-files/bad%20name.csv", headers=AUTH).status_code == 404


def test_download_rejects_path_traversal(client, vi_dir, tmp_path):
    outside = tmp_path / "outside.csv"
    outside.write_text("leak")
    for path in ("/vi-files/..%2Foutside.csv", "/vi-files/%2E%2E/outside.csv"):
        resp = client.get(path, headers=AUTH)
        assert resp.status_code == 404, path
        assert "leak" not in resp.get_data(as_text=True)


def test_listing_requires_auth(client):
    assert client.get("/vi-files").status_code == 401
