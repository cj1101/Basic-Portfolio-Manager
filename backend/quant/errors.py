"""Typed errors for the Quant Engine.

Every user-facing error raised from :mod:`quant` carries an :class:`ErrorCode`
from the universal taxonomy declared in ``docs/CONTRACTS.md`` §2. Callers (the
FastAPI response layer, to be built in a later phase) are expected to map the
code onto an HTTP status and surface ``{ code, message, details }`` over the
wire.

The math layer is pure: it never emits HTTP, never logs. It raises.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Universal error taxonomy (mirrors ``CONTRACTS.md`` §2)."""

    UNKNOWN_TICKER = "UNKNOWN_TICKER"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    DATA_PROVIDER_RATE_LIMIT = "DATA_PROVIDER_RATE_LIMIT"
    DATA_PROVIDER_UNAVAILABLE = "DATA_PROVIDER_UNAVAILABLE"
    OPTIMIZER_INFEASIBLE = "OPTIMIZER_INFEASIBLE"
    OPTIMIZER_NON_PSD_COVARIANCE = "OPTIMIZER_NON_PSD_COVARIANCE"
    INVALID_RISK_PROFILE = "INVALID_RISK_PROFILE"
    INVALID_RETURN_WINDOW = "INVALID_RETURN_WINDOW"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    INTERNAL = "INTERNAL"


class QuantError(Exception):
    """Base class for every math-layer error.

    Subclasses set a class-level :attr:`code`. Instances carry a human-readable
    ``message`` and an optional ``details`` dict that becomes the wire body's
    ``details`` field after rounding/normalization at the response boundary.
    """

    code: ErrorCode = ErrorCode.INTERNAL

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details) if details else {}

    def to_dict(self) -> dict[str, Any]:
        """Universal error shape: ``{ code, message, details }``."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code.value!r}, message={self.message!r})"


class OptimizerInfeasibleError(QuantError):
    code = ErrorCode.OPTIMIZER_INFEASIBLE


class OptimizerNonPSDCovarianceError(QuantError):
    code = ErrorCode.OPTIMIZER_NON_PSD_COVARIANCE


class InvalidRiskProfileError(QuantError):
    code = ErrorCode.INVALID_RISK_PROFILE


class InvalidReturnWindowError(QuantError):
    code = ErrorCode.INVALID_RETURN_WINDOW


class InsufficientHistoryError(QuantError):
    code = ErrorCode.INSUFFICIENT_HISTORY


class InternalError(QuantError):
    code = ErrorCode.INTERNAL


__all__ = [
    "ErrorCode",
    "InsufficientHistoryError",
    "InternalError",
    "InvalidReturnWindowError",
    "InvalidRiskProfileError",
    "OptimizerInfeasibleError",
    "OptimizerNonPSDCovarianceError",
    "QuantError",
]
