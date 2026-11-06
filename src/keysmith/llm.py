"""Vultr Serverless Inference client.

The *only* place Keysmith talks to a model. Every agent LLM call (the memory
interview, the hint-profile compiler step, the injection test) goes through here,
so the claim "every model call uses Vultr Inference" is a single, auditable
module pointed at ``https://api.vultrinference.com/v1``.

Dependency-free on purpose (stdlib ``urllib``): the control VM should not need a
heavy SDK, and the spike (``scripts/s1_live.py``) proved this exact shape works.
The API is OpenAI-compatible (``POST /v1/chat/completions``).

Notes carried over from the S1 spike (docs/spikes/inference.md):
* The default models are *reasoning* models — ``max_tokens`` must leave room for
  reasoning tokens or ``content`` comes back empty. 4000 is the proven budget.
* ``GET /v1/models`` is public (200 without auth), so it never proves the key;
  only an authenticated ``POST`` does.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

BASE_URL = "https://api.vultrinference.com/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash-1017"
FALLBACK_MODEL = "glm-5.3-flash"
DEFAULT_MAX_TOKENS = 4000
ENV_KEY = "VULTR_INFERENCE_KEY"


class LLMError(RuntimeError):
    """A model call failed (network, auth, empty content, or bad status)."""


@dataclass
class LLMResult:
    content: str
    model: str
    latency_ms: int
    attempts: List[str] = field(default_factory=list)  # models tried, in order

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "attempts": list(self.attempts),
        }


class VultrInference:
    """Thin OpenAI-compatible chat client for Vultr Serverless Inference.

    Tries ``model`` first, then ``fallback`` on failure or empty content, so a
    single flaky call does not sink a job. No wallet data ever passes through
    here: callers send only the user's stated memories (hint text).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: str = DEFAULT_MODEL,
        fallback: Optional[str] = FALLBACK_MODEL,
        base_url: str = BASE_URL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = 180.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(ENV_KEY, "")
        self.model = model
        self.fallback = fallback
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        """True when an API key is present. The app degrades honestly without
        one (the profile step reports it is unavailable) rather than faking."""
        return bool(self.api_key)

    # --- public API ----------------------------------------------------------

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """One chat turn. Returns the assistant content and which model answered.

        Raises ``LLMError`` if no configured model returns non-empty content.
        """
        if not self.configured:
            raise LLMError(
                f"no Vultr Inference key configured (set {ENV_KEY}); "
                "the interview cannot run without it"
            )
        models = [self.model] + ([self.fallback] if self.fallback else [])
        attempts: List[str] = []
        last_err: Optional[str] = None
        for model in models:
            attempts.append(model)
            try:
                content, latency_ms = self._one_call(
                    model, system, user, temperature,
                    max_tokens if max_tokens is not None else self.max_tokens,
                )
            except LLMError as exc:
                last_err = str(exc)
                continue
            if content.strip():
                return LLMResult(content=content, model=model,
                                 latency_ms=latency_ms, attempts=attempts)
            last_err = f"{model} returned empty content"
        raise LLMError(last_err or "all models failed")

    def list_models(self) -> List[str]:
        """Model ids from the public ``/v1/models`` list (no auth needed)."""
        req = urllib.request.Request(f"{self.base_url}/models", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise LLMError(f"could not list models: {exc}") from exc
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    # --- internals -----------------------------------------------------------

    def _one_call(
        self, model: str, system: str, user: str,
        temperature: float, max_tokens: int,
    ) -> tuple[str, int]:
        body = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            detail = _safe_read(exc)
            raise LLMError(f"{model} HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise LLMError(f"{model} network error: {exc.reason}") from exc
        except (ConnectionError, TimeoutError, OSError) as exc:  # pragma: no cover - network
            # e.g. ConnectionResetError mid-read; treat as a failed attempt so the
            # caller can fall back to the other model instead of crashing.
            raise LLMError(f"{model} connection error: {exc}") from exc
        latency_ms = int((time.time() - start) * 1000)
        try:
            content = payload["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{model} returned an unexpected response shape") from exc
        return content, latency_ms


def _safe_read(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # pragma: no cover - defensive
        return "(no body)"
    try:
        data = json.loads(raw)
    except ValueError:
        return raw[:300]
    # Vultr/OpenAI-style error bodies.
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str):
            return err
        if data.get("message"):
            return str(data["message"])
    return raw[:300]
