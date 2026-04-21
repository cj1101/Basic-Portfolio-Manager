"""Linear-algebra primitives used by the Quant Engine.

Covariance matrices in this project are required to be **symmetric** and
**positive semi-definite** (PSD) per ``.cursor/rules/quant.mdc`` §2. This
module provides the construction and validation helpers; anything that drifts
slightly out of PSD is projected onto the nearest PSD matrix via
:func:`nearest_psd`. Anything that drifts substantially is rejected with
:class:`OptimizerNonPSDCovarianceError` — we never paper over real bugs with
silent regularization epsilons.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .errors import OptimizerNonPSDCovarianceError

SYMMETRY_TOL: float = 1e-10
"""Maximum allowed ``max |Σ − Σᵀ|`` before a matrix is considered asymmetric."""

PSD_TOL: float = 1e-8
"""Minimum allowed eigenvalue before a matrix is considered non-PSD."""

PROJECTION_FLOOR: float = 1e-12
"""Floor applied to clipped eigenvalues inside :func:`nearest_psd`."""


def build_covariance(
    std_devs: NDArray[np.float64] | list[float],
    correlation: NDArray[np.float64] | list[list[float]],
) -> NDArray[np.float64]:
    """Construct Σ from annualized std-devs and a correlation matrix.

    ``Σᵢⱼ = σᵢ · σⱼ · ρᵢⱼ``. The diagonal is ``σᵢ²`` when ``ρᵢᵢ = 1``.

    Returns a symmetrized numpy array (averaging with its transpose to erase
    floating-point drift from the outer product).
    """
    sigma = np.asarray(std_devs, dtype=np.float64).reshape(-1)
    rho = np.asarray(correlation, dtype=np.float64)
    n = sigma.shape[0]
    if rho.shape != (n, n):
        raise ValueError(
            f"correlation must be ({n},{n}) to match std_devs of length {n}; got {rho.shape}"
        )
    if np.any(sigma < 0):
        raise ValueError("std_devs must all be non-negative")
    cov = (sigma[:, None] * sigma[None, :]) * rho
    return 0.5 * (cov + cov.T)


def is_symmetric(m: NDArray[np.float64], tol: float = SYMMETRY_TOL) -> bool:
    a = np.asarray(m, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        return False
    return bool(np.max(np.abs(a - a.T)) <= tol)


def is_psd(m: NDArray[np.float64], tol: float = PSD_TOL) -> bool:
    """True when ``m`` is symmetric and has ``min λ ≥ −tol``."""
    a = np.asarray(m, dtype=np.float64)
    if not is_symmetric(a, tol=max(SYMMETRY_TOL, tol)):
        return False
    w = np.linalg.eigvalsh(0.5 * (a + a.T))
    return bool(np.min(w) >= -tol)


def nearest_psd(m: NDArray[np.float64], eps: float = PROJECTION_FLOOR) -> NDArray[np.float64]:
    """Project ``m`` onto the nearest PSD matrix (Frobenius sense).

    Symmetrizes, eigendecomposes, clips eigenvalues at ``eps``, reconstructs.
    The returned matrix is symmetrized again to remove residual asymmetry from
    floating-point reconstruction.
    """
    a = np.asarray(m, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError("nearest_psd requires a square 2D matrix")
    symmetric = 0.5 * (a + a.T)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    clipped = np.clip(eigenvalues, eps, None)
    psd = (eigenvectors * clipped) @ eigenvectors.T
    return 0.5 * (psd + psd.T)


def ensure_psd_covariance(
    m: NDArray[np.float64] | list[list[float]],
    warnings: list[str] | None = None,
) -> NDArray[np.float64]:
    """Validate and (if necessary) project a covariance matrix onto PSD.

    Behavior:

    - Asymmetric beyond :data:`SYMMETRY_TOL` → :class:`OptimizerNonPSDCovarianceError`.
    - ``min λ < −PSD_TOL`` (substantial non-PSD) → :class:`OptimizerNonPSDCovarianceError`.
    - ``−PSD_TOL ≤ min λ < 0`` (minor numerical drift) → project via
      :func:`nearest_psd` and append a message to ``warnings`` (if provided).
    - PSD → returned as a symmetrized copy.
    """
    a = np.asarray(m, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise OptimizerNonPSDCovarianceError(
            "covariance matrix must be square 2D",
            {"shape": list(a.shape)},
        )

    asym = float(np.max(np.abs(a - a.T))) if a.size else 0.0
    if asym > SYMMETRY_TOL:
        raise OptimizerNonPSDCovarianceError(
            "covariance matrix is not symmetric",
            {"maxAsymmetry": asym, "tolerance": SYMMETRY_TOL},
        )

    symmetric = 0.5 * (a + a.T)
    eigenvalues = np.linalg.eigvalsh(symmetric)
    min_eig = float(np.min(eigenvalues))

    if min_eig < -PSD_TOL:
        raise OptimizerNonPSDCovarianceError(
            "covariance matrix is materially non-PSD; refusing to project",
            {"minEigenvalue": min_eig, "tolerance": PSD_TOL},
        )

    if min_eig < 0:
        projected = nearest_psd(symmetric)
        if warnings is not None:
            warnings.append(
                "covariance had minor PSD drift "
                f"(minEigenvalue={min_eig:.3e}); projected to nearest PSD"
            )
        return projected

    return symmetric


__all__ = [
    "PROJECTION_FLOOR",
    "PSD_TOL",
    "SYMMETRY_TOL",
    "build_covariance",
    "ensure_psd_covariance",
    "is_psd",
    "is_symmetric",
    "nearest_psd",
]
