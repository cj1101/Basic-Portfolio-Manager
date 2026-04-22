"""SQLite-backed chat session persistence (CONTRACTS §5.11).

Sessions and messages share the same SQLite file as the market-data cache
(``Settings.cache_db_path``) but own their own :mod:`aiosqlite` connection.
WAL mode + the ``foreign_keys=ON`` pragma make cross-connection reads safe.

Schema
------
``chat_sessions``
    ``id TEXT PK, portfolio_id TEXT NULL, created_at, updated_at``. The
    ``portfolio_id`` FK is reserved for Phase 3C (saved portfolios) and is
    intentionally unenforced today.

``chat_messages``
    Append-only log of user + assistant turns. Assistant rows carry a
    ``source`` (``"rule"`` | ``"llm"``) and optional ``citations_json``.
    ``ON DELETE CASCADE`` purges messages with the session.

The store is deliberately minimal: no summarisation, no pruning, no search.
It exists so the UI can restore history across reloads. Listing is capped
at ``Settings.chat_history_limit`` (default 100) to keep the ChatSession
payload bounded — older turns fall off the tail.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    source TEXT,
    citations_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages(session_id, id);
"""


@dataclass(slots=True, frozen=True)
class StoredSession:
    id: str
    portfolio_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class StoredMessage:
    role: Literal["user", "assistant"]
    content: str
    source: Literal["rule", "llm"] | None
    citations: list[tuple[str, str]]
    created_at: datetime


class ChatStore:
    """Async chat session + message store."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None
        self._init_lock = asyncio.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    async def connect(self) -> None:
        async with self._init_lock:
            if self._conn is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _ensure(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        return self._conn

    async def upsert_session(
        self, session_id: str, portfolio_id: str | None = None
    ) -> StoredSession:
        conn = await self._ensure()
        now = _utcnow()
        now_iso = _to_iso(now)
        await conn.execute(
            """
            INSERT INTO chat_sessions (id, portfolio_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                portfolio_id = COALESCE(excluded.portfolio_id, chat_sessions.portfolio_id)
            """,
            (session_id, portfolio_id, now_iso, now_iso),
        )
        await conn.commit()
        session = await self.get_session(session_id)
        assert session is not None
        return session

    async def get_session(self, session_id: str) -> StoredSession | None:
        conn = await self._ensure()
        async with conn.execute(
            "SELECT id, portfolio_id, created_at, updated_at FROM chat_sessions WHERE id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return StoredSession(
            id=row["id"],
            portfolio_id=row["portfolio_id"],
            created_at=_parse_iso(row["created_at"]),
            updated_at=_parse_iso(row["updated_at"]),
        )

    async def append_message(
        self,
        session_id: str,
        role: Literal["user", "assistant"],
        content: str,
        *,
        source: Literal["rule", "llm"] | None = None,
        citations: list[tuple[str, str]] | None = None,
    ) -> StoredMessage:
        conn = await self._ensure()
        now = _utcnow()
        now_iso = _to_iso(now)
        citations_json = (
            json.dumps([{"label": label, "value": value} for label, value in citations])
            if citations
            else None
        )
        # Ensure the session row exists (lazy create so the caller doesn't have to).
        await conn.execute(
            """
            INSERT INTO chat_sessions (id, portfolio_id, created_at, updated_at)
            VALUES (?, NULL, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (session_id, now_iso, now_iso),
        )
        await conn.execute(
            """
            INSERT INTO chat_messages (session_id, role, content, source, citations_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, role, content, source, citations_json, now_iso),
        )
        await conn.commit()
        return StoredMessage(
            role=role,
            content=content,
            source=source,
            citations=list(citations or []),
            created_at=now,
        )

    async def list_messages(self, session_id: str, *, limit: int = 100) -> list[StoredMessage]:
        if limit <= 0:
            return []
        conn = await self._ensure()
        # Grab the most recent ``limit`` rows, then return them in chronological order.
        async with conn.execute(
            """
            SELECT role, content, source, citations_json, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        messages = [
            StoredMessage(
                role=row["role"],
                content=row["content"],
                source=row["source"],
                citations=_parse_citations(row["citations_json"]),
                created_at=_parse_iso(row["created_at"]),
            )
            for row in rows
        ]
        messages.reverse()
        return messages

    async def delete_session(self, session_id: str) -> bool:
        conn = await self._ensure()
        cur = await conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        await conn.commit()
        return cur.rowcount > 0


def _parse_citations(raw: str | None) -> list[tuple[str, str]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("chat_store: malformed citations_json, skipping")
        return []
    out: list[tuple[str, str]] = []
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and "label" in entry and "value" in entry:
                out.append((str(entry["label"]), str(entry["value"])))
    return out


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["ChatStore", "StoredMessage", "StoredSession"]
