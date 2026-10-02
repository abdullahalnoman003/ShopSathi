from playwright.sync_api import sync_playwright
from shots_common import BASE, OUT, gray, login, snap
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    c = b.new_context(viewport={"width": 375, "height": 812}, locale="en-US")
    pg = c.new_page()
    login(pg, "rina.demo@example.com")
    pg.goto(f"{BASE}/dashboard/inbox"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1500)
    p = OUT / "m_inbox.png"; pg.screenshot(path=str(p)); gray(p)
    pg.goto(f"{BASE}/dashboard"); pg.wait_for_load_state("networkidle")
    pg.click("button[aria-label*=otification]"); pg.wait_for_timeout(800)
    p = OUT / "m_notifications.png"; pg.screenshot(path=str(p)); gray(p)
    pg.goto(f"{BASE}/dashboard"); pg.wait_for_load_state("networkidle")
    pg.get_by_role("button", name="Menu").click(); pg.wait_for_timeout(600)
    p = OUT / "m_menu.png"; pg.screenshot(path=str(p)); gray(p)
    c.close(); b.close()
