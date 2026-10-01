from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "shopsathi",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    include=["app.workers.tasks"],  # imported lazily when the worker starts
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    task_always_eager=_settings.celery_task_always_eager,
    task_eager_propagates=_settings.celery_task_always_eager,
)


@celery_app.task(name="shopsathi.ping")
def ping() -> str:
    return "pong"
