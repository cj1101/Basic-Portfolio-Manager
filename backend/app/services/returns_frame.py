"""Aligned log-return DataFrame for tickers (shared by optimize and analytics)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.errors import InsufficientHistoryError, InvalidReturnWindowError, UnknownTickerError
from app.schemas import PriceBar


def build_return_frame(
    bars_by_ticker: dict[str, list[PriceBar]],
    *,
    column_order: tuple[str, ...],
) -> pd.DataFrame:
    if not bars_by_ticker:
        raise InvalidReturnWindowError("no bars available to build return frame")
    close_frames: dict[str, pd.Series] = {}
    for ticker, bars in bars_by_ticker.items():
        if not bars:
            raise UnknownTickerError(ticker)
        closes = pd.Series(
            {bar.date: float(bar.close) for bar in bars},
            name=ticker,
            dtype="float64",
        )
        closes.index = pd.to_datetime(closes.index)
        closes = closes.sort_index()
        close_frames[ticker] = closes
    frame = pd.concat(close_frames, axis=1, join="inner")
    frame = frame[list(column_order)]
    frame = frame.dropna()
    if frame.shape[0] < 2:
        raise InsufficientHistoryError(
            ",".join(column_order),
            int(frame.shape[0]),
            2,
        )
    returns = np.log(frame.to_numpy(dtype=np.float64))
    diffs = np.diff(returns, axis=0)
    if not np.all(np.isfinite(diffs)):
        raise InvalidReturnWindowError(
            "non-finite log returns computed from historical bars",
            {"nonFiniteCount": int(np.sum(~np.isfinite(diffs)))},
        )
    return pd.DataFrame(
        diffs,
        index=frame.index[1:],
        columns=list(column_order),
    )


__all__ = ["build_return_frame"]
