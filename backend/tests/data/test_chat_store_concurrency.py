"""Concurrency stress test for ``ChatStore.append_message``.

SQLite serializes writes but a careless caller that forgets to await
``conn.commit()`` between inserts can still lose rows under aiosqlite's
shared-connection model. These tests slam the store with 100 concurrent
appends for the same session and assert:

- All messages make it in.
- Ordering by ``created_at`` (and implicit insert order) is preserved.
- ``list_messages`` returns the full ordered history.
- Interleaved user/assistant appends for different sessions stay isolated.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.data.chat_store import ChatStore

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def chat_store(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.db")
    await store.connect()
    try:
        yield store
    finally:
        await store.close()


async def test_append_message_survives_100_concurrent_writers(
    chat_store: ChatStore,
) -> None:
    session_id = "stress-session"
    n = 100

    async def write(i: int) -> None:
        await chat_store.append_message(
            session_id=session_id,
            role="user",
            content=f"msg-{i:03d}",
        )

    await asyncio.gather(*(write(i) for i in range(n)))

    messages = await chat_store.list_messages(session_id, limit=n + 10)
    assert len(messages) == n

    contents = {m.content for m in messages}
    expected = {f"msg-{i:03d}" for i in range(n)}
    assert contents == expected

    # Created_at must be non-decreasing (chronological order).
    timestamps = [m.created_at for m in messages]
    assert timestamps == sorted(timestamps)


async def test_concurrent_sessions_stay_isolated(chat_store: ChatStore) -> None:
    """Parallel appends across different sessions must not cross-contaminate."""

    async def write(session_id: str, idx: int) -> None:
        await chat_store.append_message(
            session_id=session_id,
            role="assistant" if idx % 2 == 0 else "user",
            content=f"{session_id}-msg-{idx}",
            source="llm" if idx % 2 == 0 else None,
        )

    tasks = []
    for sess in ("A", "B", "C"):
        for i in range(30):
            tasks.append(write(sess, i))
    await asyncio.gather(*tasks)

    for sess in ("A", "B", "C"):
        msgs = await chat_store.list_messages(sess, limit=100)
        assert len(msgs) == 30
        for m in msgs:
            assert m.content.startswith(f"{sess}-msg-")


async def test_interleaved_roles_preserve_insert_order(
    chat_store: ChatStore,
) -> None:
    session_id = "ordered"
    n = 50

    # Interleave user/assistant messages serially (to guarantee a canonical
    # order) and then verify ``list_messages`` returns them in that order.
    expected: list[str] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"{role}:{i}"
        expected.append(content)
        await chat_store.append_message(session_id, role, content)

    msgs = await chat_store.list_messages(session_id, limit=n)
    actual = [m.content for m in msgs]
    assert actual == expected
