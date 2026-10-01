"""Background jobs. Registered with the Celery app (see `include` in celery_app.py)."""

import logging

from shopsathi_ai.providers import EmbeddingProviderError
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Product
from app.services.embeddings import EmbeddingService
from app.workers.celery_app import celery_app

_retry = dict(autoretry_for=(EmbeddingProviderError,), retry_backoff=2, retry_backoff_max=20, retry_kwargs={"max_retries": 4})


@celery_app.task(name="shopsathi.embed_product", **_retry)
def embed_product(product_id: int) -> int:
    """Re-embed one product (after it was added or edited). Returns the number of chunks stored."""
    with SessionLocal() as db:
        shop_id = db.scalar(select(Product.shop_id).where(Product.id == product_id))
        if shop_id is None:
            return 0  # deleted meanwhile: delete_product_embeddings handles its chunks
        return EmbeddingService(db).embed_product(shop_id, product_id).chunks


@celery_app.task(name="shopsathi.delete_product_embeddings")
def delete_product_embeddings(product_id: int, shop_id: int) -> int:
    with SessionLocal() as db:
        EmbeddingService(db).delete_product(shop_id, product_id)
    return 0


@celery_app.task(name="shopsathi.embed_policy", **_retry)
def embed_policy(shop_id: int) -> int:
    with SessionLocal() as db:
        return EmbeddingService(db).embed_policy(shop_id).chunks


logger = logging.getLogger("shopsathi.tasks")


@celery_app.task(name="shopsathi.process_incoming_message", bind=True, max_retries=5)
def process_incoming_message(self, message_id: int) -> None:
    """Answer a stored Messenger customer message (and any earlier ones of that chat still waiting), in order.

    Never raises to the worker: a failure leaves the customer's message safely stored for the seller."""
    from app.services.messenger_processor import ChatBusy, MessengerProcessor

    try:
        with SessionLocal() as db:
            MessengerProcessor(db).process(message_id)
    except ChatBusy as e:
        raise self.retry(countdown=3, exc=e)  # another worker is on this chat: keep the order
    except Exception as e:
        logger.exception("process_incoming_message(%s) failed: %s", message_id, e.__class__.__name__)


@celery_app.task(name="shopsathi.generate_weekly_insights")
def generate_weekly_insights(week_start: str | None = None) -> dict[str, int]:
    """Weekly job (celery beat): the AI summary of the previous week for every active shop. Shops that already have
    one are skipped, so a repeated run does no extra AI work. A failing shop is logged and does not stop the rest."""
    from datetime import date

    from app.services.insights import InsightsService, previous_week_start

    week = date.fromisoformat(week_start) if week_start else previous_week_start()
    with SessionLocal() as db:
        result = InsightsService(db).generate_for_all(week)
    logger.info("weekly insights for week %s: %s", week, result)
    return result
