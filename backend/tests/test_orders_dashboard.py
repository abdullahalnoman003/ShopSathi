import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Chat, Order, Product, Shop
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"


def signup(client, email="a@example.com", shop="Shop A"):
    return client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD}).json()["access_token"]


def moderator(client, owner_token):
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(owner_token))
    return client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]


def add_product(client, token, name, price, stock, sizes=(), colours=()):
    r = client.post(f"{API}/products", json={"name": name, "description": "", "price": price, "sizes": list(sizes), "colours": list(colours), "stock_count": stock}, headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def make_order(db, shop_id, product_id, *, status="draft", is_test=False, name="Rahim Uddin", product="Cotton Panjabi", size="M", colour="White",
               qty=2, price=1100, address="House 5, Road 3, Dhanmondi, Dhaka", phone="01712345678", confirmed_at=None, chat_id=None):
    o = Order(shop_id=shop_id, chat_id=chat_id, product_id=product_id, product_name=product, size=size, colour=colour, quantity=qty, unit_price=price,
              customer_name=name, customer_phone=phone, customer_address=address, status=status, is_test=is_test)
    if status == "confirmed":
        o.confirmed_at = confirmed_at or datetime.now(timezone.utc)
    if status == "cancelled":
        o.cancelled_at = datetime.now(timezone.utc)
    db.add(o)
    db.commit()
    return o


@pytest.fixture
def shop(client, db):
    token = signup(client)
    sid = db.scalar(select(Shop.id))
    pid = add_product(client, token, "Cotton Panjabi", 1100, 10, ["M", "L", "XL"], ["White", "Navy"])
    return token, sid, pid


def ids(resp):
    return [o["id"] for o in resp.json()["items"]]


# ----------------------------------------------------------------------- list / get


def test_list_defaults_to_drafts_newest_first_and_excludes_test_and_other_shops(client, db, shop):
    token, sid, pid = shop
    h = auth_header(token)
    first = make_order(db, sid, pid)
    second = make_order(db, sid, pid)
    make_order(db, sid, pid, is_test=True)
    confirmed = make_order(db, sid, pid, status="confirmed")
    cancelled = make_order(db, sid, pid, status="cancelled")
    other_token = signup(client, "b@example.com", "Shop B")
    other_sid = db.scalar(select(Shop.id).where(Shop.name == "Shop B"))
    theirs = make_order(db, other_sid, None, name="Zed")

    body = client.get(f"{API}/orders", headers=h).json()
    assert [o["id"] for o in body["items"]] == [second.id, first.id]
    assert body["total"] == 2 and body["counts"] == {"draft": 2, "confirmed": 1, "cancelled": 1}
    assert ids(client.get(f"{API}/orders?status=confirmed", headers=h)) == [confirmed.id]
    assert ids(client.get(f"{API}/orders?status=cancelled", headers=h)) == [cancelled.id]
    assert client.get(f"{API}/orders?status=bogus", headers=h).status_code == 422
    assert theirs.id not in [o["id"] for s in ("draft", "confirmed", "cancelled") for o in client.get(f"{API}/orders?status={s}", headers=h).json()["items"]]
    assert client.get(f"{API}/orders", headers=auth_header(other_token)).json()["items"][0]["customer_name"] == "Zed"


def test_pagination(client, db, shop):
    token, sid, pid = shop
    for _ in range(5):
        make_order(db, sid, pid)
    h = auth_header(token)
    p1 = client.get(f"{API}/orders?page=1&page_size=2", headers=h).json()
    p3 = client.get(f"{API}/orders?page=3&page_size=2", headers=h).json()
    assert p1["total"] == 5 and len(p1["items"]) == 2 and len(p3["items"]) == 1
    assert client.get(f"{API}/orders?page_size=500", headers=h).status_code == 422


def test_order_detail_has_total_chat_link_and_product_options(client, db, shop):
    token, sid, pid = shop
    chat = Chat(shop_id=sid, channel="messenger", customer_psid="p1")
    db.add(chat)
    db.commit()
    o = make_order(db, sid, pid, chat_id=chat.id, qty=3, price=1100)
    body = client.get(f"{API}/orders/{o.id}", headers=auth_header(token)).json()
    assert body["chat_id"] == chat.id and body["total_price"] == 3300 and body["unit_price"] == 1100
    assert body["product_sizes"] == ["M", "L", "XL"] and body["product_colours"] == ["White", "Navy"]


def test_test_orders_and_other_shops_orders_are_404_everywhere(client, db, shop):
    token, sid, pid = shop
    h = auth_header(token)
    test = make_order(db, sid, pid, is_test=True)
    signup(client, "b@example.com", "Shop B")
    theirs = make_order(db, db.scalar(select(Shop.id).where(Shop.name == "Shop B")), None)
    for o in (test, theirs):
        assert client.get(f"{API}/orders/{o.id}", headers=h).status_code == 404
        assert client.patch(f"{API}/orders/{o.id}", json={"quantity": 1}, headers=h).status_code == 404
        assert client.post(f"{API}/orders/{o.id}/confirm", headers=h).status_code == 404
        assert client.post(f"{API}/orders/{o.id}/cancel", headers=h).status_code == 404
    db.refresh(theirs)
    assert theirs.status == "draft"


# ----------------------------------------------------------------------- edit


def test_edit_fields(client, db, shop):
    token, sid, pid = shop
    o = make_order(db, sid, pid)
    r = client.patch(f"{API}/orders/{o.id}", headers=auth_header(token), json={
        "size": "xl", "colour": "navy", "quantity": 3, "customer_name": " Karim ", "customer_phone": "+88 017-1234 5679", "customer_address": "New address, Dhaka"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["size"], body["colour"], body["quantity"], body["customer_name"]) == ("XL", "Navy", 3, "Karim")
    assert body["customer_phone"] == "01712345679" and body["customer_address"] == "New address, Dhaka"
    assert body["unit_price"] == 1100 and body["total_price"] == 3300 and body["status"] == "draft"


def test_edit_validation(client, db, shop):
    token, sid, pid = shop
    o = make_order(db, sid, pid)
    h = auth_header(token)

    def bad(payload, field):
        r = client.patch(f"{API}/orders/{o.id}", json=payload, headers=h)
        assert r.status_code == 422, (payload, r.text)
        assert field in r.text
        return r

    bad({"customer_phone": "12345"}, "customer_phone")
    bad({"customer_phone": "01212345678"}, "customer_phone")
    bad({"size": "XXL"}, "size")
    bad({"size": None}, "size")  # this product needs a size
    bad({"colour": "Purple"}, "colour")
    bad({"quantity": 0}, "quantity")
    bad({"quantity": -2}, "quantity")
    bad({"quantity": 11}, "quantity")  # only 10 in stock
    bad({"customer_name": " "}, "customer_name")
    bad({"customer_address": ""}, "customer_address")
    bad({"product_id": 999999}, "product_id")
    bad({"unit_price": 1}, "unit_price")  # the price cannot be edited
    bad({"status": "confirmed"}, "status")  # nor the status
    db.refresh(o)
    assert (o.size, o.quantity, o.customer_phone) == ("M", 2, "01712345678")  # nothing was changed


def test_changing_the_product_takes_the_catalogue_price_and_rechecks_options(client, db, shop):
    token, sid, pid = shop
    mug = add_product(client, token, "Blue Mug", 250, 5)
    o = make_order(db, sid, pid)
    h = auth_header(token)
    assert client.patch(f"{API}/orders/{o.id}", json={"product_id": mug}, headers=h).status_code == 200  # no sizes: cleared
    body = client.get(f"{API}/orders/{o.id}", headers=h).json()
    assert body["product_name"] == "Blue Mug" and body["unit_price"] == 250 and body["total_price"] == 500
    assert body["size"] is None and body["colour"] is None and body["product_sizes"] == []
    assert client.patch(f"{API}/orders/{o.id}", json={"product_id": mug, "size": "M"}, headers=h).status_code == 422
    # back to the panjabi: size and colour must be chosen again
    r = client.patch(f"{API}/orders/{o.id}", json={"product_id": pid}, headers=h)
    assert r.status_code == 422 and "size" in r.text
    r = client.patch(f"{API}/orders/{o.id}", json={"product_id": pid, "size": "L", "colour": "White"}, headers=h)
    assert r.status_code == 200 and r.json()["unit_price"] == 1100


def test_price_follows_the_catalogue_only_when_the_product_changes(client, db, shop):
    token, sid, pid = shop
    o = make_order(db, sid, pid, price=999)  # price at drafting time
    h = auth_header(token)
    db.execute(Product.__table__.update().where(Product.id == pid).values(price=1500))
    db.commit()
    assert client.patch(f"{API}/orders/{o.id}", json={"quantity": 4}, headers=h).json()["unit_price"] == 999
    other = add_product(client, token, "Other", 700, 3)
    assert client.patch(f"{API}/orders/{o.id}", json={"product_id": other, "quantity": 1}, headers=h).json()["unit_price"] == 700


def test_a_product_of_another_shop_cannot_be_used(client, db, shop):
    token, sid, pid = shop
    other_token = signup(client, "b@example.com", "Shop B")
    foreign = add_product(client, other_token, "Foreign", 10, 5)
    o = make_order(db, sid, pid)
    r = client.patch(f"{API}/orders/{o.id}", json={"product_id": foreign}, headers=auth_header(token))
    assert r.status_code == 422 and "does not exist" in r.text


def test_orders_whose_product_was_deleted_can_still_be_edited_and_confirmed(client, db, shop):
    token, sid, _ = shop
    o = make_order(db, sid, None)
    h = auth_header(token)
    r = client.patch(f"{API}/orders/{o.id}", json={"customer_name": "New Name", "size": "M"}, headers=h)
    assert r.status_code == 200 and r.json()["product_sizes"] is None
    assert client.post(f"{API}/orders/{o.id}/confirm", headers=h).status_code == 200


# ----------------------------------------------------------------------- transitions


def test_confirm_and_cancel_transitions(client, db, shop):
    token, sid, pid = shop
    h = auth_header(token)
    a, b = make_order(db, sid, pid), make_order(db, sid, pid)

    r = client.post(f"{API}/orders/{a.id}/confirm", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "confirmed" and r.json()["confirmed_at"]
    db.refresh(a)
    assert a.confirmed_by_user_id is not None and a.cancelled_at is None
    for call in (lambda: client.post(f"{API}/orders/{a.id}/confirm", headers=h), lambda: client.post(f"{API}/orders/{a.id}/cancel", headers=h),
                 lambda: client.patch(f"{API}/orders/{a.id}", json={"quantity": 1}, headers=h)):
        r = call()
        assert r.status_code == 409 and "already confirmed" in r.json()["detail"]

    r = client.post(f"{API}/orders/{b.id}/cancel", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancelled_at"]
    db.refresh(b)
    assert b.confirmed_at is None and b.confirmed_by_user_id is None
    for call in (lambda: client.post(f"{API}/orders/{b.id}/confirm", headers=h), lambda: client.post(f"{API}/orders/{b.id}/cancel", headers=h),
                 lambda: client.patch(f"{API}/orders/{b.id}", json={"quantity": 1}, headers=h)):
        r = call()
        assert r.status_code == 409 and "already cancelled" in r.json()["detail"]


def test_confirming_does_not_touch_stock(client, db, shop):
    token, sid, pid = shop
    o = make_order(db, sid, pid, qty=4)
    client.post(f"{API}/orders/{o.id}/confirm", headers=auth_header(token))
    assert db.scalar(select(Product.stock_count).where(Product.id == pid)) == 10


# ----------------------------------------------------------------------- export


def read_csv(resp):
    assert resp.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def test_export_has_exact_columns_and_only_confirmed_orders_in_range(client, db, shop):
    token, sid, pid = shop
    h = auth_header(token)
    now = datetime.now(timezone.utc)
    inside = make_order(db, sid, pid, status="confirmed", confirmed_at=now - timedelta(days=2), name="রহিম উদ্দিন", address="বাড়ি ৫, ধানমন্ডি, ঢাকা", qty=3, price=1100)
    edge = make_order(db, sid, pid, status="confirmed", confirmed_at=now - timedelta(days=1), colour=None, size=None, price=250.5)
    make_order(db, sid, pid, status="confirmed", confirmed_at=now - timedelta(days=10))  # before the range
    make_order(db, sid, pid, status="draft")
    make_order(db, sid, pid, status="cancelled")
    make_order(db, sid, pid, status="confirmed", is_test=True, confirmed_at=now - timedelta(days=2))
    other_token = signup(client, "b@example.com", "Shop B")
    make_order(db, db.scalar(select(Shop.id).where(Shop.name == "Shop B")), None, status="confirmed", confirmed_at=now - timedelta(days=2))

    frm = (now - timedelta(days=3)).date().isoformat()
    to = now.date().isoformat()
    r = client.get(f"{API}/orders/export?from={frm}&to={to}", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    rows = read_csv(r)
    assert rows[0] == ["order_id", "confirmed_at", "customer_name", "customer_phone", "customer_address", "product_name", "size", "colour", "quantity", "unit_price", "total_price"]
    assert [int(x[0]) for x in rows[1:]] == [inside.id, edge.id]
    first = rows[1]
    assert first[2] == "রহিম উদ্দিন" and first[4] == "বাড়ি ৫, ধানমন্ডি, ঢাকা" and first[3] == "01712345678"
    assert first[5:] == ["Cotton Panjabi", "M", "White", "3", "1100.00", "3300.00"]
    assert rows[2][6:8] == ["", ""] and rows[2][9:] == ["250.50", "501.00"]
    assert len(first[1]) == 16 and first[1][4] == "-"  # YYYY-MM-DD HH:MM

    everything = read_csv(client.get(f"{API}/orders/export", headers=h))
    assert len(everything) == 1 + 3  # all three of this shop's real confirmed orders
    assert read_csv(client.get(f"{API}/orders/export", headers=auth_header(other_token))).__len__() == 2


def test_export_range_uses_dhaka_days_and_includes_both_ends(client, db, shop):
    token, sid, pid = shop
    # 2026-03-10 19:00 UTC is 2026-03-11 01:00 in Dhaka (UTC+6)
    o = make_order(db, sid, pid, status="confirmed", confirmed_at=datetime(2026, 3, 10, 19, 0, tzinfo=timezone.utc))
    h = auth_header(token)
    assert len(read_csv(client.get(f"{API}/orders/export?from=2026-03-11&to=2026-03-11", headers=h))) == 2
    assert len(read_csv(client.get(f"{API}/orders/export?from=2026-03-10&to=2026-03-10", headers=h))) == 1
    assert read_csv(client.get(f"{API}/orders/export?from=2026-03-11&to=2026-03-11", headers=h))[1][1] == "2026-03-11 01:00"


def test_export_validates_dates_and_works_when_empty(client, shop):
    h = auth_header(shop[0])
    assert client.get(f"{API}/orders/export?from=2026-05-02&to=2026-05-01", headers=h).status_code == 422
    assert client.get(f"{API}/orders/export?from=not-a-date", headers=h).status_code == 422
    assert client.get(f"{API}/orders/export?from=2020-01-01&to=2026-01-01", headers=h).status_code == 422  # too long
    rows = read_csv(client.get(f"{API}/orders/export", headers=h))
    assert len(rows) == 1 and len(rows[0]) == 11


def test_export_neutralises_spreadsheet_formulas(client, db, shop):
    token, sid, pid = shop
    make_order(db, sid, pid, status="confirmed", name="=HYPERLINK(\"http://evil\")", address="@SUM(A1)")
    row = read_csv(client.get(f"{API}/orders/export", headers=auth_header(token)))[1]
    assert row[2].startswith("'=") and row[4].startswith("'@")


# ----------------------------------------------------------------------- access


def test_moderator_can_list_product_options_of_their_own_shop(client, db, shop):
    token, sid, pid = shop
    signup(client, "b@example.com", "Shop B")
    mod = auth_header(moderator(client, token))
    assert client.get(f"{API}/products", headers=mod).status_code == 403  # the products API stays owner-only
    body = client.get(f"{API}/orders/product-options", headers=mod).json()
    assert [(p["id"], p["name"], p["price"], p["sizes"], p["colours"]) for p in body] == [(pid, "Cotton Panjabi", 1100, ["M", "L", "XL"], ["White", "Navy"])]


def test_moderator_can_do_everything_and_the_id_is_recorded(client, db, shop):
    token, sid, pid = shop
    mod = auth_header(moderator(client, token))
    o = make_order(db, sid, pid)
    assert client.get(f"{API}/orders", headers=mod).json()["total"] == 1
    assert client.patch(f"{API}/orders/{o.id}", json={"quantity": 1}, headers=mod).status_code == 200
    assert client.post(f"{API}/orders/{o.id}/confirm", headers=mod).status_code == 200
    assert client.get(f"{API}/orders/export", headers=mod).status_code == 200
    c = make_order(db, sid, pid)
    assert client.post(f"{API}/orders/{c.id}/cancel", headers=mod).status_code == 200
    db.refresh(o)
    assert o.confirmed_by_user_id is not None


def test_anonymous_and_platform_admin_are_refused(client, db, shop, monkeypatch):
    from app.cli import main as cli_main

    o = make_order(db, shop[1], shop[2])
    for method, path in (("get", ""), ("get", "/export"), ("get", f"/{o.id}"), ("post", f"/{o.id}/confirm"), ("patch", f"/{o.id}")):
        assert getattr(client, method)(f"{API}/orders{path}").status_code == 401
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    admin = auth_header(client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"])
    assert client.get(f"{API}/orders", headers=admin).status_code == 403
    assert client.get(f"{API}/orders/export", headers=admin).status_code == 403
