from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    try:
        redis_status = "ok" if get_redis().ping() else "error"
    except Exception:
        redis_status = "error"
    overall = "ok" if db_status == redis_status == "ok" else "degraded"
    if overall != "ok":
        response.status_code = 503  # so a platform health check or uptime monitor sees the failure (NFR-02)
    return {"status": overall, "api": "ok", "database": db_status, "redis": redis_status}
