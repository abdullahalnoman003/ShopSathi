from playwright.sync_api import sync_playwright
from PIL import Image
from shots_common import BASE, OUT, gray, login
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    c = b.new_context(viewport={"width": 1366, "height": 800}, locale="en-US")
    pg = c.new_page()
    login(pg, "rina.demo@example.com")
    pg.goto(f"{BASE}/dashboard/orders"); pg.wait_for_load_state("networkidle")
    pg.get_by_role("button", name="Confirmed").click(); pg.wait_for_timeout(1500)
    p = OUT / "orders_confirmed.png"; pg.screenshot(path=str(p)); gray(p)
    pg.goto(f"{BASE}/dashboard/inbox"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1200)
    pg.get_by_role("button", name="Flagged").click(); pg.wait_for_timeout(1200)
    p = OUT / "inbox_flagged.png"; pg.screenshot(path=str(p)); gray(p)
    pg.goto(f"{BASE}/dashboard/products/15"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1500)
    p = OUT / "product_edit.png"; pg.screenshot(path=str(p), full_page=True); gray(p)
    pg.goto(f"{BASE}/dashboard"); pg.wait_for_load_state("networkidle")
    pg.click("button[aria-label*=otification]"); pg.wait_for_timeout(800)
    p = OUT / "notifications.png"; pg.screenshot(path=str(p)); gray(p)
    c.close(); b.close()
im = Image.open(OUT / "notifications.png"); im.crop((0, 0, 700, 330)).save(OUT / "notifications.png")
im = Image.open(OUT / "product_edit.png"); 
