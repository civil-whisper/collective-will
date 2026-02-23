from fastapi import APIRouter

from src.api.routes.analytics import router as analytics_router
from src.api.routes.auth import router as auth_router
from src.api.routes.ops import router as ops_router
from src.api.routes.user import router as user_router
from src.api.routes.webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(user_router, prefix="/user", tags=["user"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(ops_router, prefix="/ops", tags=["ops"])
