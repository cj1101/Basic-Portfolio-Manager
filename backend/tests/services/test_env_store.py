from __future__ import annotations

from pathlib import Path

import pytest

from app.services.env_store import EnvStore, EnvStoreError


def test_replace_existing_key(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=old\nFRED_API_KEY=fred\n", encoding="utf-8")
    store = EnvStore(env_path)

    result = store.update_api_key(
        key_name="OPENROUTER_API_KEY",
        new_value="new-value",
        confirm_overwrite=True,
        confirm_create=False,
    )

    assert result.updated is True
    assert result.created is False
    assert result.restart_required is True
    text = env_path.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=new-value" in text
    assert "FRED_API_KEY=fred" in text


def test_missing_key_requires_create_confirmation(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("FRED_API_KEY=fred\n", encoding="utf-8")
    store = EnvStore(env_path)

    result = store.update_api_key(
        key_name="OPENROUTER_API_KEY",
        new_value="new-value",
        confirm_overwrite=False,
        confirm_create=False,
    )

    assert result.updated is False
    assert result.requires_confirmation is True
    assert result.confirmation_type == "create"
    assert "OPENROUTER_API_KEY" not in env_path.read_text(encoding="utf-8")


def test_create_missing_key_after_confirmation(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("FRED_API_KEY=fred\n", encoding="utf-8")
    store = EnvStore(env_path)

    result = store.update_api_key(
        key_name="OPENROUTER_API_KEY",
        new_value="new-value",
        confirm_overwrite=False,
        confirm_create=True,
    )

    assert result.updated is True
    assert result.created is True
    assert "OPENROUTER_API_KEY=new-value" in env_path.read_text(encoding="utf-8")


def test_blank_value_is_noop(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=old\n", encoding="utf-8")
    store = EnvStore(env_path)

    result = store.update_api_key(
        key_name="OPENROUTER_API_KEY",
        new_value="   ",
        confirm_overwrite=True,
        confirm_create=True,
    )

    assert result.updated is False
    assert result.restart_required is False
    assert env_path.read_text(encoding="utf-8") == "OPENROUTER_API_KEY=old\n"


def test_atomic_write_failure_raises_env_store_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=old\n", encoding="utf-8")
    store = EnvStore(env_path)

    def _explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", _explode)

    with pytest.raises(EnvStoreError):
        store.update_api_key(
            key_name="OPENROUTER_API_KEY",
            new_value="new-value",
            confirm_overwrite=True,
            confirm_create=False,
        )

