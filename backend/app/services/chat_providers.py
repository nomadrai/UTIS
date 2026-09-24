"""AI provider fallback chain for the chat bot (task #11).

All three providers (Groq, Google AI Studio, OpenRouter) speak the
OpenAI-compatible /chat/completions protocol, so one minimal client serves
all of them: the chain is just an ordered list of (base_url, key, model).

Policy (see PLAN.md Phase-2 notes):
    - First provider WITH a configured key wins; on rate-limit (429), auth
      failure (401/403), timeout, or connection error the chain moves on.
    - No SDK dependency: the OpenAI-compatible surface we need is one POST
      with tools — implemented with urllib so the bot adds zero packages.
    - Providers are re-read per call (get_providers) so adding a key to
      backend/.env takes effect without a server restart.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from backend.config import settings

# Status codes that justify failing over to the next provider. 5xxs are NOT
# here: a 500 from one provider is usually a malformed-request bug on our
# side and retrying it elsewhere just triples latency for the same error.
FAILOVER_STATUS = {401, 403, 408, 429}


class NoProviderError(RuntimeError):
    """No provider has an API key configured (chat is disabled)."""


class ProviderError(RuntimeError):
    """Every configured provider failed; carries the last error."""


def get_providers() -> list[dict]:
    """Ordered provider configs that currently have a key set.

    Re-reads the environment on every call so .env edits apply live.
    """
    out = []
    for p in settings.AI_PROVIDERS:
        key = (os_getenv(p["api_key_env"]) or "").strip()
        if not key:
            continue
        model = (os_getenv(p["model_env"]) or "").strip() or p["default_model"]
        out.append({**p, "api_key": key, "model": model})
    return out


def os_getenv(name: str) -> str | None:
    # Indirection keeps the module importable in tests that patch os.environ.
    import os

    return os.getenv(name)


def chat_completion(payload: dict) -> dict:
    """POST payload to the first provider that succeeds; return its response.

    Payload: OpenAI chat-completions body WITHOUT the `model` field (the
    provider's configured model is injected per attempt).

    Raises NoProviderError if nothing is configured; ProviderError if every
    configured provider failed.
    """
    providers = get_providers()
    if not providers:
        raise NoProviderError(
            "No AI provider configured — set GROQ_API_KEY (or Google AI / "
            "OpenRouter) in backend/.env (see backend/.env.example)."
        )

    last_err: Exception | None = None
    for p in providers:
        body = {**payload, "model": p["model"]}
        try:
            return _post(p, body)
        except _Failover as e:
            last_err = e
            continue
        except _Fatal as e:
            raise ProviderError(f"{p['name']}: {e}") from e

    raise ProviderError(f"All providers failed; last error: {last_err}")


class _Failover(Exception):
    """Provider returned a failover-worthy condition (429/401/timeout…)."""


class _Fatal(Exception):
    """Non-failover failure (bad request shape, unexpected response)."""


def _post(provider: dict, body: dict) -> dict:
    url = f"{provider['base_url'].rstrip('/')}/chat/completions"
    # A real User-Agent is REQUIRED: Groq's Cloudflare edge returns
    # "HTTP 403: error code 1010" (browser-signature ban) to Python's
    # default "Python-urllib/x.y" UA (found live 2026-09-24).
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider['api_key']}",
            "User-Agent": "uhi-nagpur/0.2 (Freebuff project; python-urllib)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.AI_REQUEST_TIMEOUT_S) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in FAILOVER_STATUS:
            raise _Failover(f"{provider['name']} HTTP {e.code}: {detail}") from e
        raise _Fatal(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise _Failover(f"{provider['name']} unreachable: {e}") from e

    # Shape sanity: OpenAI-compatible responses always carry choices[].message.
    if "choices" not in resp or not resp["choices"]:
        raise _Fatal(f"{provider['name']}: unexpected response shape: {str(resp)[:200]}")
    resp["_provider"] = provider["name"]  # annotation, stripped before returning
    return resp


def strip_provider_annotation(resp: dict) -> dict:
    """Remove the internal _provider marker (kept out of user-facing JSON)."""
    return {k: v for k, v in resp.items() if k != "_provider"}
