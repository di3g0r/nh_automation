"""Application error type and the shared JSON error shape (overview §5).

Response shape: {"error": {"code": "...", "message": "<spanish text>", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Raised by services/routes for any domain-level failure.

    `message` is shown to the user, so it must already be in Spanish.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


# Common, reusable errors -----------------------------------------------------


def not_found(entity_label: str) -> AppError:
    return AppError("NOT_FOUND", f"{entity_label} no encontrado.", status.HTTP_404_NOT_FOUND)


def forbidden(message: str = "No tiene permiso para realizar esta acción.") -> AppError:
    return AppError("FORBIDDEN", message, status.HTTP_403_FORBIDDEN)


def unauthorized(message: str = "Sesión inválida o expirada.") -> AppError:
    return AppError("UNAUTHORIZED", message, status.HTTP_401_UNAUTHORIZED)
