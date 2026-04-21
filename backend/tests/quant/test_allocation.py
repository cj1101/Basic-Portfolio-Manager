"""Tests for ``quant.allocation``."""

from __future__ import annotations

import pytest

from quant.allocation import utility_max_allocation
from quant.errors import InvalidRiskProfileError
from quant.types import ORP, RiskProfile

from ..conftest import DatasetAFixture, TOLERANCE_SCALAR, TOLERANCE_WEIGHT_SUM


def _orp_from_dataset_a(dataset_a: DatasetAFixture) -> ORP:
    return ORP(
        weights=dict(dataset_a.orp_weights),
        expected_return=dataset_a.orp_expected_return,
        std_dev=dataset_a.orp_std_dev,
        variance=dataset_a.orp_variance,
        sharpe=dataset_a.orp_sharpe,
    )


class TestDatasetALeverageCase:
    """A = 4 → y* = 1.5625, leverage used."""

    def test_y_star_and_leverage_flag(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=4),
            allow_leverage=True,
        )
        assert complete.y_star == pytest.approx(1.5625, abs=TOLERANCE_SCALAR)
        assert complete.leverage_used is True
        assert complete.weight_risk_free == pytest.approx(-0.5625, abs=TOLERANCE_SCALAR)

    def test_risky_weights(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=4),
            allow_leverage=True,
        )
        expected = {"S1": 2.0 / 3.0, "S2": 9.0 / 16.0, "S3": 1.0 / 3.0}
        for t, w in expected.items():
            assert complete.weights[t] == pytest.approx(w, abs=TOLERANCE_SCALAR)
        assert sum(complete.weights.values()) + complete.weight_risk_free == pytest.approx(
            1.0, abs=TOLERANCE_WEIGHT_SUM
        )

    def test_moments(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=4),
            allow_leverage=True,
        )
        assert complete.expected_return == pytest.approx(0.170625, abs=TOLERANCE_SCALAR)
        assert complete.std_dev == pytest.approx(0.180711, abs=TOLERANCE_SCALAR)


class TestDatasetANoLeverageCase:
    """A = 8 → y* = 0.78125, no leverage."""

    def test_y_star_and_leverage_flag(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=8),
            allow_leverage=True,
        )
        assert complete.y_star == pytest.approx(0.78125, abs=TOLERANCE_SCALAR)
        assert complete.leverage_used is False
        assert complete.weight_risk_free == pytest.approx(0.21875, abs=TOLERANCE_SCALAR)

    def test_risky_weights(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=8),
            allow_leverage=True,
        )
        expected = {"S1": 1.0 / 3.0, "S2": 9.0 / 32.0, "S3": 1.0 / 6.0}
        for t, w in expected.items():
            assert complete.weights[t] == pytest.approx(w, abs=TOLERANCE_SCALAR)

    def test_moments(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=8),
            allow_leverage=True,
        )
        assert complete.expected_return == pytest.approx(0.105313, abs=TOLERANCE_SCALAR)
        assert complete.std_dev == pytest.approx(0.090356, abs=TOLERANCE_SCALAR)


class TestTargetReturnOverride:
    def test_target_below_orp_does_not_override(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        warnings: list[str] = []
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=8, target_return=0.08),
            allow_leverage=True,
            warnings=warnings,
        )
        assert complete.y_star == pytest.approx(0.78125, abs=TOLERANCE_SCALAR)
        assert warnings == []

    def test_target_above_orp_overrides_with_warning(
        self, dataset_a: DatasetAFixture
    ) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        warnings: list[str] = []
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=8, target_return=0.20),
            allow_leverage=True,
            warnings=warnings,
        )
        # y_target = (0.20 - 0.04) / 0.0836 ≈ 1.91387
        expected_y = (0.20 - dataset_a.risk_free_rate) / (
            dataset_a.orp_expected_return - dataset_a.risk_free_rate
        )
        assert complete.y_star == pytest.approx(expected_y, abs=TOLERANCE_SCALAR)
        assert complete.leverage_used is True
        assert len(warnings) == 1 and "targetReturn" in warnings[0]


class TestLeverageClamping:
    def test_disallowed_leverage_clamps_to_one(self, dataset_a: DatasetAFixture) -> None:
        orp = _orp_from_dataset_a(dataset_a)
        warnings: list[str] = []
        complete = utility_max_allocation(
            orp=orp,
            risk_free_rate=dataset_a.risk_free_rate,
            risk_profile=RiskProfile(risk_aversion=4),
            allow_leverage=False,
            warnings=warnings,
        )
        assert complete.y_star == pytest.approx(1.0, abs=TOLERANCE_SCALAR)
        assert complete.leverage_used is False
        assert complete.weight_risk_free == pytest.approx(0.0, abs=TOLERANCE_WEIGHT_SUM)
        assert len(warnings) == 1 and "leverage disabled" in warnings[0]


class TestInvalidProfiles:
    def test_negative_risk_premium_raises(self, dataset_a: DatasetAFixture) -> None:
        # ORP with expected return below rf → y* < 0.
        bad_orp = ORP(
            weights=dict(dataset_a.orp_weights),
            expected_return=0.02,
            std_dev=dataset_a.orp_std_dev,
            variance=dataset_a.orp_variance,
            sharpe=-1.0,
        )
        with pytest.raises(InvalidRiskProfileError):
            utility_max_allocation(
                orp=bad_orp,
                risk_free_rate=dataset_a.risk_free_rate,
                risk_profile=RiskProfile(risk_aversion=4),
                allow_leverage=True,
            )

    def test_zero_variance_raises(self, dataset_a: DatasetAFixture) -> None:
        bad_orp = ORP(
            weights=dict(dataset_a.orp_weights),
            expected_return=0.10,
            std_dev=0.0,
            variance=0.0,
            sharpe=0.0,
        )
        with pytest.raises(InvalidRiskProfileError):
            utility_max_allocation(
                orp=bad_orp,
                risk_free_rate=dataset_a.risk_free_rate,
                risk_profile=RiskProfile(risk_aversion=4),
                allow_leverage=True,
            )

    def test_target_return_with_zero_premium_raises(
        self, dataset_a: DatasetAFixture
    ) -> None:
        # ORP with E(r) == rf — any target above that is infeasible.
        flat_orp = ORP(
            weights=dict(dataset_a.orp_weights),
            expected_return=dataset_a.risk_free_rate,
            std_dev=dataset_a.orp_std_dev,
            variance=dataset_a.orp_variance,
            sharpe=0.0,
        )
        with pytest.raises(InvalidRiskProfileError):
            utility_max_allocation(
                orp=flat_orp,
                risk_free_rate=dataset_a.risk_free_rate,
                risk_profile=RiskProfile(risk_aversion=4, target_return=0.10),
                allow_leverage=True,
            )
