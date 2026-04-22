"""Hypothesis fuzz tests for the chat intent classifier.

The guarantees we assert are **safety** rather than correctness:

- ``classify_intent`` never raises on *any* Unicode string.
- It never returns a ``ticker`` that wasn't in the ``known_tickers`` list.
- It never returns an ``Intent`` outside the declared enum.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.chat.intent import Intent, classify_intent

_SLOW = settings(
    deadline=None,
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)


@given(
    raw=st.text(min_size=0, max_size=400),
    tickers=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
            min_size=1,
            max_size=5,
        ),
        min_size=0,
        max_size=8,
        unique=True,
    ),
)
@_SLOW
def test_classify_intent_never_crashes(raw: str, tickers: list[str]) -> None:
    result = classify_intent(raw, known_tickers=tickers or None)
    if result is not None:
        assert isinstance(result.intent, Intent)
        if result.ticker is not None:
            # When the classifier resolves a ticker it must be one we told it
            # about. Anything else would be hallucinated provenance.
            assert result.ticker in tickers


@given(
    raw=st.text(
        alphabet=st.characters(whitelist_categories=("Cc", "Cs", "Lu", "Ll", "Nd", "Po", "Sm")),
        min_size=0,
        max_size=200,
    )
)
@_SLOW
def test_classify_intent_survives_control_characters(raw: str) -> None:
    classify_intent(raw)  # just don't crash


@given(raw=st.text(min_size=0, max_size=10_000))
@settings(max_examples=40, deadline=None)
def test_classify_intent_handles_large_input(raw: str) -> None:
    classify_intent(raw)
