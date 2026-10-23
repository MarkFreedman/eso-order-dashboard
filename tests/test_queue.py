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


def test_queue_page_loads_its_script_and_order_page_does_not(client, seed_orders):
    # Select-all, the submit confirm and the 60-second auto-refresh live in
    # queue.js: the page's security header blocks inline scripts.
    queue = client.get("/").get_data(as_text=True)
    assert "queue.js" in queue
    assert "<script>" not in queue
    assert "onclick=" not in queue
    assert client.get("/static/queue.js").status_code == 200
    detail = client.get("/orders/1001").get_data(as_text=True)
    assert "queue.js" not in detail


def test_queue_shows_the_customer_po_number(client, seed_orders):
    # Mark, 2026-10-23: the queue had no order number on it, so a row could
    # not be matched to the paper without opening it.
    html = client.get("/").get_data(as_text=True)
    assert ">Customer PO<" in html
    assert "PO-998877" in html
    assert "TUL-88241" in html


def _customer_order(html: str) -> list[str]:
    import re

    return re.findall(r'class="customer-link"[^>]*>([^<]*)<', html)


def test_queue_sorts_by_order_date_both_ways_with_blanks_last(client, seed_orders):
    asc = _customer_order(client.get("/?sort=order_date&dir=asc").get_data(as_text=True))
    assert asc == [
        "Riverview Low Vision Clinic",  # 2026-04-11
        "Statewide Vision Services",  # 2026-04-13
        "VA Sample Clinic - Riverview",  # 2026-04-14
        "Downtown Vision Center",  # 2026-04-15
        "Order #1004",  # no date
    ]
    desc = _customer_order(client.get("/?sort=order_date&dir=desc").get_data(as_text=True))
    assert desc == [
        "Downtown Vision Center",
        "VA Sample Clinic - Riverview",
        "Statewide Vision Services",
        "Riverview Low Vision Clinic",
        "Order #1004",
    ]


def test_queue_sort_header_shows_direction_and_flips_on_click(client, seed_orders):
    html = client.get("/?sort=customer&dir=asc").get_data(as_text=True)
    assert 'aria-sort="ascending"' in html
    assert "/?sort=customer&amp;dir=desc" in html  # the active column offers the flip
    assert "/?sort=order_date&amp;dir=asc" in html  # others start ascending


def test_queue_ignores_an_unknown_sort_column(client, seed_orders):
    default = _customer_order(client.get("/").get_data(as_text=True))
    tampered = client.get("/?sort=1;DROP&dir=desc")
    assert tampered.status_code == 200
    assert _customer_order(tampered.get_data(as_text=True)) == default
    assert "aria-sort" not in tampered.get_data(as_text=True)
