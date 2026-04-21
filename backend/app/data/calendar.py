"""NYSE trading calendar helpers (SPEC §7: never use ``pd.bdate_range``)."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as Date
from functools import lru_cache

import pandas as pd
import pandas_market_calendars as mcal


@lru_cache(maxsize=1)
def _nyse():
    return mcal.get_calendar("NYSE")


def last_trading_day_on_or_before(reference: Date | datetime) -> Date:
    """Return the NYSE trading session date <= ``reference``.

    ``reference`` may be a date or datetime. If it is a session date, that
    session is returned. Otherwise the previous session is used.
    """

    if isinstance(reference, datetime):
        as_date = reference.astimezone(UTC).date()
    else:
        as_date = reference

    cal = _nyse()
    schedule = cal.schedule(start_date=as_date - pd.Timedelta(days=14), end_date=as_date)
    if schedule.empty:
        raise RuntimeError("NYSE calendar returned empty window")
    last_index = schedule.index[-1]
    if hasattr(last_index, "date"):
        return last_index.date()
    return last_index  # type: ignore[return-value]


def trading_days_between(start: Date, end: Date) -> int:
    """Count NYSE trading sessions in ``[start, end]`` inclusive."""

    if end < start:
        return 0
    cal = _nyse()
    schedule = cal.schedule(start_date=start, end_date=end)
    return len(schedule)


def today_utc() -> Date:
    return datetime.now(tz=UTC).date()


__all__ = ["last_trading_day_on_or_before", "today_utc", "trading_days_between"]
