from fastapi import APIRouter

from app.api.v1.routes import auth, health, plans, products, shop

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(plans.router)
api_router.include_router(shop.router)
api_router.include_router(products.router)
