from pathlib import Path
from PIL import Image
OUT = Path(__file__).parent / "shots"
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
