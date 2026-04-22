"""``POST /api/chat`` + chat session CRUD (CONTRACTS §5.9 / §5.11).

Agent E: a thin HTTP layer on top of :class:`ChatService` and :class:`ChatStore`.
Responsibilities here are strictly:

- Parse the request into typed Pydantic models.
- Delegate answer generation to :class:`ChatService`.
- When ``session_id`` is provided (on ``POST /api/chat``) or present in the
  path (on ``POST /api/chat/sessions/{id}/messages``), persist both the
  trailing user turn and the assistant reply via :class:`ChatStore`.
- Never touch OpenAI or the rule engine directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_chat_service, get_chat_store
from app.data.chat_store import ChatStore, StoredMessage
from app.schemas import (
    ChatCitation,
    ChatHistoryEntry,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSource,
)
from app.services.chat.service import ChatService

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_by_alias=True,
)
async def post_chat(
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    chat_store: ChatStore = Depends(get_chat_store),
) -> ChatResponse:
    response = await chat_service.answer(
        messages=list(body.messages),
        context=body.portfolio_context,
        mode=body.mode,
        model=body.model,
    )
    if body.session_id:
        await _persist_turn(chat_store, body.session_id, body.messages, response)
    return response


@router.get(
    "/chat/sessions/{session_id}",
    response_model=ChatSessionResponse,
    response_model_by_alias=True,
)
async def get_chat_session(
    session_id: str,
    chat_store: ChatStore = Depends(get_chat_store),
) -> ChatSessionResponse:
    session = await chat_store.get_session(session_id)
    messages = await chat_store.list_messages(session_id, limit=_history_limit(chat_store))
    if session is None:
        return ChatSessionResponse(
            session_id=session_id,
            portfolio_id=None,
            created_at=_fallback_timestamp(messages),
            updated_at=_fallback_timestamp(messages),
            messages=[_to_history_entry(m) for m in messages],
        )
    return ChatSessionResponse(
        session_id=session.id,
        portfolio_id=session.portfolio_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[_to_history_entry(m) for m in messages],
    )


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatResponse,
    response_model_by_alias=True,
)
async def post_chat_session_message(
    session_id: str,
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    chat_store: ChatStore = Depends(get_chat_store),
) -> ChatResponse:
    response = await chat_service.answer(
        messages=list(body.messages),
        context=body.portfolio_context,
        mode=body.mode,
        model=body.model,
    )
    await _persist_turn(chat_store, session_id, body.messages, response)
    return response


@router.delete(
    "/chat/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_chat_session(
    session_id: str,
    chat_store: ChatStore = Depends(get_chat_store),
) -> Response:
    await chat_store.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _persist_turn(
    store: ChatStore,
    session_id: str,
    messages: list[ChatMessage],
    response: ChatResponse,
) -> None:
    user_msg = _last_user_message(messages)
    if user_msg is not None:
        await store.append_message(
            session_id,
            role="user",
            content=user_msg.content,
        )
    await store.append_message(
        session_id,
        role="assistant",
        content=response.answer,
        source=response.source.value,
        citations=[(c.label, c.value) for c in response.citations],
    )


def _history_limit(store: ChatStore) -> int:
    # ChatStore's own ``list_messages`` clamps on its side; we just forward the
    # configured default from Settings at app startup. Keeping a local default
    # here means the dep signature stays plain and tests can stub the store.
    return 100


def _last_user_message(messages: list[ChatMessage]) -> ChatMessage | None:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg
    return None


def _to_history_entry(message: StoredMessage) -> ChatHistoryEntry:
    source = ChatSource(message.source) if message.source else None
    return ChatHistoryEntry(
        role=message.role,
        content=message.content,
        source=source,
        citations=[ChatCitation(label=lbl, value=val) for lbl, val in message.citations],
        created_at=message.created_at,
    )


def _fallback_timestamp(messages: list[StoredMessage]):
    if messages:
        return messages[-1].created_at
    from datetime import UTC, datetime

    return datetime.now(UTC)


__all__ = ["router"]
