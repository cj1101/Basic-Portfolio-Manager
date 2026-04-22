"""Agent E — Chat Assistant service package.

Entry points:

- :class:`ChatService` (``service.py``) — orchestrates rule / llm / auto modes.
- :func:`classify_intent` / :class:`Intent` (``intent.py``) — deterministic
  keyword+regex classifier over the Core 5 intents declared in
  ``docs/SPEC.md`` §3 decision 5.
- :mod:`rules` — pure templated answer generators keyed by intent.
- :class:`OpenRouterChatClient` (``llm.py``) — thin async wrapper around
  OpenRouter's OpenAI-compatible Chat Completions API with timeouts +
  error normalisation onto ``LLM_UNAVAILABLE``.
"""

from app.services.chat.intent import Intent, IntentMatch, classify_intent
from app.services.chat.llm import OpenAIChatClient, OpenRouterChatClient
from app.services.chat.rules import render_rule_answer
from app.services.chat.service import ChatService

__all__ = [
    "ChatService",
    "Intent",
    "IntentMatch",
    "OpenAIChatClient",
    "OpenRouterChatClient",
    "classify_intent",
    "render_rule_answer",
]
