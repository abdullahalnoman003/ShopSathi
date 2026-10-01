"""Deleting a shop and everything it owns (section 5.3: "Sellers can delete their shop, and all its chats and orders
are then removed"). The database does the bulk of it: every shop-owned table has a foreign key to ``shops`` with
ON DELETE CASCADE (users, products, policies and delivery areas, embeddings, chats, messages, orders, notifications,
handover events, usage, weekly insights, AI usage logs, the Facebook Page and simulated payments), so one DELETE on
the shop row removes it all. Around that: Facebook is told to stop sending events, the product photo files and the
shop's short-lived Redis keys are removed. Not undoable."""

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.models import Chat, Shop
from app.services.facebook import FacebookError, FacebookService
from app.services.storage import StorageService

logger = logging.getLogger("shopsathi.privacy")

#: Redis key prefixes that contain "<shop_id>:" right after the prefix
SHOP_KEY_PREFIXES = ("chatmem", "chatlock", "chatmsgs", "ingest")


@dataclass
class DeletionReport:
    page_disconnected: bool
    files_deleted: int
    redis_keys_deleted: int


class ShopDeletionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.redis = get_redis()

    def delete_shop(self, shop_id: int) -> DeletionReport:
        chat_ids = list(self.db.scalars(select(Chat.id).where(Chat.shop_id == shop_id)))

        # 1. stop Facebook from sending events (best effort: the Page may already be gone)
        disconnected = False
        try:
            FacebookService(self.db).disconnect(shop_id)
            disconnected = True
        except FacebookError:
            pass  # no Page connected
        except Exception as e:  # noqa: BLE001 - never block the deletion on Facebook
            self.db.rollback()
            logger.warning("shop %s: Facebook disconnect failed (%s)", shop_id, e.__class__.__name__)

        # 2. product photo files
        files = 0
        try:
            files = StorageService().delete_shop_files(shop_id)
        except Exception as e:  # noqa: BLE001
            logger.error("shop %s: deleting the photo files failed (%s)", shop_id, e.__class__.__name__)

        # 3. short-lived Redis keys of the shop's chats (memory, locks, pending Page list, name lookups)
        keys = 0
        try:
            keys = self._delete_redis_keys(shop_id, chat_ids)
        except Exception as e:  # noqa: BLE001
            logger.error("shop %s: deleting the Redis keys failed (%s)", shop_id, e.__class__.__name__)

        # 4. the shop row: the database cascades to everything the shop owns
        self.db.execute(delete(Shop).where(Shop.id == shop_id))
        self.db.commit()
        logger.info("shop %s deleted (%s chats, %s files, %s Redis keys)", shop_id, len(chat_ids), files, keys)
        return DeletionReport(page_disconnected=disconnected, files_deleted=files, redis_keys_deleted=keys)

    def _delete_redis_keys(self, shop_id: int, chat_ids: list[int]) -> int:
        deleted = 0
        patterns = [f"{prefix}:{shop_id}:*" for prefix in SHOP_KEY_PREFIXES] + [f"fb:pages:{shop_id}"]
        for pattern in patterns:
            for key in self.redis.scan_iter(match=pattern, count=500):
                deleted += int(self.redis.delete(key))
        if chat_ids:
            deleted += int(self.redis.delete(*[f"fb:name_tried:{c}" for c in chat_ids]))
        return deleted
