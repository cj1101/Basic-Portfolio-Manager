"""Tests for ``quant.sharpe``."""

from __future__ import annotations

import math

import pytest

from quant.sharpe import sharpe_ratio

from ..conftest import DatasetAFixture, TOLERANCE_SCALAR


def test_dataset_a_orp_sharpe(dataset_a: DatasetAFixture) -> None:
    sr = sharpe_ratio(
        dataset_a.orp_expected_return,
        dataset_a.orp_std_dev,
        dataset_a.risk_free_rate,
    )
    assert sr == pytest.approx(dataset_a.orp_sharpe, abs=TOLERANCE_SCALAR)
    assert sr == pytest.approx(math.sqrt(0.5225), abs=TOLERANCE_SCALAR)


def test_non_positive_std_raises() -> None:
    with pytest.raises(ValueError):
        sharpe_ratio(0.1, 0.0, 0.04)


def test_non_finite_raises() -> None:
    with pytest.raises(ValueError):
        sharpe_ratio(float("nan"), 0.2, 0.04)
