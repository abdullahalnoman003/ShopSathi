import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger("shopsathi.tasks")


def enqueue(task: Any, *args: Any) -> None:
    """Queue a background task without ever failing the request that triggered it.

    The data change is already committed; if the queue is down the embeddings can be rebuilt with
    `python -m app.cli reembed-shop --shop-id N`. In eager (test) mode errors are raised so tests see them.
    """
    try:
        task.delay(*args)
    except Exception:
        if get_settings().celery_task_always_eager:
            raise
        logger.exception("could not queue %s%r", task.name, args)
