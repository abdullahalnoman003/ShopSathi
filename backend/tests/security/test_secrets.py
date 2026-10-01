"""NFR-03 and NFR-04: Page tokens encrypted at rest, no secret in any API response or log, no secret in the repository."""

import logging
import re
import subprocess
from pathlib import Path

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.core.config import get_settings
from app.core.crypto import TokenCipher
from tests.conftest import PASSWORD, auth_header
from tests.test_facebook import PAGES, Recorder, connect_flow, mock_login

API = "/api/v1"
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def graph():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def owner(client):
    return client.post(f"{API}/auth/signup", json={"shop_name": "Shop A", "owner_name": "Owner", "email": "a@example.com", "password": PASSWORD}).json()["access_token"]


# ------------------------------------------------------------------------------------ at rest


def test_the_page_token_is_encrypted_in_the_database_and_not_readable_without_the_key(client, db, graph):
    mock_login(graph)
    token = owner(client)
    rec = Recorder(client)
    assert connect_flow(rec, token, "1001").status_code == 200
    plain_tokens = [p["access_token"] for p in PAGES]
    (stored,) = [v for (v,) in db.execute(text("select encrypted_page_token from facebook_pages"))]
    assert stored.startswith("gAAAA")  # a Fernet token (AES-128-CBC + HMAC)
    assert all(t not in stored for t in plain_tokens)
    assert TokenCipher().decrypt(stored) in plain_tokens
    other_key = Fernet(Fernet.generate_key())
    with pytest.raises(Exception):
        other_key.decrypt(stored.encode())  # useless to anyone without the shop's encryption key
    # no column of any table holds a Page token or a user token in clear
    for table in ("facebook_pages", "shops", "users", "chats", "messages"):
        dump = " ".join(str(v) for row in db.execute(text(f"select * from {table}")) for v in row)
        assert not any(t in dump for t in plain_tokens), table


def test_no_api_response_contains_a_token_or_a_secret(client, db, graph):
    mock_login(graph)
    token = owner(client)
    rec = Recorder(client)
    h = auth_header(token)
    connect_flow(rec, token, "1001")
    for path in ("/facebook/page", "/facebook/pages/available", "/facebook/connect-url", "/shop/plan", "/shop/staff", "/auth/me", "/chats", "/orders", "/products", "/shop/policy", "/notifications"):
        rec.request("GET", path, headers=h)
    s = get_settings()
    secrets_ = [s.jwt_secret, s.fb_app_secret, s.fb_token_encryption_key, s.fb_verify_token, *(p["access_token"] for p in PAGES), "FAKE-LONG-USER-TOKEN"]
    secrets_ += [v for v in (s.openai_api_key, s.gemini_api_key, s.smtp_password) if v]
    blob = "\n".join(rec.bodies)
    for secret in secrets_:
        if secret:
            assert secret not in blob, "a secret appeared in an API response"
    assert "encrypted_page_token" not in blob and "access_token" not in re.sub(r'"access_token":"[^"]{20,}\.[^"]{20,}\.[^"]{10,}"', "", blob)  # only our own session token (a JWT) may be named


def test_the_openapi_schema_exposes_no_secret_fields():
    import json

    from app.main import app

    schema = json.dumps(app.openapi())
    for name in ("password_hash", "encrypted_page_token", "token_hash", "fb_app_secret", "jwt_secret"):
        assert name not in schema, f"{name} is part of the public API schema"


# ------------------------------------------------------------------------------------ logs


def test_no_secret_is_written_to_the_logs_during_login_connect_and_webhook(client, graph, caplog):
    caplog.set_level(logging.DEBUG)
    mock_login(graph)
    token = owner(client)
    client.post(f"{API}/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    client.post(f"{API}/auth/login", json={"email": "a@example.com", "password": "wrong-password-1"})
    rec = Recorder(client)
    connect_flow(rec, token, "1001")
    client.get(f"{API}/auth/me", headers=auth_header(token))
    s = get_settings()
    text_ = caplog.text
    for secret in (s.jwt_secret, s.fb_app_secret, s.fb_token_encryption_key, token, PASSWORD, "wrong-password-1", *(p["access_token"] for p in PAGES), "FAKE-LONG-USER-TOKEN"):
        assert secret and secret not in text_, "a secret was written to the logs"


# ------------------------------------------------------------------------------------ the repository


SECRET_PATTERNS = {
    "OpenAI key": r"sk-[A-Za-z0-9_-]{20,}",
    "Google API key": r"AIza[0-9A-Za-z_-]{35}",
    "Facebook access token": r"\bEAA[A-Za-z0-9]{40,}",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----",
    "Slack token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{30,}",
}
SKIP_DIRS = {".git", "node_modules", ".next", ".venv", "venv", "__pycache__", ".pytest_cache", "media", "reports", "results", "shopsathi_ai.egg-info"}


def repo_files(with_frontend: bool = True) -> list[Path]:
    """Files that would be committed: tracked and untracked-but-not-ignored (git), plus the frontend sources (the
    repository's .gitignore currently ignores frontend/ as a whole, but its source must be clean as well)."""
    files: set[Path] = set()
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=REPO, capture_output=True, check=True).stdout
        files.update(REPO / p for p in out.decode("utf-8", "replace").split("\0") if p)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available here")
    for top in (("frontend",) if with_frontend else ()):
        base = REPO / top
        if base.is_dir():
            files.update(p for p in base.rglob("*") if p.is_file() and not (set(p.relative_to(REPO).parts) & SKIP_DIRS))
    return sorted(p for p in files if p.is_file() and not (set(p.relative_to(REPO).parts) & SKIP_DIRS))


def text_of(path: Path) -> str | None:
    try:
        if path.stat().st_size > 2_000_000:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return None if b"\0" in data else data.decode("utf-8", "replace")


def test_no_env_file_with_real_values_is_part_of_the_repository():
    files = [p.relative_to(REPO).as_posix() for p in repo_files(with_frontend=False)]
    bad = [f for f in files if re.search(r"(^|/)\.env($|\.)", f) and not f.endswith((".env.example", ".env.sample", ".env.template"))]
    assert bad == [], f"environment files that would be committed: {bad}"
    assert any(f.endswith(".env.example") for f in files)


def test_the_repository_contains_no_api_keys_or_private_keys():
    found = []
    for path in repo_files():
        text_ = text_of(path)
        if text_ is None:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            for m in re.finditer(pattern, text_):
                found.append(f"{path.relative_to(REPO).as_posix()}: looks like a {name}")
    assert found == [], "\n".join(found)


def test_the_example_env_files_hold_no_secret_values():
    secret_keys = re.compile(r"(SECRET|PASSWORD|API_KEY|ENCRYPTION_KEY|TOKEN)$")
    for path in repo_files():
        if not path.name.endswith(".env.example"):
            continue
        for line in text_of(path).splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                if secret_keys.search(key.strip()):
                    # the one public local-development default of the demo database container (database/docker-compose.yml)
                    assert value.strip() in ("", "shopsathi_local"), f"{path.name}: {key.strip()} has a value in the example file"


def test_none_of_this_machines_real_secrets_appear_in_the_repository():
    """If a local backend/.env exists, none of its secret values may appear in any file that would be committed."""
    env = REPO / "backend" / ".env"
    if not env.exists():
        pytest.skip("no local backend/.env to compare with")
    values = []
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if re.search(r"(SECRET|PASSWORD|API_KEY|ENCRYPTION_KEY|TOKEN)$", key.strip()) and len(value) >= 12:
                values.append(value)
    leaks = []
    for path in repo_files():
        if path.name == ".env":
            continue
        text_ = text_of(path)
        if text_ and any(v in text_ for v in values):
            leaks.append(path.relative_to(REPO).as_posix())
    assert leaks == [], f"a real secret value from backend/.env appears in: {leaks}"


def test_the_settings_have_no_hardcoded_secret_defaults():
    import inspect

    from app.core import config

    source = inspect.getsource(config)
    for line in source.splitlines():
        m = re.match(r"\s+(\w*(?:secret|password|api_key|encryption_key|token)\w*)\s*:\s*str\s*=\s*(.+)", line, re.IGNORECASE)
        if m:
            assert m.group(2).strip() in ('""', "''"), f"{m.group(1)} has a default value in config.py"
