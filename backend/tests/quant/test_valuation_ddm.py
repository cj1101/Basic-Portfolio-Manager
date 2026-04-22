"""Dividend discount models."""

from __future__ import annotations

import pytest

from quant.valuation_ddm import ddm_gordon, ddm_two_stage


def test_gordon() -> None:
    # P = D1 / (k - g)
    assert ddm_gordon(d1=2.0, cost_of_equity=0.10, growth=0.02) == pytest.approx(25.0)


def test_gordon_requires_spread() -> None:
    with pytest.raises(ValueError, match="k_e"):
        ddm_gordon(d1=1.0, cost_of_equity=0.03, growth=0.03)


def test_two_stage_matches_manual_n2() -> None:
    # d0=1, g1=10%, g2=2%, k=12%, n=2
    # D1=1.1, D2=1.21, PV1=1.1/1.12, PV2=1.21/1.12^2
    # terminal P2 = D3/(k-g2), D3=1.21*1.02, PVterm = P2/1.12^2
    k = 0.12
    g1 = 0.10
    g2 = 0.02
    n = 2
    d0 = 1.0
    d = d0
    pv = 0.0
    for t in range(1, n + 1):
        d = d * (1.0 + g1)
        pv += d / (1.0 + k) ** t
    d_next = d * (1.0 + g2)
    terminal = d_next / (k - g2) / (1.0 + k) ** n
    expected = pv + terminal
    assert ddm_two_stage(d0, g1, g2, n, k) == pytest.approx(expected)
