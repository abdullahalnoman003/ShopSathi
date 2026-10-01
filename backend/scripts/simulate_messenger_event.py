"""Posts a correctly signed Messenger webhook event to the local API, as Facebook would. For development and
testing without Facebook.

    python scripts/simulate_messenger_event.py --page-id 900001 --psid 5550001 --text "Red Jamdani Saree price koto?"

The signature uses FB_APP_SECRET from backend/.env, so the API must run with the same value. The Page id must be
the id of a connected Page (see /dashboard/facebook). Run a Celery worker to process the message, and see the
reply with the fake Facebook (scripts/fake_facebook.py, GET /_debug/messages) or on a real test Page.

Options: --attachment image|audio|video|file|sticker (a non-text message), --echo (an echo of the Page's own
message, which must be ignored), --bad-signature (must be rejected with 403), --mid (repeat the same value to send
a duplicate, which must be processed once), --timestamp-hours-ago N (an old message, to try the 24-hour window).
"""

import argparse
import json
import sys
import time
import uuid

import httpx

sys.path.insert(0, ".")
from app.core.config import get_settings  # noqa: E402
from app.integrations.facebook.webhook import sign  # noqa: E402


def build_payload(args: argparse.Namespace) -> dict:
    now_ms = int((time.time() - args.timestamp_hours_ago * 3600) * 1000)
    message: dict = {"mid": args.mid or f"m_sim_{uuid.uuid4().hex[:16]}"}
    if args.attachment:
        message["attachments"] = [{"type": "image" if args.attachment == "sticker" else args.attachment, "payload": {"url": "https://example.com/x"}}]
        if args.attachment == "sticker":
            message["sticker_id"] = 369239263222822
    else:
        message["text"] = args.text
    sender, recipient = (args.page_id, args.psid) if args.echo else (args.psid, args.page_id)
    if args.echo:
        message["is_echo"] = True
    return {
        "object": "page",
        "entry": [
            {
                "id": args.page_id,
                "time": now_ms,
                "messaging": [{"sender": {"id": sender}, "recipient": {"id": recipient}, "timestamp": now_ms, "message": message}],
            }
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000", help="base URL of the ShopSathi API")
    ap.add_argument("--page-id", required=True)
    ap.add_argument("--psid", default="5550001", help="the customer's Page-scoped id")
    ap.add_argument("--text", default="Hello")
    ap.add_argument("--mid", default=None)
    ap.add_argument("--attachment", choices=["image", "audio", "video", "file", "sticker"], default=None)
    ap.add_argument("--echo", action="store_true")
    ap.add_argument("--bad-signature", action="store_true")
    ap.add_argument("--timestamp-hours-ago", type=float, default=0.0)
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    secret = get_settings().fb_app_secret
    if not secret:
        print("FB_APP_SECRET is not set in backend/.env: cannot sign the event.", file=sys.stderr)
        return 2
    body = json.dumps(build_payload(args), ensure_ascii=False).encode()
    signature = sign("wrong-secret" if args.bad_signature else secret, body)
    res = httpx.post(
        f"{args.api.rstrip('/')}/api/v1/webhooks/messenger",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        timeout=15,
    )
    print(res.status_code, res.text)
    return 0 if res.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
