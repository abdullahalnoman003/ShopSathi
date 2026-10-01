from celery import Celery

from app.core.config import get_settings

celery_app = Celery(
    "shopsathi",
    broker=get_settings().redis_url,
    backend=get_settings().redis_url,
)
celery_app.conf.update(task_serializer="json", result_serializer="json", timezone="UTC")


@celery_app.task(name="shopsathi.ping")
def ping() -> str:
    return "pong"
