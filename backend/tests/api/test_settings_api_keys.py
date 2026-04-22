from __future__ import annotations

from pathlib import Path

import httpx

import app.api.settings as settings_api
from app.services.env_store import EnvStore


async def test_update_allowlisted_key_happy_path(
    api_client: httpx.AsyncClient, tmp_path: Path, monkeypatch
):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(settings_api, "get_backend_env_store", lambda: EnvStore(env_path))

    resp = await api_client.patch(
        "/api/settings/api-keys",
        json={"keyName": "OPENROUTER_API_KEY", "newValue": "new-value", "confirmOverwrite": True},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["updated"] is True
    assert payload["requiresConfirmation"] is False
    assert payload["restartRequired"] is True
    assert "OPENROUTER_API_KEY=new-value" in env_path.read_text(encoding="utf-8")


async def test_non_allowlisted_key_rejected(api_client: httpx.AsyncClient):
    resp = await api_client.patch(
        "/api/settings/api-keys",
        json={"keyName": "SOME_OTHER_KEY", "newValue": "value"},
    )
    assert resp.status_code == 400
    payload = resp.json()
    assert payload["code"] == "INVALID_RETURN_WINDOW"


async def test_existing_key_requires_confirmation(
    api_client: httpx.AsyncClient, tmp_path: Path, monkeypatch
):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(settings_api, "get_backend_env_store", lambda: EnvStore(env_path))

    resp = await api_client.patch(
        "/api/settings/api-keys",
        json={"keyName": "OPENROUTER_API_KEY", "newValue": "new-value"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["updated"] is False
    assert payload["requiresConfirmation"] is True
    assert payload["confirmationType"] == "overwrite"
    assert "OPENROUTER_API_KEY=old" in env_path.read_text(encoding="utf-8")

