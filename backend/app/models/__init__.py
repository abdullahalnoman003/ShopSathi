"""ORM models. Import every model module here so Alembic sees it."""

from app.models.chat import Chat, Message
from app.models.embedding import AiUsageLog, EmbeddingChunk
from app.models.facebook import FacebookPage
from app.models.handover import HandoverEvent, Notification
from app.models.order import Order
from app.models.password_reset_token import PasswordResetToken
from app.models.plan import Plan, ShopMessageUsage, SimulatedPayment
from app.models.policy import DeliveryArea, ShopPolicy
from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.models.weekly_insight import WeeklyInsight

__all__ = [
    "AiUsageLog",
    "Chat",
    "EmbeddingChunk",
    "DeliveryArea",
    "PasswordResetToken",
    "FacebookPage",
    "HandoverEvent",
    "Message",
    "Notification",
    "Order",
    "Plan",
    "Product",
    "Shop",
    "ShopMessageUsage",
    "ShopPolicy",
    "SimulatedPayment",
    "User",
    "WeeklyInsight",
]
