"""Tests for ``quant.capm`` using Dataset A §5.6."""

from __future__ import annotations

import pytest

from quant.capm import (
    capm_required_return,
    capm_systematic_variance,
    capm_total_expected_return,
    capm_total_std_dev,
    capm_total_variance,
)

from ..conftest import DatasetACAPMFixture, TOLERANCE_SCALAR


def test_required_return(dataset_a_capm: DatasetACAPMFixture) -> None:
    r = capm_required_return(
        beta=dataset_a_capm.beta,
        market_expected_return=dataset_a_capm.market_expected_return,
        risk_free_rate=dataset_a_capm.risk_free_rate,
    )
    assert r == pytest.approx(dataset_a_capm.required_return, abs=TOLERANCE_SCALAR)


def test_total_expected_return(dataset_a_capm: DatasetACAPMFixture) -> None:
    r = capm_total_expected_return(
        beta=dataset_a_capm.beta,
        alpha=dataset_a_capm.alpha,
        market_expected_return=dataset_a_capm.market_expected_return,
        risk_free_rate=dataset_a_capm.risk_free_rate,
    )
    assert r == pytest.approx(dataset_a_capm.total_expected_return, abs=TOLERANCE_SCALAR)


def test_systematic_variance(dataset_a_capm: DatasetACAPMFixture) -> None:
    v = capm_systematic_variance(dataset_a_capm.beta, dataset_a_capm.market_variance)
    assert v == pytest.approx(dataset_a_capm.systematic_variance, abs=TOLERANCE_SCALAR)


def test_total_variance_and_std(dataset_a_capm: DatasetACAPMFixture) -> None:
    v = capm_total_variance(
        dataset_a_capm.beta,
        dataset_a_capm.market_variance,
        dataset_a_capm.firm_specific_var,
    )
    sd = capm_total_std_dev(
        dataset_a_capm.beta,
        dataset_a_capm.market_variance,
        dataset_a_capm.firm_specific_var,
    )
    assert v == pytest.approx(dataset_a_capm.total_variance, abs=TOLERANCE_SCALAR)
    assert sd == pytest.approx(dataset_a_capm.std_dev, abs=TOLERANCE_SCALAR)


def test_zero_beta_yields_risk_free() -> None:
    assert capm_required_return(0.0, 0.10, 0.04) == pytest.approx(0.04)


def test_beta_one_yields_market() -> None:
    assert capm_required_return(1.0, 0.10, 0.04) == pytest.approx(0.10)


def test_negative_market_variance_raises() -> None:
    with pytest.raises(ValueError):
        capm_systematic_variance(1.0, -0.01)


def test_negative_firm_specific_var_raises() -> None:
    with pytest.raises(ValueError):
        capm_total_variance(1.0, 0.01, -0.01)
