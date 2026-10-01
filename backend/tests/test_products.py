from pathlib import Path

import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.core.config import get_settings
from app.models import Product, User
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def signup(client, email="a@example.com", shop="Shop A"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


def product_body(**over):
    body = {
        "name": "Red Jamdani Saree",
        "description": "Hand-woven",
        "price": 4800,
        "sizes": ["M", "L"],
        "colours": ["Red"],
        "stock_count": 3,
    }
    body.update(over)
    return body


def create(client, token, **over):
    return client.post(f"{API}/products", json=product_body(**over), headers=auth_header(token))


def upload(client, token, pid, *files):
    return client.post(
        f"{API}/products/{pid}/photos",
        files=[("files", (f"p{i}.png", data, "image/png")) for i, data in enumerate(files)],
        headers=auth_header(token),
    )


def media_path(url: str) -> Path:
    return Path(get_settings().media_root).resolve() / url.split("/media/")[1]


@pytest.fixture
def token(client):
    return signup(client)


def test_crud(client, token):
    h = auth_header(token)
    r = create(client, token)
    assert r.status_code == 201
    p = r.json()
    assert (p["name"], p["price"], p["sizes"], p["colours"], p["stock_count"], p["photos"]) == (
        "Red Jamdani Saree",
        4800.0,
        ["M", "L"],
        ["Red"],
        3,
        [],
    )

    assert client.get(f"{API}/products/{p['id']}", headers=h).json()["name"] == "Red Jamdani Saree"

    r = client.put(
        f"{API}/products/{p['id']}",
        json=product_body(name="Blue Saree", price="5200.50", stock_count=0, sizes=[]),
        headers=h,
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["name"], out["price"], out["stock_count"], out["sizes"]) == ("Blue Saree", 5200.5, 0, [])

    assert client.delete(f"{API}/products/{p['id']}", headers=h).status_code == 204
    assert client.get(f"{API}/products/{p['id']}", headers=h).status_code == 404


def test_list_search_and_pagination(client, token):
    for name in ["Cotton Panjabi", "Silk Panjabi", "Red Saree", "100% Cotton"]:
        create(client, token, name=name)
    h = auth_header(token)
    page = client.get(f"{API}/products", params={"page_size": 3}, headers=h).json()
    assert page["total"] == 4 and len(page["items"]) == 3 and page["page"] == 1
    page2 = client.get(f"{API}/products", params={"page_size": 3, "page": 2}, headers=h).json()
    assert len(page2["items"]) == 1
    assert client.get(f"{API}/products", params={"q": "panjabi"}, headers=h).json()["total"] == 2
    # % is matched literally, not as a wildcard
    assert client.get(f"{API}/products", params={"q": "100%"}, headers=h).json()["total"] == 1
    assert client.get(f"{API}/products", params={"q": "%"}, headers=h).json()["total"] == 1


@pytest.mark.parametrize(
    "over,fragment",
    [
        ({"name": ""}, "name"),
        ({"name": "   "}, "required"),
        ({"price": 0}, "price"),
        ({"price": -5}, "price"),
        ({"price": 10.123}, "price"),
        ({"stock_count": -1}, "stock_count"),
        ({"stock_count": 1.5}, "stock_count"),
        ({"sizes": ["M", "m"]}, "Duplicate size"),
        ({"colours": ["Red", "Red"]}, "Duplicate colour"),
        ({"sizes": ["  "]}, "must not be blank"),
    ],
)
def test_validation_errors(client, token, over, fragment):
    r = create(client, token, **over)
    assert r.status_code == 422
    assert fragment in str(r.json()["detail"])


def test_sizes_and_colours_are_trimmed(client, token):
    p = create(client, token, sizes=[" M ", "L"], colours=["  Red"]).json()
    assert p["sizes"] == ["M", "L"] and p["colours"] == ["Red"]


def test_photo_upload_serves_url_and_limits_to_five(client, token):
    h = auth_header(token)
    pid = create(client, token).json()["id"]
    r = upload(client, token, pid, PNG, JPG)
    assert r.status_code == 200
    urls = r.json()["photos"]
    assert len(urls) == 2 and urls[0].startswith(get_settings().backend_public_url)
    assert urls[0].endswith(".png") and urls[1].endswith(".jpg")
    served = client.get("/media/" + urls[0].split("/media/")[1])
    assert served.status_code == 200 and served.content == PNG  # reachable by URL

    assert upload(client, token, pid, PNG, PNG, PNG).status_code == 200  # now 5
    sixth = upload(client, token, pid, PNG)
    assert sixth.status_code == 422 and "at most 5" in sixth.json()["detail"]
    assert len(client.get(f"{API}/products/{pid}", headers=h).json()["photos"]) == 5


def test_upload_rejects_non_images_all_or_nothing(client, token):
    pid = create(client, token).json()["id"]
    r = upload(client, token, pid, PNG, b"<html>not an image</html>")
    assert r.status_code == 422 and "JPEG, PNG or WebP" in r.json()["detail"]
    assert client.get(f"{API}/products/{pid}", headers=auth_header(token)).json()["photos"] == []


def test_upload_rejects_oversize(client, token, monkeypatch):
    pid = create(client, token).json()["id"]
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    try:
        big = upload(client, token, pid, b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10))
        assert big.status_code == 422 and "larger than" in big.json()["detail"]
    finally:
        monkeypatch.delenv("MAX_UPLOAD_MB")
        get_settings.cache_clear()


def test_remove_photo_deletes_file(client, token):
    pid = create(client, token).json()["id"]
    urls = upload(client, token, pid, PNG, JPG).json()["photos"]
    first = media_path(urls[0])
    assert first.exists()
    r = client.delete(f"{API}/products/{pid}/photos/0", headers=auth_header(token))
    assert r.status_code == 200 and r.json()["photos"] == [urls[1]]
    assert not first.exists()
    assert client.delete(f"{API}/products/{pid}/photos/5", headers=auth_header(token)).status_code == 404


def test_delete_product_removes_stored_photos(client, token):
    pid = create(client, token).json()["id"]
    urls = upload(client, token, pid, PNG, JPG).json()["photos"]
    files = [media_path(u) for u in urls]
    assert all(f.exists() for f in files)
    assert client.delete(f"{API}/products/{pid}", headers=auth_header(token)).status_code == 204
    assert not any(f.exists() for f in files)


def test_shop_a_cannot_touch_shop_b_products(client):
    a = signup(client, "a@example.com", "Shop A")
    b = signup(client, "b@example.com", "Shop B")
    pid = create(client, b).json()["id"]
    ha = auth_header(a)
    assert client.get(f"{API}/products/{pid}", headers=ha).status_code == 404
    assert client.put(f"{API}/products/{pid}", json=product_body(name="Hacked"), headers=ha).status_code == 404
    assert client.delete(f"{API}/products/{pid}", headers=ha).status_code == 404
    assert upload(client, a, pid, PNG).status_code == 404
    assert client.delete(f"{API}/products/{pid}/photos/0", headers=ha).status_code == 404
    assert client.get(f"{API}/products", headers=ha).json()["total"] == 0
    assert client.get(f"{API}/products/{pid}", headers=auth_header(b)).json()["name"] == "Red Jamdani Saree"


def test_moderator_gets_403_and_anonymous_401(client, token):
    client.post(
        f"{API}/shop/staff",
        json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD},
        headers=auth_header(token),
    )
    mod = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    h = auth_header(mod)
    assert client.get(f"{API}/products", headers=h).status_code == 403
    assert client.post(f"{API}/products", json=product_body(), headers=h).status_code == 403
    assert client.get(f"{API}/products").status_code == 401


def test_change_hooks_are_called(client, token, monkeypatch):
    from app.services import products as svc

    calls = []
    monkeypatch.setattr(svc.product_hooks, "product_changed", lambda s, p: calls.append(("changed", p)))
    monkeypatch.setattr(svc.product_hooks, "product_deleted", lambda s, p: calls.append(("deleted", p)))
    pid = create(client, token).json()["id"]
    client.put(f"{API}/products/{pid}", json=product_body(name="X"), headers=auth_header(token))
    client.delete(f"{API}/products/{pid}", headers=auth_header(token))
    assert calls == [("changed", pid), ("changed", pid), ("deleted", pid)]


def test_seed_creates_demo_products_idempotently(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password-1")
    assert cli_main(["seed"]) == 0
    products = db.scalars(select(Product)).all()
    assert len(products) >= 8
    assert any(p.stock_count == 0 for p in products)
    assert any(p.name == "Red Jamdani Saree" for p in products)
    assert any(len(p.sizes) >= 3 for p in products)  # panjabi in several sizes
    owner_shops = {u.shop_id for u in db.scalars(select(User).where(User.role == "owner"))}
    assert {p.shop_id for p in products} <= owner_shops
    assert cli_main(["seed"]) == 0
    db.expire_all()
    assert len(db.scalars(select(Product)).all()) == len(products)
