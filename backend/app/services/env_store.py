from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.schemas import ApiKeyName


@dataclass(frozen=True)
class EnvUpdateResult:
    updated: bool
    created: bool
    restart_required: bool
    requires_confirmation: bool
    confirmation_type: str | None
    message: str


class EnvStoreError(Exception):
    pass


class EnvStore:
    def __init__(self, env_path: Path) -> None:
        self._env_path = env_path

    def update_api_key(
        self,
        key_name: ApiKeyName,
        new_value: str,
        *,
        confirm_overwrite: bool,
        confirm_create: bool,
    ) -> EnvUpdateResult:
        if new_value.strip() == "":
            return EnvUpdateResult(
                updated=False,
                created=False,
                restart_required=False,
                requires_confirmation=False,
                confirmation_type=None,
                message="Empty value ignored. Existing key remains unchanged.",
            )

        raw = self._env_path.read_text(encoding="utf-8") if self._env_path.exists() else ""
        line_ending = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.splitlines()
        pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key_name)}\s*=")
        existing_idx = next((idx for idx, line in enumerate(lines) if pattern.match(line)), None)

        if existing_idx is not None:
            if not confirm_overwrite:
                return EnvUpdateResult(
                    updated=False,
                    created=False,
                    restart_required=False,
                    requires_confirmation=True,
                    confirmation_type="overwrite",
                    message=f"{key_name} already exists. Confirm overwrite to continue.",
                )
            lines[existing_idx] = f"{key_name}={new_value}"
            self._atomic_write(lines, line_ending)
            return EnvUpdateResult(
                updated=True,
                created=False,
                restart_required=True,
                requires_confirmation=False,
                confirmation_type=None,
                message=f"{key_name} updated in backend/.env. Restart backend to apply.",
            )

        if not confirm_create:
            return EnvUpdateResult(
                updated=False,
                created=False,
                restart_required=False,
                requires_confirmation=True,
                confirmation_type="create",
                message=f"{key_name} is missing. Confirm creation to append it to backend/.env.",
            )

        lines.append(f"{key_name}={new_value}")
        self._atomic_write(lines, line_ending)
        return EnvUpdateResult(
            updated=True,
            created=True,
            restart_required=True,
            requires_confirmation=False,
            confirmation_type=None,
            message=f"{key_name} created in backend/.env. Restart backend to apply.",
        )

    def _atomic_write(self, lines: list[str], line_ending: str) -> None:
        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        content = line_ending.join(lines)
        if lines:
            content += line_ending
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=str(self._env_path.parent),
                newline="",
            ) as handle:
                handle.write(content)
                tmp_path = Path(handle.name)
            tmp_path.replace(self._env_path)
        except OSError as exc:
            raise EnvStoreError("Failed to persist backend/.env") from exc


def get_backend_env_store() -> EnvStore:
    backend_root = Path(__file__).resolve().parents[2]
    return EnvStore(backend_root / ".env")
