"""Second set of screenshots: detail pages and interactive flows."""
from pathlib import Path

from playwright.sync_api import sync_playwright

from shots_common import PW, BASE, OUT, gray, login, snap

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    c = b.new_context(viewport={"width": 1366, "height": 800}, locale="en-US")
    pg = c.new_page()
    login(pg, "rina.demo@example.com")
    snap(pg, "inbox_chat", "/dashboard/inbox/87", True)
    snap(pg, "order_detail", "/dashboard/orders/24", True)
    snap(pg, "orders_confirmed", "/dashboard/orders", False)
    snap(pg, "products_import", "/dashboard/products", True)
    # notification bell
    pg.goto(f"{BASE}/dashboard")
    pg.wait_for_load_state("networkidle")
    pg.click("button[aria-label*=otification]")
    pg.wait_for_timeout(800)
    p = OUT / "notifications.png"
    pg.screenshot(path=str(p)); gray(p)
    # test chat conversation
    pg.goto(f"{BASE}/dashboard/test-chat")
    pg.wait_for_load_state("networkidle")
    pg.get_by_role("button", name="Start new test conversation").first.click()
    pg.wait_for_timeout(1500)
    box = pg.get_by_placeholder("Type a customer message")
    for msg in ["Ami ekta saree chai, 3000 takar moddhe", "Red Jamdani Saree ta nibo, 1ta. Naam Rina, phone 01711223344, Dhaka Mirpur 10"]:
        box.fill(msg)
        box.press("Enter")
        pg.wait_for_timeout(16000)
    p = OUT / "test_chat_conv.png"
    pg.screenshot(path=str(p), full_page=True); gray(p)
    c.close()

    c = b.new_context(viewport={"width": 1366, "height": 800}, locale="en-US")
    pg = c.new_page()
    login(pg, "admin.report@example.com")
    snap(pg, "admin_shop_detail", "/admin/shops/3", True)
    c.close()
    b.close()
