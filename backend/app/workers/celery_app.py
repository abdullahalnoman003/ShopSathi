import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from app.core.config import get_settings
from app.core.log_masking import install_log_masking

_settings = get_settings()
install_log_masking()  # the worker logs through the same masking as the API

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
    # No task result is read by anyone except the admin health check (the ping task), so do not store one per message in Redis.
    task_ignore_result=True,
    task_always_eager=_settings.celery_task_always_eager,
    task_eager_propagates=_settings.celery_task_always_eager,
    # Celery runs in UTC. Sunday 20:00 UTC = Monday 02:00 in Dhaka: the previous week (Mon-Sun, Dhaka) is complete.
    beat_schedule={
        "weekly-insights": {
            "task": "shopsathi.generate_weekly_insights",
            "schedule": crontab(minute=0, hour=20, day_of_week="sunday"),
        },
    },
)


@celery_app.task(name="shopsathi.ping", ignore_result=False)  # the admin health check waits for this answer
def ping() -> str:
    return "pong"


@worker_ready.connect
def warm_up(**_kwargs) -> None:
    """Get the first customers of a freshly started worker the same speed as the later ones. The first burst of
    messages would otherwise open all its database connections and import the AI client at the same moment (measured in
    docs/TEST_REPORT.md: the 90th percentile of the first 100 messages was 10 s, afterwards 6 s). No AI request is made."""
    log = logging.getLogger("shopsathi.tasks")
    try:
        from app.ai_adapters.factory import get_embedder, get_llm
        from app.core.database import engine

        get_llm()  # builds the model client (imports the AI libraries)
        get_embedder()
        connections = [engine.connect() for _ in range(_settings.db_pool_size)]  # fills the pool
        for c in connections:
            c.close()
        log.info("worker warmed up (%s database connections)", len(connections))
    except Exception as e:  # noqa: BLE001 - a warm-up problem must never stop the worker
        log.warning("worker warm-up skipped (%s)", e.__class__.__name__)
