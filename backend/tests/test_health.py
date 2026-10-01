def test_health_reports_database_and_redis_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["api"] == "ok"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
    assert body["status"] == "ok"


def test_cors_allows_frontend_origin(client):
    r = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_health_answers_503_when_a_dependency_is_down(client, monkeypatch):
    """A platform health check / uptime monitor only looks at the HTTP status (NFR-02)."""
    from app.core import redis as redis_module

    class Broken:
        def ping(self):
            raise ConnectionError("redis is down")

    monkeypatch.setattr("app.api.v1.routes.health.get_redis", lambda: Broken())
    r = client.get("/api/v1/health")
    assert r.status_code == 503 and r.json()["status"] == "degraded" and r.json()["redis"] == "error" and r.json()["database"] == "ok"


def test_managed_database_urls_are_accepted():
    from app.core.config import Settings

    for given in ("postgres://u:p@db.example.com:5432/shop", "postgresql://u:p@db.example.com:5432/shop", "postgresql+psycopg://u:p@db.example.com:5432/shop"):
        assert Settings(database_url=given, jwt_secret="x" * 40).database_url == "postgresql+psycopg://u:p@db.example.com:5432/shop"


def test_api_docs_are_published_only_in_local_runs(monkeypatch):
    import importlib

    import app.main
    from app.core.config import get_settings

    try:
        assert app.main.app.docs_url == "/docs"  # the local/test run
        monkeypatch.setenv("APP_ENV", "production")
        get_settings.cache_clear()
        prod = importlib.reload(app.main).app
        assert prod.docs_url is None and prod.redoc_url is None and prod.openapi_url is None
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        importlib.reload(app.main)
