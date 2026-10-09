"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Work Order and Production Tracking System API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Starlette's handler type is covariant on Exception; our handler is
    # correctly typed for AppError specifically (registered only for it).
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]

    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
