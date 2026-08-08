"""
LLM provider abstraction.

Usage
-----
provider = get_provider()
text   = provider.generate(messages)
parsed = provider.generate_structured(messages, MyPydanticModel)

Configuration (environment variables)
--------------------------------------
LLM_PROVIDER   : "openai" | "ollama"  (default: "openai")
LLM_BASE_URL   : override base URL    (e.g. http://localhost:11434/v1)
LLM_MODEL      : model name           (default: "gpt-4o-mini")
OPENAI_API_KEY : required for openai provider
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


# ── Abstract interface ────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Provider-independent interface consumed by all agents."""

    @abstractmethod
    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Return a plain text completion for the given message list."""

    @abstractmethod
    def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: Type[T],
        **kwargs: Any,
    ) -> T:
        """Return a Pydantic model instance parsed from the LLM JSON output."""


# ── OpenAI / Ollama adapter ───────────────────────────────────────────────────

class OpenAIAdapter(LLMProvider):
    """
    Wraps the openai Python SDK.
    Works unchanged for Ollama when LLM_BASE_URL points to the Ollama server.
    """

    def __init__(self, base_url: str | None = None, model: str = "gpt-4o-mini"):
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            ) from exc

        self._model = model
        kwargs: dict[str, Any] = {}
        if base_url:
            kwargs["base_url"] = base_url
        api_key = os.getenv("OPENAI_API_KEY", "sk-placeholder")
        self._client = OpenAI(api_key=api_key, **kwargs)

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, **kwargs
        )
        return resp.choices[0].message.content or ""

    def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: Type[T],
        **kwargs: Any,
    ) -> T:
        # Ask the model for JSON; parse with Pydantic.
        system_injection = {
            "role": "system",
            "content": (
                f"You MUST respond with a single valid JSON object "
                f"matching this schema:\n{json.dumps(schema.model_json_schema(), indent=2)}"
            ),
        }
        augmented = [system_injection] + list(messages)
        raw = self.generate(augmented, response_format={"type": "json_object"}, **kwargs)
        return schema.model_validate_json(raw)


# ── Groq adapter ──────────────────────────────────────────────────────────────

class GroqAdapter(LLMProvider):
    """
    Wraps the groq Python SDK.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        try:
            from groq import Groq  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "groq package not installed. Run: pip install groq"
            ) from exc

        self._model = model
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            # We allow instantiation to pass without key for test mocking 
            # Real usage will fail during the request, caught by the router
            api_key = "dummy-key"
        self._client = Groq(api_key=api_key)

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, **kwargs
        )
        return resp.choices[0].message.content or ""

    def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: Type[T],
        **kwargs: Any,
    ) -> T:
        system_injection = {
            "role": "system",
            "content": (
                f"You MUST respond with a single valid JSON object "
                f"matching this schema:\n{json.dumps(schema.model_json_schema(), indent=2)}"
            ),
        }
        augmented = [system_injection] + list(messages)
        # Groq SDK also supports response_format={"type": "json_object"}
        raw = self.generate(augmented, response_format={"type": "json_object"}, **kwargs)
        return schema.model_validate_json(raw)


# ── Factory ───────────────────────────────────────────────────────────────────

def get_provider() -> LLMProvider:
    """
    Build the configured LLM provider from environment variables.
    Callers that need deterministic behaviour in tests should inject
    a FakeLLMProvider directly instead of calling this.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    
    if provider == "groq":
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        return GroqAdapter(model=model)

    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    base_url = os.getenv("LLM_BASE_URL")

    if provider in ("openai", "ollama"):
        return OpenAIAdapter(base_url=base_url, model=model)

    raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Supported: groq, openai, ollama")


# ── Test/fake provider ────────────────────────────────────────────────────────

class FakeLLMProvider(LLMProvider):
    """
    Deterministic provider for unit tests.
    Callers may pre-set canned responses via `queue` or override
    generate/generate_structured entirely.
    """

    def __init__(
        self,
        text_response: str = "Mock answer",
        structured_override: BaseModel | None = None,
    ):
        self._text = text_response
        self._structured = structured_override

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:  # noqa: ARG002
        return self._text

    def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: Type[T],
        **kwargs: Any,  # noqa: ARG002
    ) -> T:
        if self._structured is not None and isinstance(self._structured, schema):
            return self._structured  # type: ignore[return-value]
        # Build a minimal valid instance from defaults
        return schema.model_validate({})
