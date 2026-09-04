import psycopg


def test_queue_page_renders(client, seed_orders):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Order Queue" in body
    assert "VA Sample Clinic - Riverview" in body
    assert "Needs Review" in body


def test_queue_shows_skipped_order_label_and_reason(client, seed_orders):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Skipped (custom order)" in body
    assert "Custom prescription eyeglass order" in body


def test_skipped_orders_sort_last_in_the_queue(client, seed_orders):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # 1005 is skipped, 1003 is submitted: skipped sorts below everything.
    assert body.index("/orders/1005") > body.index("/orders/1003")
    assert body.index("/orders/1005") > body.index("/orders/1001")


def test_batch_submit_leaves_out_blank_comment_and_skipped_orders(
    client, seed_orders, db_url, tmp_path, monkeypatch
):
    # The batch must enforce the same two rules the single-order submit
    # does, without failing the whole batch: 1001 has a comment and goes,
    # 1002 has none, and 1005 was skipped.
    monkeypatch.setenv("VI_OUTPUT_DIR", str(tmp_path))
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE orders SET comment = %s WHERE id = %s", ("Reviewed/mf", 1001))
            cur.execute("UPDATE orders SET comment = %s WHERE id = %s", ("   ", 1002))

    response = client.post(
        "/batch-submit",
        data={"order_ids": ["1001", "1002", "1005"]},
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Submitted 1 order(s) to Sage" in body
    assert "Order 1002: no comment" in body
    assert "Order 1005: skipped" in body

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status FROM orders WHERE id IN (1001, 1002, 1005) ORDER BY id"
            )
            statuses = dict(cur.fetchall())
    assert statuses == {1001: "submitted", 1002: "extracted", 1005: "skipped"}
    assert len(list(tmp_path.glob("batch_*.csv"))) == 1
