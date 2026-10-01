import io
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Product, Shop
from app.services import products as product_service
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
SAMPLE = Path(__file__).resolve().parents[2] / "database" / "seed" / "sample_products_import.csv"
HEADER = "name,description,price,sizes,colours,stock,photos\n"


def signup(client, email="a@example.com", shop="Shop A"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


@pytest.fixture
def token(client):
    return signup(client)


def post_file(client, token, filename, data, content_type="application/octet-stream"):
    return client.post(
        f"{API}/products/import",
        files={"file": (filename, data, content_type)},
        headers=auth_header(token),
    )


def xlsx_bytes(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_template_download(client, token):
    r = client.get(f"{API}/products/import/template", headers=auth_header(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "name,description,price,sizes,colours,stock,photos"
    assert len(lines) == 2
    # the template itself imports cleanly
    res = post_file(client, token, "t.csv", r.content).json()
    assert (res["rows_read"], res["imported"], res["failed"]) == (1, 1, 0)


def test_csv_all_valid(client, token, db):
    csv = HEADER + (
        'Cotton Panjabi,Everyday,1850,M|L|XL,White|Navy,24,https://example.com/a.jpg|https://example.com/b.jpg\n'
        'Silk Saree,Fancy,"4,800","S,M",Red,3,\n'
        "Plain Mug,,150,,,0,\n"
    )
    r = post_file(client, token, "p.csv", csv.encode())
    assert r.status_code == 200
    body = r.json()
    assert (body["rows_read"], body["imported"], body["failed"], body["failures"]) == (3, 3, 0, [])
    by_name = {p.name: p for p in db.scalars(select(Product))}
    pj = by_name["Cotton Panjabi"]
    assert pj.sizes == ["M", "L", "XL"] and pj.colours == ["White", "Navy"] and pj.stock_count == 24
    assert pj.photos == ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    assert float(by_name["Silk Saree"].price) == 4800 and by_name["Silk Saree"].sizes == ["S", "M"]
    assert by_name["Plain Mug"].stock_count == 0 and by_name["Plain Mug"].description == ""


def test_imported_photo_urls_come_back_as_given(client, token):
    csv = HEADER + "Item,,100,,,1,https://example.com/a.jpg\n"
    post_file(client, token, "p.csv", csv.encode())
    listed = client.get(f"{API}/products", headers=auth_header(token)).json()["items"]
    assert listed[0]["photos"] == ["https://example.com/a.jpg"]


def test_mixed_rows_report_row_numbers_and_reasons(client, token, db):
    csv = HEADER + (
        "Good One,,100,,,5,\n"  # row 2
        ",No name,100,,,5,\n"  # row 3
        "Free Item,,0,,,5,\n"  # row 4
        "Bad Price,,abc,,,5,\n"  # row 5
        "Neg Stock,,10,,,-1,\n"  # row 6
        "Dupes,,10,M|m,,1,\n"  # row 7
        "Many Photos,,10,,,1," + "|".join(f"https://x.com/{i}.jpg" for i in range(6)) + "\n"  # row 8
        "Not A Url,,10,,,1,ftp://x/y.jpg\n"  # row 9
        ",Two problems,-5,,,1,\n"  # row 10
        "Good Two,,20,,,0,\n"  # row 11
    )
    body = post_file(client, token, "p.csv", csv.encode()).json()
    assert (body["rows_read"], body["imported"], body["failed"]) == (10, 2, 8)
    fails = {f["row"]: f for f in body["failures"]}
    assert sorted(fails) == [3, 4, 5, 6, 7, 8, 9, 10]
    assert fails[3]["reasons"] == ["missing name"]
    assert fails[4]["reasons"] == ["price must be greater than 0"]
    assert "price" in fails[5]["reasons"][0]
    assert fails[6]["reasons"] == ["stock must be greater than or equal to 0"]
    assert fails[7]["reasons"] == ["Duplicate size: m"]
    assert fails[8]["reasons"] == ["more than 5 photos"]
    assert "valid http(s) URL" in fails[9]["reasons"][0]
    assert fails[10]["name"] == "" and set(fails[10]["reasons"]) == {"missing name", "price must be greater than 0"}
    assert sorted(p.name for p in db.scalars(select(Product))) == ["Good One", "Good Two"]


def test_sample_file_in_seed_folder(client, token):
    body = post_file(client, token, "sample_products_import.csv", SAMPLE.read_bytes()).json()
    assert (body["rows_read"], body["imported"], body["failed"]) == (11, 4, 7)
    assert [f["row"] for f in body["failures"]] == [4, 5, 6, 7, 8, 9, 12]


def test_xlsx_import(client, token, db):
    data = xlsx_bytes(
        [
            ["Name", " Description", "PRICE", "sizes", "colours", "stock", "photos", "ignored extra"],
            ["Excel Shirt", "From Excel", 1250.5, "M|L", "Blue", 12, None, "x"],
            ["Excel Mug", None, 300, None, None, 0, None, None],
            [None, "no name", 100, None, None, 1, None, None],
            [None, None, None, None, None, None, None, None],  # blank row ignored
            ["Bad Stock", None, 100, None, None, 1.5, None, None],
        ]
    )
    body = post_file(client, token, "p.xlsx", data).json()
    assert (body["rows_read"], body["imported"], body["failed"]) == (4, 2, 2)
    assert [f["row"] for f in body["failures"]] == [4, 6]  # Excel row numbers (header is row 1)
    shirt = db.scalar(select(Product).where(Product.name == "Excel Shirt"))
    assert float(shirt.price) == 1250.5 and shirt.stock_count == 12 and shirt.sizes == ["M", "L"]


def test_missing_required_columns(client, token):
    r = post_file(client, token, "p.csv", b"name,stock\nShirt,3\n")
    assert r.status_code == 400
    assert "Missing required column" in r.json()["detail"] and "price" in r.json()["detail"]
    r = post_file(client, token, "p.xlsx", xlsx_bytes([["title", "cost"], ["a", 1]]))
    assert r.status_code == 400 and "Missing required column" in r.json()["detail"]


@pytest.mark.parametrize(
    "filename,data,fragment",
    [
        ("p.txt", b"name,price\na,1\n", "Only .csv and .xlsx"),
        ("p.xls", b"whatever", "Only .csv and .xlsx"),
        ("p.csv", b"", "empty"),
        ("p.csv", HEADER.encode(), "no product rows"),
        ("p.xlsx", b"not a zip file", "not a valid .xlsx"),
        ("p.csv", b"\xff\xfe\x00bad bytes \x80\x81", "UTF-8"),
    ],
)
def test_bad_files_rejected_with_clear_error(client, token, db, filename, data, fragment):
    r = post_file(client, token, filename, data)
    assert r.status_code in (400, 413)
    assert fragment in r.json()["detail"]
    assert db.scalar(select(Product.id)) is None


def test_file_too_large_and_too_many_rows(client, token, monkeypatch):
    monkeypatch.setenv("MAX_IMPORT_MB", "1")
    monkeypatch.setenv("MAX_IMPORT_ROWS", "2")
    get_settings.cache_clear()
    try:
        three = HEADER + "a,,1,,,1,\nb,,1,,,1,\nc,,1,,,1,\n"
        r = post_file(client, token, "p.csv", three.encode())
        assert r.status_code == 413 and "more than 2 rows" in r.json()["detail"]
        big = (HEADER + "a," + "x" * (1024 * 1024) + ",1,,,1,\n").encode()
        r = post_file(client, token, "p.csv", big)
        assert r.status_code == 413 and "larger than 1 MB" in r.json()["detail"]
    finally:
        monkeypatch.delenv("MAX_IMPORT_MB")
        monkeypatch.delenv("MAX_IMPORT_ROWS")
        get_settings.cache_clear()


def test_imported_products_belong_only_to_importers_shop(client, db):
    a = signup(client, "a@example.com", "Shop A")
    b = signup(client, "b@example.com", "Shop B")
    post_file(client, a, "p.csv", (HEADER + "A Item,,100,,,1,\n").encode())
    shop_a = db.scalar(select(Shop.id).where(Shop.name == "Shop A"))
    assert [(p.name, p.shop_id) for p in db.scalars(select(Product))] == [("A Item", shop_a)]
    assert client.get(f"{API}/products", headers=auth_header(b)).json()["total"] == 0
    assert client.get(f"{API}/products", headers=auth_header(a)).json()["total"] == 1


def test_import_uses_product_service_and_its_hook(client, token, monkeypatch):
    calls = []
    monkeypatch.setattr(product_service.product_hooks, "product_changed", lambda s, p: calls.append(p))
    post_file(client, token, "p.csv", (HEADER + "One,,10,,,1,\nTwo,,10,,,1,\n,bad,10,,,1,\n").encode())
    assert len(calls) == 2  # one per imported product, none for the failed row


def test_moderator_and_anonymous_cannot_import(client, token):
    client.post(
        f"{API}/shop/staff",
        json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD},
        headers=auth_header(token),
    )
    mod = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    assert post_file(client, mod, "p.csv", (HEADER + "A,,1,,,1,\n").encode()).status_code == 403
    assert client.get(f"{API}/products/import/template", headers=auth_header(mod)).status_code == 403
    assert client.post(f"{API}/products/import", files={"file": ("p.csv", b"x")}).status_code == 401
    assert client.get(f"{API}/products/import/template").status_code == 401
