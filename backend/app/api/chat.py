"""POST /api/chat — the AI assistant endpoint (task #11).

Contract:
    - Body: {message: str, history?: [{role: "user"|"assistant", content: str}]}
    - 200: {reply, sources, provider}
    - 503 with a clear reason when no provider key is configured (chat is
      OPTIONAL — the app works fully without it) or when every configured
      provider failed.
    - History is capped and sanitized (roles forced, length capped) — the
      loop re-seeds its own system prompt server-side; client history can
      never inject one.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.app.services import chat_bot, chat_providers

router = APIRouter()

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 12


class ChatTurn(BaseModel):
    role: str
    content: str = Field(..., max_length=MAX_MESSAGE_CHARS)

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in ("user", "assistant"):
            raise ValueError('history roles must be "user" or "assistant"')
        return v


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


@router.post("/api/chat")
def post_chat(req: ChatRequest) -> dict:
    try:
        result = chat_bot.run_chat(
            req.message,
            [t.model_dump() for t in req.history],
        )
    except chat_providers.NoProviderError as exc:
        raise HTTPException(
            503,
            f"AI chat is not configured: {exc}",
        ) from exc
    except chat_providers.ProviderError as exc:
        raise HTTPException(503, f"All AI providers failed: {exc}") from exc

    # Strip the internal provider marker from the response payload shape;
    # provider NAME is surfaced (nice for debugging free-tier failover).
    return {
        "reply": result["reply"],
        "sources": result["sources"],
        "provider": result["provider"],
    }
