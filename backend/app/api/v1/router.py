from fastapi import APIRouter

from app.api.v1.routes import admin, auth, chats, facebook, health, notifications, orders, plans, policy, products, reports, shop, test_chat, webhooks

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
api_router.include_router(admin.router)
api_router.include_router(chats.router)
api_router.include_router(orders.router)
api_router.include_router(reports.router)
api_router.include_router(webhooks.router)
