"""The load-test tools themselves (scripts/loadtest): the percentile maths, the signed events they send, and the stub
Send API they send replies to. The load test is only as trustworthy as these."""

import json

import pytest
from fastapi.testclient import TestClient

from app.integrations.facebook.webhook import verify_signature
from scripts.loadtest import run_loadtest as lt
from scripts.loadtest import stub_send_api as stub

API = "/api/v1"


def test_percentiles():
    data = [float(x) for x in range(1, 101)]  # 1..100
    assert lt.percentile(data, 50) == pytest.approx(50.5)
    assert lt.percentile(data, 90) == pytest.approx(90.1)
    assert lt.percentile(data, 100) == 100 and lt.percentile(data, 0) == 1
    assert lt.percentile([7.0], 99) == 7.0 and lt.percentile([], 50) is None
    assert lt.percentile([5, 1, 3], 50) == 3  # unsorted input is fine
    s = lt.summary([1000.0, 2000.0, 3000.0])
    assert s["n"] == 3 and s["p50"] == 2000 and s["max"] == 3000 and s["mean"] == 2000
    assert lt.summary([])["p50"] is None


def test_events_are_signed_like_metas_and_accepted_by_the_webhook(client):
    secret = "test-app-secret"
    body = lt.event("some-page", "customer-1", "m_1", "Cotton Panjabi er dam koto?")
    r = client.post(f"{API}/webhooks/messenger", content=body, headers={"X-Hub-Signature-256": lt.sign(secret, body), "Content-Type": "application/json"})
    assert r.status_code == 200  # (the Page is unknown here, so nothing is stored: the point is the signature)
    assert verify_signature(secret, body, lt.sign(secret, body))
    payload = json.loads(body)
    msg = payload["entry"][0]["messaging"][0]
    assert msg["sender"]["id"] == "customer-1" and msg["recipient"]["id"] == "some-page" and msg["message"]["text"] == "Cotton Panjabi er dam koto?"


def test_bangla_text_survives_the_event_encoding():
    body = lt.event("p", "c", "m", "দাম কত?")
    assert "দাম কত?" in body.decode("utf-8") and json.loads(body)["entry"][0]["messaging"][0]["message"]["text"] == "দাম কত?"


def test_the_question_lists_are_usable():
    for pool in (lt.QUESTIONS, lt.SIMPLE_QUESTIONS):
        assert len(set(pool)) == len(pool) and len(pool) >= 6
        assert all("{p}" in q or "delivery" in q.lower() or "ডেলিভারি" in q or "return" in q or "Cash" in q for q in pool)
    assert all("{p}" in q for q in lt.SIMPLE_QUESTIONS)  # the mock model needs a product name in every question


def test_the_stub_send_api_answers_like_the_send_api_and_counts(monkeypatch):
    monkeypatch.setattr(stub, "LATENCY", 0)
    with TestClient(stub.app) as c:
        c.post("/_reset")
        r = c.post("/v21.0/me/messages", json={"recipient": {"id": "psid-1"}, "messaging_type": "RESPONSE", "message": {"text": "hi"}}, headers={"Authorization": "Bearer LOADTEST-TOKEN-01"})
        assert r.status_code == 200 and r.json()["recipient_id"] == "psid-1" and r.json()["message_id"].startswith("m_stub_")
        c.post("/v21.0/me/messages", json={"recipient": {"id": "psid-1"}, "message": {"attachment": {"type": "image"}}}, headers={"Authorization": "Bearer LOADTEST-TOKEN-02"})
        c.post("/v21.0/me/messages", json={"recipient": {"id": "psid-2"}, "message": {"text": "x"}}, headers={"Authorization": "Bearer LOADTEST-TOKEN-02"})
        stats = c.get("/_stats").json()
        assert (stats["sends"], stats["texts"], stats["images"], stats["recipients"], stats["pages"], stats["max_per_recipient"]) == (3, 2, 1, 2, 2, 2)
        assert c.get("/v21.0/12345").json()["id"] == "12345"  # the customer profile lookup
        assert c.delete("/v21.0/page-1/subscribed_apps").json() == {"success": True}
        c.post("/_reset")
        assert c.get("/_stats").json()["sends"] == 0


def test_the_stub_never_leaves_the_machine():
    """It has no outgoing calls at all: it only answers."""
    import inspect

    source = inspect.getsource(stub)
    assert "httpx" not in source and "requests" not in source and "graph.facebook.com" not in source


def test_the_load_test_refuses_to_run_against_the_real_graph_api(monkeypatch, capsys):
    from app.core.config import get_settings

    monkeypatch.setenv("FB_GRAPH_BASE_URL", "https://graph.facebook.com")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr("sys.argv", ["run_loadtest", "run"])
        assert lt.main() == 2
        assert "only talk to the stub" in capsys.readouterr().err
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
