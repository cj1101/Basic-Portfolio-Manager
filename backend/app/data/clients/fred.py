"""FRED client — fetches the 3-month T-bill (``DGS3MO``) for the risk-free rate.

When ``FRED_API_KEY`` is absent the caller must fall back to the documented
constant in ``app.settings.FRED_FALLBACK_RATE``; this module never invents a
value itself. SPEC §3 #4 allows that behaviour and requires the response
``source`` to be ``"FALLBACK"``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from datetime import date as Date
from typing import Any

import httpx

from app.errors import ProviderUnavailableError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "fred"
SERIES_ID = "DGS3MO"


class FredClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.stlouisfed.org/fred/series/observations",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required; use the fallback path if unset")
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._http_client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> FredClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def get_latest_dgs3mo(self) -> dict[str, Any]:
        """Return ``{"rate": decimal, "as_of": datetime, "source": "FRED"}``.

        FRED publishes DGS3MO as a percent (e.g. ``"5.23"``). We convert to
        decimal per SPEC §1 (``0.0523``).
        """

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)

        params = {
            "series_id": SERIES_ID,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": "10",
        }

        try:
            resp = await self._http_client.get(self._base_url, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, "timeout") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc

        if resp.status_code >= 500:
            raise ProviderUnavailableError(
                PROVIDER_NAME, f"upstream {resp.status_code}"
            )
        if resp.status_code >= 400:
            raise ProviderUnavailableError(
                PROVIDER_NAME, f"status {resp.status_code}"
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, "invalid JSON") from exc

        observations = payload.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ProviderUnavailableError(PROVIDER_NAME, "no observations returned")

        for obs in observations:
            value = obs.get("value")
            date_str = obs.get("date")
            if value in (None, ".", ""):
                continue
            try:
                percent = float(value)
            except (TypeError, ValueError):
                continue
            try:
                as_of_date = Date.fromisoformat(date_str)
            except (TypeError, ValueError) as exc:
                raise ProviderUnavailableError(
                    PROVIDER_NAME, f"invalid observation date {date_str!r}"
                ) from exc
            as_of = datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC)
            return {"rate": percent / 100.0, "as_of": as_of, "source": "FRED"}

        raise ProviderUnavailableError(
            PROVIDER_NAME, "no non-null observation in the latest 10 rows"
        )


__all__ = ["PROVIDER_NAME", "SERIES_ID", "FredClient"]
