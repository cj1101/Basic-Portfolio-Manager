"""Agent E — SQLite chat store round-trip tests."""

from __future__ import annotations

from pathlib import Path

import pytest_asyncio

from app.data.chat_store import ChatStore


@pytest_asyncio.fixture
async def chat_store(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.db")
    await store.connect()
    try:
        yield store
    finally:
        await store.close()


async def test_append_and_list_round_trip(chat_store: ChatStore):
    await chat_store.append_message("sess-1", role="user", content="hello")
    await chat_store.append_message(
        "sess-1",
        role="assistant",
        content="hi there",
        source="rule",
        citations=[("ORP Sharpe", "0.7674")],
    )
    messages = await chat_store.list_messages("sess-1")
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "hello"
    assert messages[0].source is None
    assert messages[0].citations == []
    assert messages[1].role == "assistant"
    assert messages[1].source == "rule"
    assert messages[1].citations == [("ORP Sharpe", "0.7674")]
    # Messages must be returned in chronological order.
    assert messages[0].created_at <= messages[1].created_at


async def test_get_session_returns_none_before_first_message(chat_store: ChatStore):
    assert await chat_store.get_session("missing") is None


async def test_append_creates_session_lazily(chat_store: ChatStore):
    await chat_store.append_message("sess-new", role="user", content="hi")
    session = await chat_store.get_session("sess-new")
    assert session is not None
    assert session.id == "sess-new"
    assert session.portfolio_id is None


async def test_upsert_session_sets_portfolio_id(chat_store: ChatStore):
    session = await chat_store.upsert_session("sess-2", portfolio_id="pf-abc")
    assert session.portfolio_id == "pf-abc"
    # Updating without a portfolio_id preserves the existing value.
    await chat_store.upsert_session("sess-2")
    session = await chat_store.get_session("sess-2")
    assert session is not None
    assert session.portfolio_id == "pf-abc"


async def test_list_messages_respects_limit(chat_store: ChatStore):
    for i in range(5):
        await chat_store.append_message(
            "sess-cap", role="user", content=f"msg {i}"
        )
    tail = await chat_store.list_messages("sess-cap", limit=3)
    assert len(tail) == 3
    # Should return the *most recent* 3, still in chronological order.
    assert [m.content for m in tail] == ["msg 2", "msg 3", "msg 4"]


async def test_list_messages_zero_limit_returns_empty(chat_store: ChatStore):
    await chat_store.append_message("sess-0", role="user", content="hi")
    assert await chat_store.list_messages("sess-0", limit=0) == []


async def test_delete_session_cascades(chat_store: ChatStore):
    await chat_store.append_message("sess-del", role="user", content="hi")
    await chat_store.append_message(
        "sess-del",
        role="assistant",
        content="hello",
        source="llm",
    )
    assert await chat_store.delete_session("sess-del") is True
    assert await chat_store.get_session("sess-del") is None
    assert await chat_store.list_messages("sess-del") == []


async def test_delete_missing_session_returns_false(chat_store: ChatStore):
    assert await chat_store.delete_session("does-not-exist") is False


async def test_malformed_citations_json_is_tolerated(
    chat_store: ChatStore, tmp_path: Path
):
    # Poke malformed JSON directly into the citations column.
    conn = await chat_store._ensure()
    await chat_store.append_message("sess-bad", role="user", content="hi")
    await conn.execute(
        """
        INSERT INTO chat_messages (session_id, role, content, source, citations_json, created_at)
        VALUES ('sess-bad', 'assistant', 'bad', 'rule', '{not json', '2025-01-01T00:00:00Z')
        """
    )
    await conn.commit()
    messages = await chat_store.list_messages("sess-bad")
    assert len(messages) == 2
    # Malformed citations should degrade to an empty list, not raise.
    assistant = [m for m in messages if m.role == "assistant"][0]
    assert assistant.citations == []


async def test_connect_is_idempotent(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.db")
    await store.connect()
    await store.connect()  # second call is a no-op
    await store.close()
