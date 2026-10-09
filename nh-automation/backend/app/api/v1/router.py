from fastapi import APIRouter

from app.api.v1 import audit, auth, catalogs, health, imports, inventory, settings, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(settings.router)
api_router.include_router(catalogs.router)
api_router.include_router(imports.router)
api_router.include_router(inventory.router)
