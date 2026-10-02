"""Captures real screenshots of the running local app (grayscale) into docs/report/shots/."""
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "shots"
OUT.mkdir(exist_ok=True)
BASE = "http://localhost:3000"
PW = "report-demo-pass-1"


def gray(path):
    Image.open(path).convert("L").convert("RGB").save(path)


def login(page, email):
    page.goto(f"{BASE}/login")
    page.fill("input[type=email]", email)
    page.fill("input[type=password]", PW)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)


def snap(page, name, url=None, full=False, wait=1500):
    if url:
        page.goto(f"{BASE}{url}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(wait)
    p = OUT / f"{name}.png"
    page.screenshot(path=str(p), full_page=full)
    gray(p)
    print("shot", name)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    def ctx(w=1366, h=800, mobile=False):
        return b.new_context(viewport={"width": w, "height": h}, locale="en-US")

    # public pages
    c = ctx(); pg = c.new_page()
    snap(pg, "login", "/login")
    snap(pg, "signup", "/signup")
    snap(pg, "forgot", "/forgot-password")
    c.close()

    # owner
    c = ctx(); pg = c.new_page()
    login(pg, "rina.demo@example.com")
    for name, url, full in [
        ("dashboard", "/dashboard", False), ("products", "/dashboard/products", False),
        ("product_new", "/dashboard/products/new", True), ("policy", "/dashboard/policy", True),
        ("test_chat", "/dashboard/test-chat", False), ("facebook", "/dashboard/facebook", True),
        ("plan", "/dashboard/plan", True), ("staff", "/dashboard/staff", True),
        ("inbox", "/dashboard/inbox", False), ("orders", "/dashboard/orders", False),
        ("reports", "/dashboard/reports", True), ("settings", "/dashboard/settings", True),
    ]:
        snap(pg, name, url, full)
    c.close()

    # mobile owner
    c = ctx(375, 812); pg = c.new_page()
    login(pg, "rina.demo@example.com")
    snap(pg, "m_dashboard", "/dashboard")
    snap(pg, "m_products", "/dashboard/products")
    snap(pg, "m_orders", "/dashboard/orders")
    c.close()

    # moderator
    c = ctx(); pg = c.new_page()
    login(pg, "mod.report@example.com")
    snap(pg, "mod_dashboard", "/dashboard/inbox")
    c.close()

    # admin
    c = ctx(); pg = c.new_page()
    login(pg, "admin.report@example.com")
    for name, url in [("admin_shops", "/admin"), ("admin_plans", "/admin/plans"), ("admin_ai", "/admin/ai-usage"), ("admin_health", "/admin/health")]:
        snap(pg, name, url)
    c.close()
    b.close()
