import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.crypto import TokenCipher
from app.integrations.facebook.graph_client import GraphClient
from app.integrations.facebook.messenger_sender import (
    MessengerSender,
    MessengerSendError,
    OutsideMessagingWindow,
    is_public_url,
    split_text,
    window_open,
)
from app.integrations.facebook.webhook import sign, verify_signature
from app.models import AiUsageLog, Chat, FacebookPage, HandoverEvent, Message, Notification, Plan, Product, Shop
from app.services.usage import UsageLimitService
from app.workers.tasks import process_incoming_message
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
URL = f"{API}/webhooks/messenger"
GRAPH = "https://graph.facebook.com/v21.0"
APP_SECRET = "test-app-secret"
PAGE_ID = "1001"
PAGE_TOKEN = "EAAB-page-token-SECRET-for-messenger"
PSID = "5550001"


# ----------------------------------------------------------------------------- helpers


@pytest.fixture
def graph():
    """Facebook's Graph API, mocked. The Send API records every call."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


class SendApi:
    """The mocked Send API: succeeds unless told to fail first."""

    def __init__(self, graph):
        self.plan: list[httpx.Response] = []
        self.route = graph.post(f"{GRAPH}/me/messages").mock(side_effect=self._answer)
        graph.get(url__regex=rf"{re.escape(GRAPH)}/\d+(\?.*)?$").mock(
            return_value=httpx.Response(200, json={"first_name": "Nasrin", "last_name": "Sultana", "id": PSID})
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        if self.plan:
            return self.plan.pop(0)
        return httpx.Response(200, json={"recipient_id": PSID, "message_id": f"m_{len(self.route.calls)}"})

    @property
    def sent(self) -> list[dict]:
        return [json.loads(c.request.content) for c in self.route.calls]

    @property
    def texts(self) -> list[str]:
        return [m["message"]["text"] for m in self.sent if "text" in m["message"]]

    @property
    def images(self) -> list[str]:
        return [m["message"]["attachment"]["payload"]["url"] for m in self.sent if "attachment" in m["message"]]


def error(status: int, code: int, message: str = "error", subcode: int | None = None) -> httpx.Response:
    err = {"message": message, "code": code}
    if subcode:
        err["error_subcode"] = subcode
    return httpx.Response(status, json={"error": err})


@pytest.fixture
def send(graph):
    return SendApi(graph)


def signup(client, email="a@example.com", shop="Rina Fashion House"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


def add_product(client, token, name, price, stock, sizes=(), colours=()):
    r = client.post(
        f"{API}/products",
        json={"name": name, "description": "", "price": price, "sizes": list(sizes), "colours": list(colours), "stock_count": stock},
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def connect_page(db, shop_id, page_id=PAGE_ID, token=PAGE_TOKEN, name="Rina Fashion House"):
    db.add(FacebookPage(shop_id=shop_id, page_id=page_id, page_name=name, encrypted_page_token=TokenCipher().encrypt(token)))
    db.commit()


@pytest.fixture
def shop(client, db):
    """A shop with a product and a connected Facebook Page."""
    token = signup(client)
    add_product(client, token, "Red Jamdani Saree", 4800, 6)
    shop_id = db.scalar(select(Shop.id))
    connect_page(db, shop_id)
    return token, shop_id


def event(text="Red Jamdani Saree price koto?", *, page_id=PAGE_ID, psid=PSID, mid=None, ts=None, attachments=None, echo=False, recipient=None, sticker=False):
    ts = ts if ts is not None else int(time.time() * 1000)
    message: dict = {"mid": mid or f"m_{time.time_ns()}"}
    if attachments:
        message["attachments"] = [{"type": t, "payload": {"url": "https://example.com/x"}} for t in attachments]
        if sticker:
            message["sticker_id"] = 369239263222822
    else:
        message["text"] = text
    if echo:
        message["is_echo"] = True
    sender, rcpt = (page_id, psid) if echo else (psid, recipient or page_id)
    return {"sender": {"id": sender}, "recipient": {"id": rcpt}, "timestamp": ts, "message": message}


def payload(*events, page_id=PAGE_ID):
    return {"object": "page", "entry": [{"id": page_id, "time": int(time.time() * 1000), "messaging": list(events)}]}


def post(client, body: dict, secret=APP_SECRET, signature=None):
    raw = json.dumps(body, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"}
    sig = signature if signature is not None else sign(secret, raw)
    if sig:
        headers["X-Hub-Signature-256"] = sig
    return client.post(URL, content=raw, headers=headers)


def messages(db, chat_id=None):
    db.expire_all()
    q = select(Message).order_by(Message.id)
    return list(db.scalars(q if chat_id is None else q.where(Message.chat_id == chat_id)))


def model_calls(db):
    return db.scalar(select(func.count(AiUsageLog.id)))


def ai_messages(db):
    return [m for m in messages(db) if m.sender == "ai"]


def customer_messages(db):
    return [m for m in messages(db) if m.sender == "customer"]


# ----------------------------------------------------------------------- verification


def test_verification_handshake(client):
    ok = client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": "verify-token-for-tests", "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444" and ok.headers["content-type"].startswith("text/plain")
    for params in (
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
        {"hub.mode": "unsubscribe", "hub.verify_token": "verify-token-for-tests", "hub.challenge": "1"},
        {"hub.mode": "subscribe", "hub.challenge": "1"},
        {},
    ):
        assert client.get(URL, params=params).status_code == 403


def test_verification_needs_a_configured_token(client, monkeypatch):
    monkeypatch.setenv("FB_VERIFY_TOKEN", "")
    get_settings.cache_clear()
    try:
        r = client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
        assert r.status_code == 503 and "FB_VERIFY_TOKEN" in r.json()["detail"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_signature_check_unit():
    body = b'{"a": "b\xc3\xa4"}'
    good = sign("secret", body)
    assert verify_signature("secret", body, good)
    assert not verify_signature("secret", body + b" ", good) and not verify_signature("other", body, good)
    assert not verify_signature("secret", body, None) and not verify_signature("secret", body, "sha256=")
    assert not verify_signature("secret", body, good.replace("sha256=", "sha1=")) and not verify_signature("", body, good)


# ------------------------------------------------------------- what the webhook accepts


def test_bad_or_missing_signature_is_rejected_and_nothing_is_stored(client, shop, db, send):
    body = payload(event())
    assert post(client, body, secret="wrong-secret").status_code == 403
    assert post(client, body, signature="").status_code == 403  # no header at all
    assert post(client, body, signature="sha256=" + "0" * 64).status_code == 403
    raw = json.dumps(body).encode()
    tampered = client.post(URL, content=raw.replace(b"price", b"pr1ce"), headers={"X-Hub-Signature-256": sign(APP_SECRET, raw)})
    assert tampered.status_code == 403
    assert messages(db) == [] and not send.route.calls


def test_a_signed_unicode_message_is_accepted(client, shop, db, send):
    r = post(client, payload(event("লাল শাড়ির দাম কত?")))
    assert r.status_code == 200 and r.json() == {"status": "ok", "received": 1}
    assert customer_messages(db)[0].text == "লাল শাড়ির দাম কত?"


def test_invalid_json_and_other_objects(client, shop, db, send):
    raw = b"not json"
    assert client.post(URL, content=raw, headers={"X-Hub-Signature-256": sign(APP_SECRET, raw)}).status_code == 400
    assert post(client, {"object": "instagram", "entry": []}).json()["received"] == 0
    assert messages(db) == []


def test_echoes_receipts_and_the_pages_own_messages_are_ignored(client, shop, db, send):
    receipt = {"sender": {"id": PSID}, "recipient": {"id": PAGE_ID}, "timestamp": 1, "delivery": {"mids": ["m_1"]}}
    r = post(client, payload(event(echo=True), receipt, event(psid=PAGE_ID)))
    assert r.status_code == 200 and r.json()["received"] == 0
    assert messages(db) == [] and not send.route.calls


def test_events_for_pages_that_are_not_connected_are_ignored(client, shop, db, send):
    r = post(client, payload(event(page_id="999"), page_id="999"))
    assert r.status_code == 200 and r.json()["received"] == 0
    assert messages(db) == [] and db.scalars(select(Chat)).all() == []


# --------------------------------------------------------------------- the whole flow


def test_message_to_reply_through_the_send_api(client, shop, db, send):
    token, shop_id = shop
    before = datetime.now(timezone.utc)
    r = post(client, payload(event(mid="m_abc123")))
    assert r.status_code == 200 and r.json()["received"] == 1

    chat = db.scalars(select(Chat)).one()
    assert (chat.shop_id, chat.channel, chat.customer_psid) == (shop_id, "messenger", PSID)
    assert chat.customer_name == "Nasrin Sultana" and chat.last_customer_message_at is not None
    customer, ai = customer_messages(db)[0], ai_messages(db)[0]
    assert (customer.external_message_id, customer.text, customer.shop_id) == ("m_abc123", "Red Jamdani Saree price koto?", shop_id)
    assert customer.received_at >= before and customer.extras["ai_status"] == "replied"
    assert customer.intent == "price"

    # the reply went to the same customer, as a RESPONSE, with the Page's own token
    (call,) = send.route.calls
    body = json.loads(call.request.content)
    assert body["recipient"] == {"id": PSID} and body["messaging_type"] == "RESPONSE"
    assert "4800" in body["message"]["text"] and body["message"]["text"] == ai.text
    assert call.request.headers["authorization"] == f"Bearer {PAGE_TOKEN}" and PAGE_TOKEN not in str(call.request.url)
    assert "automatic assistant" in ai.text  # first AI reply of the chat

    # sent only after Facebook accepted it; counted once
    assert ai.sent_at is not None and ai.extras["delivery"]["status"] == "sent" and ai.extras["delivery"]["facebook_message_id"].startswith("m_")
    assert UsageLimitService(db).get_usage(shop_id).used == 1
    assert ai.extras["in_reply_to"] == customer.id


def test_timings_are_recorded(client, shop, db, send):
    post(client, payload(event()))
    customer, ai = customer_messages(db)[0], ai_messages(db)[0]
    timings = ai.extras["delivery"]["timings_ms"]
    assert set(timings) == {"queue", "ai", "send", "total"} and all(isinstance(v, int) and v >= 0 for v in timings.values())
    assert timings["total"] >= timings["ai"] + timings["send"] - 5
    assert abs(timings["total"] - int((ai.sent_at - customer.received_at).total_seconds() * 1000)) <= 5  # = sent_at - received_at
    assert ai.sent_at > customer.received_at


def test_a_second_message_reuses_the_chat_and_the_disclosure_comes_once(client, shop, db, send):
    post(client, payload(event("Red Jamdani Saree price koto?")))
    post(client, payload(event("Red Jamdani Saree stock ache?")))
    assert len(db.scalars(select(Chat)).all()) == 1
    texts = send.texts
    assert len(texts) == 2 and "automatic assistant" in texts[0] and "automatic assistant" not in texts[1]
    assert UsageLimitService(db).get_usage(shop[1]).used == 2


def test_the_customers_name_is_optional(client, shop, db, graph):
    send_api = SendApi(graph)
    graph.get(url__regex=rf"{re.escape(GRAPH)}/\d+(\?.*)?$").mock(return_value=error(400, 100, "(#100) Requires pages_user_profile"))
    post(client, payload(event()))
    chat = db.scalars(select(Chat)).one()
    assert chat.customer_name is None and len(send_api.texts) == 1  # no name, the reply still goes out


def test_duplicate_mid_is_processed_once(client, shop, db, send):
    e = event(mid="m_same")
    assert post(client, payload(e)).json()["received"] == 1
    again = post(client, payload(e))
    assert again.status_code == 200 and again.json()["received"] == 0
    assert len(customer_messages(db)) == 1 and len(send.sent) == 1
    assert UsageLimitService(db).get_usage(shop[1]).used == 1


def test_several_events_in_one_request(client, shop, db, send):
    r = post(client, payload(event("Red Jamdani Saree price koto?", mid="m_1"), event("hello", mid="m_2", psid="5550002")))
    assert r.json()["received"] == 2
    assert len(db.scalars(select(Chat)).all()) == 2 and len(send.sent) == 2


# ------------------------------------------------------------------ when the AI must not reply


def test_a_paused_chat_gets_no_ai_reply(client, shop, db, send):
    post(client, payload(event("product ta kharap chilo")))  # complaint: flagged and paused
    sent_before = len(send.sent)
    r = post(client, payload(event("Red Jamdani Saree price koto?")))
    assert r.status_code == 200
    last = customer_messages(db)[-1]
    assert last.extras["ai_status"] == "skipped" and last.extras["ai_skip_reason"] == "ai_paused"
    assert len(send.sent) == sent_before and len(ai_messages(db)) == 1  # kept for the seller, not answered
    assert UsageLimitService(db).get_usage(shop[1]).used == 1  # only the holding reply counted


def test_a_suspended_shop_gets_no_ai_reply(client, shop, db, send):
    calls_before = model_calls(db)
    db.execute(update(Shop).values(status="suspended"))
    db.commit()
    assert post(client, payload(event())).status_code == 200
    assert not send.route.calls and ai_messages(db) == []
    msg = customer_messages(db)[0]
    assert msg.extras["ai_skip_reason"] == "shop_suspended"
    assert model_calls(db) == calls_before  # the AI was not even called


def test_the_monthly_limit_stops_ai_replies(client, shop, db, send):
    token, shop_id = shop
    db.execute(update(Plan).values(monthly_message_limit=2))
    db.commit()
    usage = UsageLimitService(db)
    for _ in range(2):
        usage.record_ai_reply(shop_id)
    assert usage.can_send_ai_reply(shop_id) is False

    assert post(client, payload(event())).status_code == 200
    assert not send.route.calls and ai_messages(db) == []
    assert customer_messages(db)[0].extras["ai_skip_reason"] == "limit_reached"
    assert usage.get_usage(shop_id).used == 2  # unchanged


def test_the_last_message_within_the_limit_is_answered_and_the_next_is_not(client, shop, db, send):
    token, shop_id = shop
    db.execute(update(Plan).values(monthly_message_limit=1))
    db.commit()
    post(client, payload(event("Red Jamdani Saree price koto?")))
    post(client, payload(event("Red Jamdani Saree stock ache?")))
    assert len(send.sent) == 1
    assert [m.extras["ai_status"] for m in customer_messages(db)] == ["replied", "skipped"]
    assert UsageLimitService(db).get_usage(shop_id).used == 1


def test_a_disconnected_page_means_no_reply(client, shop, db, send, monkeypatch):
    monkeypatch.setattr("app.api.v1.routes.webhooks.enqueue", lambda *a: None)  # keep the message waiting
    post(client, payload(event()))
    db.execute(FacebookPage.__table__.delete())
    db.commit()
    process_incoming_message(customer_messages(db)[0].id)
    assert customer_messages(db)[0].extras["ai_skip_reason"] == "no_page" and not send.route.calls


# ----------------------------------------------------------------- the 24-hour window


def test_a_message_older_than_24_hours_is_not_answered(client, shop, db, send):
    old = int((time.time() - 25 * 3600) * 1000)
    assert post(client, payload(event(ts=old))).status_code == 200
    assert not send.route.calls and ai_messages(db) == []
    assert customer_messages(db)[0].extras["ai_skip_reason"] == "outside_window"
    assert UsageLimitService(db).get_usage(shop[1]).used == 0


def test_a_message_just_inside_the_window_is_answered(client, shop, db, send):
    inside = int((time.time() - 23 * 3600) * 1000)
    post(client, payload(event(ts=inside)))
    assert len(send.sent) == 1


def test_window_helper_and_sender_enforce_the_rule_themselves(graph):
    now = datetime.now(timezone.utc)
    assert window_open(now - timedelta(hours=23, minutes=59), now) and not window_open(now - timedelta(hours=24, minutes=1), now)
    assert not window_open(None)
    api = SendApi(graph)
    page = FacebookPage(shop_id=1, page_id=PAGE_ID, page_name="x", encrypted_page_token=TokenCipher().encrypt(PAGE_TOKEN))
    sender = MessengerSender()
    with pytest.raises(OutsideMessagingWindow):
        sender.send_text(page, PSID, "hi", now - timedelta(hours=25))
    with pytest.raises(OutsideMessagingWindow):
        sender.send_image(page, PSID, "https://cdn.example.com/p.jpg", None)
    assert not api.route.calls  # nothing reached Facebook
    assert sender.send_text(page, PSID, "hi", now - timedelta(hours=1)) is not None and len(api.route.calls) == 1


def test_facebook_saying_outside_the_window_is_not_retried(graph):
    api = SendApi(graph)
    api.plan = [error(400, 10, "(#10) This message is sent outside of allowed window.", 2018278)]
    page = FacebookPage(shop_id=1, page_id=PAGE_ID, page_name="x", encrypted_page_token=TokenCipher().encrypt(PAGE_TOKEN))
    with pytest.raises(OutsideMessagingWindow):
        MessengerSender().send_text(page, PSID, "hi", datetime.now(timezone.utc))
    assert len(api.route.calls) == 1


# --------------------------------------------------------------- failed sends are not counted


def test_a_failed_send_is_not_counted_and_the_worker_survives(client, shop, db, send):
    send.plan = [error(400, 100, "(#100) Invalid parameter")]  # permanent: no retry
    assert post(client, payload(event())).status_code == 200
    ai = ai_messages(db)[0]
    assert ai.sent_at is None and ai.extras["delivery"]["status"] == "failed"
    assert customer_messages(db)[0].extras["ai_status"] == "failed"
    assert len(send.route.calls) == 1
    assert UsageLimitService(db).get_usage(shop[1]).used == 0


def test_temporary_errors_are_retried_a_limited_number_of_times(client, shop, db, send):
    send.plan = [error(500, 2, "temporary"), error(500, 2, "temporary"), error(500, 2, "temporary"), error(500, 2, "temporary")]
    post(client, payload(event()))
    assert len(send.route.calls) == 3  # FB_SEND_MAX_ATTEMPTS
    assert ai_messages(db)[0].sent_at is None and UsageLimitService(db).get_usage(shop[1]).used == 0


def test_a_temporary_error_followed_by_success_counts_once(client, shop, db, send):
    send.plan = [error(500, 2, "temporary"), httpx.Response(503, text="Service Unavailable")]
    post(client, payload(event()))
    assert len(send.route.calls) == 3
    assert ai_messages(db)[0].sent_at is not None and UsageLimitService(db).get_usage(shop[1]).used == 1


def test_a_network_error_is_retried_too(client, shop, db, graph):
    api = SendApi(graph)
    api.route.mock(side_effect=[httpx.ConnectError("down"), httpx.Response(200, json={"message_id": "m_ok"})])
    post(client, payload(event()))
    assert ai_messages(db)[0].sent_at is not None and UsageLimitService(db).get_usage(shop[1]).used == 1


def test_errors_are_logged_without_secrets(client, shop, db, send, caplog):
    caplog.set_level(logging.DEBUG)
    send.plan = [error(400, 190, "Invalid OAuth access token.")]
    post(client, payload(event("Red Jamdani Saree price koto?")))
    assert "Invalid OAuth access token." in caplog.text
    assert PAGE_TOKEN not in caplog.text and PSID not in caplog.text and "Red Jamdani" not in caplog.text


def test_the_worker_never_crashes_on_an_unexpected_error(client, shop, db, send, monkeypatch):
    def boom(self, chat, message):
        raise RuntimeError("bug")

    monkeypatch.setattr("app.services.conversation.ConversationService.reply_to_stored_message", boom)
    assert post(client, payload(event())).status_code == 200  # the webhook still answered 200
    msg = customer_messages(db)[0]
    assert msg.extras["ai_status"] == "failed" and msg.extras["ai_error"] == "RuntimeError"
    assert not send.route.calls and msg.text  # the customer's message is safe for the seller


def test_the_webhook_answers_200_even_if_the_queue_is_down(client, shop, db, send, monkeypatch):
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(process_incoming_message, "delay", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("redis down")))
    try:
        r = post(client, payload(event()))
        assert r.status_code == 200 and r.json()["received"] == 1
        assert customer_messages(db)[0].extras["ai_status"] == "pending" and not send.route.calls
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# ----------------------------------------------------------------- order and idempotency


def test_messages_of_one_chat_are_answered_in_order_and_a_retried_task_does_not_answer_twice(client, shop, db, send, monkeypatch):
    monkeypatch.setattr("app.api.v1.routes.webhooks.enqueue", lambda *a: None)  # both messages wait in the database
    post(client, payload(event("Red Jamdani Saree price koto?", mid="m_1")))
    post(client, payload(event("Red Jamdani Saree stock ache?", mid="m_2")))
    first, second = [m.id for m in customer_messages(db)]
    assert not send.route.calls

    process_incoming_message(second)  # the task of the LATER message arrives first
    assert len(send.texts) == 2
    assert "automatic assistant" in send.texts[0] and "dam 4800" in send.texts[0]  # answered the first message first
    assert [m.extras["ai_status"] for m in customer_messages(db)] == ["replied", "replied"]

    process_incoming_message(first)
    process_incoming_message(second)
    assert len(send.sent) == 2 and UsageLimitService(db).get_usage(shop[1]).used == 2


def test_a_retried_task_after_a_crash_sends_the_stored_reply_once(client, shop, db, send, monkeypatch):
    monkeypatch.setattr("app.api.v1.routes.webhooks.enqueue", lambda *a: None)
    post(client, payload(event()))
    msg_id = customer_messages(db)[0].id
    original = MessengerSender.send_text
    calls = {"n": 0}

    def flaky(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("worker died while sending")
        return original(self, *a, **k)

    monkeypatch.setattr(MessengerSender, "send_text", flaky)
    process_incoming_message(msg_id)  # AI reply stored, then the crash
    assert len(ai_messages(db)) == 1 and ai_messages(db)[0].sent_at is None
    db.execute(update(Message).where(Message.id == msg_id).values(extras={"ai_status": "pending"}))
    db.commit()
    process_incoming_message(msg_id)
    assert len(ai_messages(db)) == 1 and len(send.sent) == 1  # the stored reply was sent, not regenerated


# ------------------------------------------------------------------- not text


@pytest.mark.parametrize(
    "attachments,sticker,placeholder",
    [(["image"], False, "[Customer sent a photo]"), (["audio"], False, "[Customer sent a voice message]"), (["video"], False, "[Customer sent a video]"), (["file"], False, "[Customer sent a file]"), (["image"], True, "[Customer sent a sticker]")],
)
def test_non_text_messages_are_stored_as_a_placeholder_and_handed_over(client, shop, db, send, attachments, sticker, placeholder):
    calls_before = model_calls(db)
    r = post(client, payload(event(attachments=attachments, sticker=sticker)))
    assert r.status_code == 200
    customer = customer_messages(db)[0]
    assert customer.text == placeholder and customer.extras["non_text"] is True
    chat = db.scalars(select(Chat)).one()
    db.expire_all()
    assert (chat.is_flagged, chat.flag_reason, chat.ai_paused) == (True, "low_confidence", True)
    (event_row,) = db.scalars(select(HandoverEvent)).all()
    assert event_row.reason == "low_confidence"
    (note,) = db.scalars(select(Notification)).all()
    assert (note.reason, note.chat_id, note.read_at) == ("low_confidence", chat.id, None)  # Messenger: the seller is notified
    # the AI did not try to interpret it: no model call, a short holding reply
    assert model_calls(db) == calls_before
    assert len(send.texts) == 1 and "check" in send.texts[0].lower()
    assert ai_messages(db)[0].extras["handover"]["detail"] == "non_text_message"


def test_text_with_an_attachment_is_treated_as_text(client, shop, db, send):
    e = event("Red Jamdani Saree price koto?")
    e["message"]["attachments"] = [{"type": "image", "payload": {"url": "https://example.com/x"}}]
    post(client, payload(e))
    assert customer_messages(db)[0].extras["non_text"] is False and "4800" in send.texts[0]


# ----------------------------------------------------------------- suggestions come with photos


def test_suggestion_replies_send_the_product_photos(client, shop, db, send):
    token, shop_id = shop
    pid = add_product(client, token, "Eid Special Panjabi", 1450, 8, ["M", "L"], ["White"])
    local = add_product(client, token, "Cotton Panjabi", 1100, 5, ["M"], ["White"])
    db.execute(update(Product).where(Product.id == pid).values(photos=["https://cdn.example.com/eid.jpg"]))
    db.execute(update(Product).where(Product.id == local).values(photos=["http://localhost:8000/media/local.jpg"]))
    db.commit()

    post(client, payload(event("panjabi dekhan 2000 er moddhe")))
    assert len(send.texts) == 1 and "Eid Special Panjabi" in send.texts[0]
    assert send.images == ["https://cdn.example.com/eid.jpg"]  # a localhost URL cannot be fetched by Facebook: skipped
    delivery = ai_messages(db)[0].extras["delivery"]
    assert (delivery["images_sent"], delivery["images_skipped"]) == (1, 1)
    assert UsageLimitService(db).get_usage(shop_id).used == 1  # photos do not count as extra replies


def test_a_failed_photo_does_not_undo_the_delivered_reply(client, shop, db, send):
    token, shop_id = shop
    pid = add_product(client, token, "Eid Special Panjabi", 1450, 8, ["M"], ["White"])
    db.execute(update(Product).where(Product.id == pid).values(photos=["https://cdn.example.com/eid.jpg"]))
    db.commit()
    send.plan = [httpx.Response(200, json={"message_id": "m_text"}), error(400, 100, "(#100) Failed to fetch image")]
    post(client, payload(event("panjabi dekhan 2000 er moddhe")))
    ai = ai_messages(db)[0]
    assert ai.sent_at is not None and ai.extras["delivery"]["images_sent"] == 0 and UsageLimitService(db).get_usage(shop_id).used == 1


# ------------------------------------------------------------------ shops stay separate


def test_a_page_only_routes_to_its_own_shop(client, shop, db, send):
    token_a, shop_a = shop
    token_b = signup(client, "b@example.com", "Shop B")
    add_product(client, token_b, "Blue Mug", 120, 5)
    shop_b = db.scalar(select(Shop.id).where(Shop.name == "Shop B"))
    connect_page(db, shop_b, page_id="2002", token="EAAB-shop-B-token", name="Shop B Page")

    post(client, payload(event("Blue Mug price koto?", page_id="2002"), page_id="2002"))
    chat_b = db.scalars(select(Chat)).one()
    assert chat_b.shop_id == shop_b and "120" in send.texts[0]
    assert send.route.calls[0].request.headers["authorization"] == "Bearer EAAB-shop-B-token"  # B's token, not A's

    # the same customer id writing to shop A's Page is a different chat of shop A
    post(client, payload(event("Blue Mug price koto?"), page_id=PAGE_ID))
    chats = {c.shop_id: c for c in db.scalars(select(Chat))}
    assert set(chats) == {shop_a, shop_b} and chats[shop_a].id != chats[shop_b].id
    assert "120" not in send.texts[1] and send.route.calls[1].request.headers["authorization"] == f"Bearer {PAGE_TOKEN}"
    assert all(m.shop_id == chats[m.shop_id].shop_id for m in messages(db))
    # an event naming Page A inside Page B's entry is not routed anywhere
    cross = payload(event(page_id=PAGE_ID, recipient=PAGE_ID), page_id="2002")
    assert post(client, cross).json()["received"] == 0


def test_a_customer_is_one_chat_per_shop(client, shop, db, send):
    post(client, payload(event(mid="m_1")))
    post(client, payload(event(mid="m_2")))
    assert len(db.scalars(select(Chat)).all()) == 1


# ------------------------------------------------------------------------- small units


def test_public_url_check_and_text_splitting():
    assert is_public_url("https://cdn.example.com/a.jpg") and is_public_url("http://203.0.113.9/a.jpg")
    for url in ("http://localhost:8000/media/a.jpg", "http://127.0.0.1/a.jpg", "http://192.168.0.5/a.jpg", "http://10.0.0.2/a.jpg", "ftp://x/a.jpg", "/media/a.jpg", ""):
        assert not is_public_url(url)
    assert split_text("short") == ["short"] and split_text("") == []
    long = ("word " * 900).strip()
    parts = split_text(long)
    assert len(parts) == 3 and all(len(p) <= 2000 for p in parts) and " ".join(parts).split() == long.split()


def test_graph_client_sends_a_response_message(graph):
    api = SendApi(graph)
    assert GraphClient().send_message("tok", PSID, {"text": "hi"}) == "m_0"
    body = json.loads(api.route.calls[0].request.content)
    assert body == {"recipient": {"id": PSID}, "messaging_type": "RESPONSE", "message": {"text": "hi"}}
    assert GraphClient().customer_name(PSID, "tok") == "Nasrin Sultana"
