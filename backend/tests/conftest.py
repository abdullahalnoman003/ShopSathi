import os
import tempfile

# Point the whole app at the test database and a separate Redis db BEFORE the app is imported.
from app.core.config import get_settings

_s = get_settings()
os.environ["DATABASE_URL"] = _s.test_database_url
os.environ["REDIS_URL"] = _s.redis_url.rsplit("/", 1)[0] + "/15"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"  # run background jobs inline in tests
os.environ["EMBEDDING_PROVIDER"] = "mock"  # never call a real provider from tests
os.environ["EMBEDDING_DIM"] = "1536"
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="shopsathi-test-media-")
get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.main import app  # noqa: E402
from app.services.email import EmailService, get_email_service  # noqa: E402
from app.services.plans import seed_plans  # noqa: E402


class FakeEmail(EmailService):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_password_reset(self, to: str, reset_link: str) -> None:
        self.sent.append((to, reset_link))


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean():
    get_redis().flushdb()
    with engine.begin() as conn:
        existing = set(inspect(conn).get_table_names())
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name in existing)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with SessionLocal() as session:
        seed_plans(session)  # plans are reference data every shop needs
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def emails():
    fake = FakeEmail()
    app.dependency_overrides[get_email_service] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_email_service, None)


@pytest.fixture
def client(emails):
    with TestClient(app) as c:
        yield c


PASSWORD = "correct-horse-1"


@pytest.fixture
def signup(client):
    def _signup(shop="Shop A", email="a@example.com", password=PASSWORD, owner="Owner A"):
        return client.post(
            "/api/v1/auth/signup",
            json={"shop_name": shop, "owner_name": owner, "email": email, "password": password},
        )

    return _signup


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
