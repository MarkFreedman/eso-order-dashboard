"""The review page's document viewer reads the copy of the PDF that the
reader stored in the database (sources.file_bytes), falling back to the file
on disk for older rows. Submitting an order drops the database copy; the
G drive keeps the permanent one."""

from __future__ import annotations

import psycopg

from order_dashboard import queries

PDF = b"%PDF-1.4\n% test document\n%%EOF\n"


def _source_id(db_url: str, order_id: int) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE order_id = %s ORDER BY id LIMIT 1", (order_id,))
        (sid,) = cur.fetchone()
        return sid


def _set_bytes(db_url: str, sid: int, data: bytes | None) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("UPDATE sources SET file_bytes = %s WHERE id = %s", (data, sid))


def test_viewer_serves_the_database_copy(client, seed_orders, db_url):
    sid = _source_id(db_url, 1001)
    _set_bytes(db_url, sid, PDF)
    response = client.get(f"/sources/{sid}/file")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data == PDF


def test_viewer_is_404_when_there_is_neither_a_copy_nor_a_file(client, seed_orders, db_url):
    sid = _source_id(db_url, 1001)
    _set_bytes(db_url, sid, None)  # seeded gdrive_path points at a file that does not exist here
    assert client.get(f"/sources/{sid}/file").status_code == 404


def test_submitting_an_order_drops_the_database_copy(client, seed_orders, db_url):
    sid = _source_id(db_url, 1001)
    _set_bytes(db_url, sid, PDF)
    with client.application.app_context():
        queries.submit_order(1001, "/tmp/order_1001.csv")
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT file_bytes IS NULL FROM sources WHERE id = %s", (sid,))
        (cleared,) = cur.fetchone()
    assert cleared
