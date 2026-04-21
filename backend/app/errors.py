"""Universal error envelope, exception classes, and FastAPI handlers.

Every non-2xx response from this backend uses the shape
``{ code: ErrorCode, message: str, details?: object }`` per CONTRACTS.md §1. The
HTTP status is derived from the ``ErrorCode``; no raw upstream 5xx body ever
reaches the client (SPEC §6 "Error taxonomy").
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorCode

logger = logging.getLogger(__name__)


# Stable mapping from ErrorCode to HTTP status. Declared here so routes never
# hardcode numbers and so the tests can iterate the whole surface.
ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNKNOWN_TICKER: 404,
    ErrorCode.INSUFFICIENT_HISTORY: 422,
    ErrorCode.DATA_PROVIDER_RATE_LIMIT: 429,
    ErrorCode.DATA_PROVIDER_UNAVAILABLE: 503,
    ErrorCode.OPTIMIZER_INFEASIBLE: 422,
    ErrorCode.OPTIMIZER_NON_PSD_COVARIANCE: 422,
    ErrorCode.INVALID_RISK_PROFILE: 400,
    ErrorCode.INVALID_RETURN_WINDOW: 400,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.INTERNAL: 500,
}


class AppError(Exception):
    """Base typed error. Maps 1:1 to the universal error envelope."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code or ERROR_STATUS.get(code, 500)


class DataProviderError(AppError):
    """Upstream data-provider failure (remapped, never leaked raw)."""


class UnknownTickerError(AppError):
    def __init__(self, ticker: str) -> None:
        super().__init__(
            ErrorCode.UNKNOWN_TICKER,
            f"Unknown ticker: {ticker}",
            {"ticker": ticker},
        )


class InsufficientHistoryError(AppError):
    def __init__(self, ticker: str, n_observations: int, required: int) -> None:
        super().__init__(
            ErrorCode.INSUFFICIENT_HISTORY,
            (
                f"Insufficient history for {ticker}: "
                f"{n_observations} observations available, {required} required"
            ),
            {
                "ticker": ticker,
                "nObservations": n_observations,
                "required": required,
            },
        )


class RateLimitError(AppError):
    def __init__(
        self,
        provider: str,
        retry_after_seconds: float,
        *,
        scope: str = "minute",
    ) -> None:
        super().__init__(
            ErrorCode.DATA_PROVIDER_RATE_LIMIT,
            f"{provider} rate limit exceeded ({scope})",
            {
                "provider": provider,
                "scope": scope,
                "retryAfterSeconds": round(retry_after_seconds, 3),
            },
        )
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(AppError):
    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            ErrorCode.DATA_PROVIDER_UNAVAILABLE,
            f"{provider} unavailable: {reason}",
            {"provider": provider, "reason": reason},
        )


class InvalidReturnWindowError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.INVALID_RETURN_WINDOW, message, details)


def _envelope(code: ErrorCode, message: str, details: dict | None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code.value, "message": message}
    if details is not None:
        body["details"] = jsonable_encoder(details)
    return body


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitError):
        headers["Retry-After"] = str(int(max(1, round(exc.retry_after_seconds))))
    logger.info("app_error code=%s status=%s msg=%s", exc.code.value, exc.status_code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, exc.details),
        headers=headers,
    )


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {"msg": "validation error"}
    message = f"Invalid request: {first.get('msg', 'validation error')}"
    return JSONResponse(
        status_code=400,
        content=_envelope(
            ErrorCode.INVALID_RETURN_WINDOW,
            message,
            {"errors": jsonable_encoder(errors)},
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = exc.status_code
    code = ErrorCode.INTERNAL
    for candidate, mapped in ERROR_STATUS.items():
        if mapped == status:
            code = candidate
            break
    detail = exc.detail if not isinstance(exc.detail, dict) else None
    message = str(detail) if detail else code.value
    details = exc.detail if isinstance(exc.detail, dict) else None
    return JSONResponse(
        status_code=status,
        content=_envelope(code, message, details),
        headers=exc.headers or {},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=_envelope(ErrorCode.INTERNAL, "Internal server error", None),
    )


__all__ = [
    "ERROR_STATUS",
    "AppError",
    "DataProviderError",
    "InsufficientHistoryError",
    "InvalidReturnWindowError",
    "ProviderUnavailableError",
    "RateLimitError",
    "UnknownTickerError",
    "app_error_handler",
    "http_exception_handler",
    "unhandled_exception_handler",
    "validation_handler",
]
