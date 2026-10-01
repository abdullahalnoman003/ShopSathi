import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult
from sqlalchemy import select

from app.cli import main as cli_main
from app.models import AiUsageLog, Chat, Message, Shop, WeeklyInsight
from app.services.insights import InsightsService, monday_of, previous_week_start, week_window
from app.workers.celery_app import celery_app
from app.workers.tasks import generate_weekly_insights
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
DHAKA = ZoneInfo("Asia/Dhaka")
WEEK = date(2026, 3, 9)  # a Monday


class ScriptedInsightsLLM(LLMProvider):
    name, model = "scripted", "scripted-1"

    def __init__(self, questions=None, products=None, fail=False):
        self.questions = questions if questions is not None else [{"question": "Asks the price of a product", "count": 4}]
        self.products = products if products is not None else [{"name": "laptop", "count": 3}]
        self.fail = fail
        self.prompts: list[str] = []

    def generate_json_with_usage(self, system_prompt, user_prompt, *, task="generic"):
        self.prompts.append(user_prompt)
        if self.fail:
            raise LLMProviderError("model down")
        if task == "insights_map":
            return LLMResult({"questions": self.questions, "products": self.products}, 100, 20, self.name, self.model)
        return LLMResult({"questions": self.questions}, 50, 10, self.name, self.model)


def signup(client, email="a@example.com", shop="Shop A"):
    return client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD}).json()["access_token"]


def add_product(client, token, name):
    r = client.post(f"{API}/products", json={"name": name, "description": "", "price": 100, "sizes": [], "colours": [], "stock_count": 5}, headers=auth_header(token))
    assert r.status_code == 201, r.text


def chat_with(db, sid, texts, *, day=WEEK, hour=12, channel="messenger", psid="p", name=None, sender="customer"):
    c = Chat(shop_id=sid, channel=channel, customer_psid=psid if channel == "messenger" else None, customer_name=name)
    db.add(c)
    db.flush()
    for i, t in enumerate(texts):
        at = datetime.combine(day, time(hour, i), tzinfo=DHAKA)
        db.add(Message(shop_id=sid, chat_id=c.id, sender=sender, text=t, created_at=at, received_at=at if sender == "customer" else None))
    db.commit()
    return c


@pytest.fixture
def shop(client, db):
    token = signup(client)
    return token, db.scalar(select(Shop.id))


def rows(db):
    db.expire_all()
    return list(db.scalars(select(WeeklyInsight).order_by(WeeklyInsight.id)))


# ----------------------------------------------------------------------- week helpers


def test_week_helpers():
    assert monday_of(date(2026, 3, 15)) == WEEK and monday_of(WEEK) == WEEK
    # Monday 2026-03-16 02:00 in Dhaka: the previous complete week starts 03-09
    assert previous_week_start(datetime(2026, 3, 16, 2, 0, tzinfo=DHAKA)) == WEEK
    assert previous_week_start(datetime(2026, 3, 15, 23, 59, tzinfo=DHAKA)) == date(2026, 3, 2)
    start, end = week_window(WEEK)
    assert start == datetime(2026, 3, 9, 0, 0, tzinfo=DHAKA) and end == datetime(2026, 3, 16, 0, 0, tzinfo=DHAKA)


# ----------------------------------------------------------------------- generation


def test_generation_from_seeded_chats_stores_the_summary_and_logs_usage(client, db, shop):
    token, sid = shop
    add_product(client, token, "Red Jamdani Saree")
    chat_with(db, sid, ["Red Jamdani Saree price koto?", "do you have a laptop?"] + [f"more question number {i}" for i in range(12)])
    llm = ScriptedInsightsLLM(
        questions=[{"question": f"Question {i}", "count": 10 - i} for i in range(7)],
        products=[{"name": "laptop", "count": 3}, {"name": "Red Jamdani Saree", "count": 5}, {"name": "jamdani saree", "count": 2}],
    )
    before = len(db.scalars(select(AiUsageLog)).all())
    row = InsightsService(db, llm).generate_for_shop(sid, WEEK)

    assert row.shop_id == sid and row.week_start == WEEK
    assert [q["question"] for q in row.top_questions] == [f"Question {i}" for i in range(5)]  # at most 5, most asked first
    assert row.top_questions[0] == {"question": "Question 0", "count": 10}
    assert row.missing_products == [{"name": "laptop", "count": 3}]  # the saree is in the catalogue
    logs = db.scalars(select(AiUsageLog).where(AiUsageLog.operation == "weekly_insights")).all()
    assert len(logs) >= 1 and all(l.shop_id == sid and l.input_tokens > 0 for l in logs)
    assert any(l.model == "scripted-1" for l in logs)
    assert len(db.scalars(select(AiUsageLog)).all()) > before


def test_a_week_has_one_row_per_shop_and_regenerating_updates_it(client, db, shop):
    _, sid = shop
    chat_with(db, sid, ["price koto?"])
    svc = InsightsService(db, ScriptedInsightsLLM(products=[]))
    first = svc.generate_for_shop(sid, WEEK)
    again = InsightsService(db, ScriptedInsightsLLM(questions=[{"question": "A newer question", "count": 1}], products=[])).generate_for_shop(sid, WEEK)
    assert first.id == again.id and len(rows(db)) == 1
    assert rows(db)[0].top_questions == [{"question": "A newer question", "count": 1}]
    svc.generate_for_shop(sid, WEEK + timedelta(days=7))
    assert len(rows(db)) == 2


def test_only_this_shops_messenger_customer_messages_of_that_week_are_used(client, db, shop):
    token, sid = shop
    signup(client, "b@example.com", "Shop B")
    other = db.scalar(select(Shop.id).where(Shop.name == "Shop B"))
    chat_with(db, sid, ["MINE price koto?"], psid="a1")
    chat_with(db, other, ["THEIRS secret question"], psid="b1")
    chat_with(db, sid, ["TESTCHAT question"], channel="test")
    chat_with(db, sid, ["AIREPLY text"], sender="ai", psid="a2")
    chat_with(db, sid, ["SELLERREPLY text"], sender="seller", psid="a3")
    chat_with(db, sid, ["LASTWEEK question"], day=WEEK - timedelta(days=1), hour=23, psid="a4")  # Sunday before
    chat_with(db, sid, ["NEXTWEEK question"], day=WEEK + timedelta(days=7), hour=0, psid="a5")  # next Monday 00:xx
    chat_with(db, sid, ["SUNDAYEND question"], day=WEEK + timedelta(days=6), hour=23, psid="a6")  # last day: included
    chat_with(db, sid, ["MONDAYSTART question"], day=WEEK, hour=0, psid="a7")  # first minute: included
    llm = ScriptedInsightsLLM()
    InsightsService(db, llm).generate_for_shop(sid, WEEK)
    sent = "\n".join(llm.prompts)
    assert "MINE" in sent and "SUNDAYEND" in sent and "MONDAYSTART" in sent
    for leaked in ("THEIRS", "TESTCHAT", "AIREPLY", "SELLERREPLY", "LASTWEEK", "NEXTWEEK"):
        assert leaked not in sent


def test_customer_names_and_phone_numbers_never_reach_the_model(client, db, shop):
    _, sid = shop
    chat_with(db, sid, ["Hi I am Nasrin, saree price?", "call 01712345678", "my name is Rahim Uddin", "address House 5 Road 3 Dhanmondi"], name="Nasrin Sultana", psid="x1")
    llm = ScriptedInsightsLLM()
    InsightsService(db, llm).generate_for_shop(sid, WEEK)
    sent = "\n".join(llm.prompts)
    for secret in ("Nasrin", "01712345678", "Rahim", "Dhanmondi"):
        assert secret not in sent
    assert "saree price?" in sent


def test_a_week_without_messages_gets_an_empty_summary_without_calling_the_model(client, db, shop):
    _, sid = shop
    llm = ScriptedInsightsLLM()
    row = InsightsService(db, llm).generate_for_shop(sid, WEEK)
    assert row.top_questions == [] and row.missing_products == [] and llm.prompts == []
    assert db.scalars(select(AiUsageLog).where(AiUsageLog.operation == "weekly_insights")).all() == []


def test_the_week_must_start_on_a_monday(db, shop):
    with pytest.raises(ValueError):
        InsightsService(db, ScriptedInsightsLLM()).generate_for_shop(shop[1], date(2026, 3, 10))


def test_a_dead_model_stores_nothing(db, shop):
    _, sid = shop
    chat_with(db, sid, ["price koto?"])
    with pytest.raises(LLMProviderError):
        InsightsService(db, ScriptedInsightsLLM(fail=True)).generate_for_shop(sid, WEEK)
    assert rows(db) == []


def test_product_existence_is_decided_by_the_catalogue_not_the_model(client, db, shop):
    token, sid = shop
    for name in ("Wireless Earbuds", "Smart Watch"):
        add_product(client, token, name)
    chat_with(db, sid, [f"earbuds ache {i}?" for i in range(12)])
    llm = ScriptedInsightsLLM(products=[{"name": "earbuds", "count": 5}, {"name": "Smart Watch", "count": 4}, {"name": "laptop", "count": 3}, {"name": "drone", "count": 1}])
    row = InsightsService(db, llm).generate_for_shop(sid, WEEK)
    assert [p["name"] for p in row.missing_products] == ["laptop", "drone"]


# ----------------------------------------------------------------------- the weekly job


def test_the_job_covers_active_shops_skips_done_ones_and_survives_failures(client, db, shop):
    _, sid = shop
    signup(client, "b@example.com", "Shop B")
    signup(client, "c@example.com", "Shop C")
    b, c = (db.scalar(select(Shop.id).where(Shop.name == n)) for n in ("Shop B", "Shop C"))
    db.get(Shop, c).status = "suspended"
    db.commit()
    for s in (sid, b, c):
        chat_with(db, s, ["price koto?"], psid=f"p{s}")

    svc = InsightsService(db, ScriptedInsightsLLM())
    out = svc.generate_for_all(WEEK)
    assert out == {"generated": 2, "skipped": 0, "failed": 0}  # the suspended shop is not processed
    assert {r.shop_id for r in rows(db)} == {sid, b}
    assert svc.generate_for_all(WEEK) == {"generated": 0, "skipped": 2, "failed": 0}  # repeating does no AI work
    assert svc.generate_for_all(WEEK, replace=True)["generated"] == 2

    # one failing shop does not stop the others
    db.execute(WeeklyInsight.__table__.delete())
    db.commit()
    broken = InsightsService(db, ScriptedInsightsLLM(fail=True))
    assert broken.generate_for_all(WEEK) == {"generated": 0, "skipped": 0, "failed": 2}
    assert rows(db) == []


def test_the_celery_task_and_beat_schedule(client, db, shop, monkeypatch):
    _, sid = shop
    chat_with(db, sid, ["price koto?"])
    entry = celery_app.conf.beat_schedule["weekly-insights"]
    assert entry["task"] == "shopsathi.generate_weekly_insights"
    assert str(entry["schedule"].day_of_week) == "{0}" and str(entry["schedule"].hour) == "{20}"  # Sunday 20:00 UTC = Monday 02:00 Dhaka
    assert "shopsathi.generate_weekly_insights" in celery_app.tasks
    out = generate_weekly_insights(WEEK.isoformat())  # the offline test provider (mock) answers
    assert out["generated"] == 1 and len(rows(db)) == 1


# ----------------------------------------------------------------------- the command line


def test_cli_generates_and_prints(client, db, shop, capsys):
    _, sid = shop
    chat_with(db, sid, ["Red Saree price koto?", "delivery charge koto?"])
    assert cli_main(["generate-insights", "--shop-id", str(sid), "--week-start", WEEK.isoformat()]) == 0
    out = capsys.readouterr().out
    assert "Top questions" in out and "does not have" in out
    assert len(rows(db)) == 1
    assert cli_main(["generate-insights", "--shop-id", str(sid), "--week-start", "2026-03-10"]) == 2  # not a Monday
    assert cli_main(["generate-insights", "--shop-id", "9999", "--week-start", WEEK.isoformat()]) == 2


# ----------------------------------------------------------------------- API


def put(db, sid, week=WEEK, q=None, m=None):
    db.add(WeeklyInsight(shop_id=sid, week_start=week, top_questions=q or [{"question": "Asks the price", "count": 4}], missing_products=m or [{"name": "laptop", "count": 2}]))
    db.commit()


def test_list_and_read_weekly_insights(client, db, shop):
    token, sid = shop
    h = auth_header(token)
    assert client.get(f"{API}/reports/weekly-insights", headers=h).json() == []
    put(db, sid, WEEK)
    put(db, sid, WEEK + timedelta(days=7), q=[{"question": "Newer", "count": 1}], m=[])
    weeks = client.get(f"{API}/reports/weekly-insights", headers=h).json()
    assert [w["week_start"] for w in weeks] == ["2026-03-16", "2026-03-09"] and weeks[1]["week_end"] == "2026-03-15"
    one = client.get(f"{API}/reports/weekly-insights/2026-03-09", headers=h).json()
    assert one["top_questions"] == [{"question": "Asks the price", "count": 4}] and one["missing_products"] == [{"name": "laptop", "count": 2}]
    assert one["week_start"] == "2026-03-09" and one["week_end"] == "2026-03-15" and one["generated_at"]
    assert client.get(f"{API}/reports/weekly-insights/2026-03-23", headers=h).status_code == 404
    assert client.get(f"{API}/reports/weekly-insights/2026-03-10", headers=h).status_code == 422  # not a Monday
    assert client.get(f"{API}/reports/weekly-insights/nope", headers=h).status_code == 422


def test_weekly_insights_are_private_to_the_shop_and_owner_only(client, db, shop, monkeypatch):
    token, sid = shop
    other_token = signup(client, "b@example.com", "Shop B")
    put(db, db.scalar(select(Shop.id).where(Shop.name == "Shop B")), q=[{"question": "B secret", "count": 9}])
    assert client.get(f"{API}/reports/weekly-insights", headers=auth_header(token)).json() == []
    assert client.get(f"{API}/reports/weekly-insights/2026-03-09", headers=auth_header(token)).status_code == 404
    assert "B secret" in client.get(f"{API}/reports/weekly-insights/2026-03-09", headers=auth_header(other_token)).text

    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(token))
    mod = auth_header(client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"])
    assert client.get(f"{API}/reports/weekly-insights", headers=mod).status_code == 403
    assert client.get(f"{API}/reports/weekly-insights/2026-03-09", headers=mod).status_code == 403
    assert client.get(f"{API}/reports/weekly-insights").status_code == 401
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    admin = auth_header(client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"])
    assert client.get(f"{API}/reports/weekly-insights", headers=admin).status_code == 403


def test_deleting_a_shop_removes_its_insights(client, db, shop):
    _, sid = shop
    put(db, sid)
    db.delete(db.get(Shop, sid))
    db.commit()
    assert rows(db) == []
