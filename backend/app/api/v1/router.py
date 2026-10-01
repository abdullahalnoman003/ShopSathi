from fastapi import APIRouter

from app.api.v1.routes import auth, facebook, health, notifications, plans, policy, products, shop, test_chat, webhooks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(plans.router)
api_router.include_router(shop.router)
api_router.include_router(products.router)
api_router.include_router(policy.router)
api_router.include_router(test_chat.router)
api_router.include_router(notifications.router)
api_router.include_router(facebook.router)
api_router.include_router(webhooks.router)
