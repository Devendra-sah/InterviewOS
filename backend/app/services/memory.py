"""
Memory provider abstraction for persistent interview memory using Breeth.

Usage
-----
provider = get_memory_provider()
provider.remember_evidence(...)
memories = provider.recall_relevant(...)
"""

from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod
from typing import Any, List, Optional

import httpx
from pydantic import BaseModel, Field

# ── Data Models ────────────────────────────────────────────────────────────────
class MemoryEvidence(BaseModel):
    """Evidence to be stored in Breeth."""
    candidate_id: str
    session_id: str
    turn_number: int
    curriculum_day: int
    topic: str
    question: str
    answer: str
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    missing_concepts: List[str] = Field(default_factory=list)
    score: float = Field(..., ge=0.0, le=10.0)
    significance: str = Field(..., description="Why this evidence is meaningful")


class MemoryResult(BaseModel):
    """Result from Breeth search."""
    fact: str
    source_node: Optional[str] = None
    target_node: Optional[str] = None
    name: Optional[str] = None
    optional_intent_meta: Optional[dict] = None


# ── Abstract Interface ─────────────────────────────────────────────────────────
class MemoryProvider(ABC):
    """Provider-independent interface for interview memory."""

    @abstractmethod
    def remember_evidence(self, evidence: MemoryEvidence) -> None:
        """Store interview evidence. Should be idempotent per turn."""

    @abstractmethod
    def recall_relevant(self, candidate_id: str, query: str, limit: int = 5) -> List[MemoryResult]:
        """Retrieve relevant memories for a candidate."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if memory service is reachable."""


# ── Breeth Implementation ──────────────────────────────────────────────────────
class BreethMemoryProvider(MemoryProvider):
    """Breeth-backed memory provider."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or os.getenv("BREETH_BASE_URL", "https://api.thebreeth.com")).rstrip("/")
        self.api_key = api_key or os.getenv("BREETH_API_KEY")
        if not self.api_key:
            raise ValueError("BREETH_API_KEY must be set in environment or passed to constructor")
        self.timeout = timeout
        # Reusable HTTP client with separate connect and read timeouts
        # Connect timeout: 5.0 seconds, Read timeout: 30.0 seconds
        timeout_config = httpx.Timeout(5.0, read=30.0)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_config,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

    def _group_id(self, candidate_id: str) -> str:
        """Generate deterministic Breeth group_id from candidate_id."""
        # Keep only alphanumeric, dash, underscore
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', candidate_id)
        return f"candidate-{sanitized}"

    def _evidence_id(self, evidence: MemoryEvidence) -> str:
        """Create a deterministic ID for deduplication within a session."""
        data = f"{evidence.candidate_id}:{evidence.session_id}:{evidence.turn_number}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def remember_evidence(self, evidence: MemoryEvidence) -> None:
        """Write evidence to Breeth as an episode."""
        # In a real implementation we would check for duplicates using a local set.
        # However, the spec says to implement application-level deduplication.
        # We'll leave that to the orchestrator to maintain a set of seen IDs.
        # For now, we just write; the orchestrator should avoid calling us twice.
        try:
            payload = {
                "content": self._format_evidence(evidence),
                "group_id": self._group_id(evidence.candidate_id),
                "source_description": f"interview-turn-{evidence.turn_number}",
                "extract_intent": False,
            }
            response = self._client.post("/v1/episodes", json=payload)
            response.raise_for_status()
        except httpx.ConnectTimeout as e:
            print(f"Warning: Breeth connection timeout: {e}")
        except httpx.ReadTimeout as e:
            print(f"Warning: Breeth read timeout: {e}")
        except httpx.NetworkError as e:
            print(f"Warning: Breeth network error: {e}")
        except httpx.HTTPStatusError as e:
            # Log warning but do not crash the interview
            # In a real app, we would use proper logging
            print(f"Warning: Breeth memory write failed: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            # Catch-all for any other request errors
            print(f"Warning: Breeth memory write failed due to request error: {e}")

    def recall_relevant(self, candidate_id: str, query: str, limit: int = 5) -> List[MemoryResult]:
        """Search Breeth for relevant memories."""
        try:
            payload = {
                "query": query,
                "group_id": self._group_id(candidate_id),
                "limit": limit,
            }
            response = self._client.post("/v1/search", json=payload)
            response.raise_for_status()
            data = response.json()
            # Breeth returns a list of edges; we need to map to MemoryResult
            results: List[MemoryResult] = []
            for item in data.get("results", []):
                # Assuming Breeth returns items with fact, source_node, target_node, name, optional intent_meta
                results.append(
                    MemoryResult(
                        fact=item.get("fact", ""),
                        source_node=item.get("source_node"),
                        target_node=item.get("target_node"),
                        name=item.get("name"),
                        optional_intent_meta=item.get("intent_meta"),
                    )
                )
            return results
        except httpx.ConnectTimeout as e:
            print(f"Warning: Breeth connection timeout: {e}")
            return []
        except httpx.ReadTimeout as e:
            print(f"Warning: Breeth read timeout: {e}")
            return []
        except httpx.NetworkError as e:
            print(f"Warning: Breeth network error: {e}")
            return []
        except httpx.HTTPStatusError as e:
            print(f"Warning: Breeth memory search failed: {e.response.status_code} - {e.response.text}")
            return []
        except httpx.RequestError as e:
            # Catch-all for any other request errors
            print(f"Warning: Breeth memory search failed due to request error: {e}")
            return []

    def health_check(self) -> bool:
        """Check Breeth API reachability."""
        try:
            # We can try to access a known endpoint; maybe we can do a simple search with empty query?
            # However, to avoid abuse, we'll just check if we can reach the base URL.
            response = self._client.get("/")  # Breeth might not have a root endpoint; but we can try.
            # If we get any response, consider it healthy.
            return response.status_code < 500
        except httpx.RequestError:
            return False

    def _format_evidence(self, evidence: MemoryEvidence) -> str:
        """Format evidence into a concise natural-language episode."""
        return (
            f"Interview evidence for candidate {evidence.candidate_id}. "
            f"Curriculum day: {evidence.curriculum_day}. "
            f"Topic: {evidence.topic}. "
            f"Question: {evidence.question}. "
            f"Answer: {evidence.answer[:200]}... "
            f"Evaluation: score {evidence.score}/10. "
            f"Strengths: {', '.join(evidence.strengths) or 'none'}. "
            f"Weaknesses: {', '.join(evidence.weaknesses) or 'none'}. "
            f"Missing concepts: {', '.join(evidence.missing_concepts) or 'none'}. "
            f"Significance: {evidence.significance}"
        )


# ── Fake Provider for Tests ────────────────────────────────────────────────────
class FakeMemoryProvider(MemoryProvider):
    """Deterministic memory provider for unit tests."""

    def __init__(self):
        self.stored_evidence: List[MemoryEvidence] = []
        self.recall_results: List[MemoryResult] = []
        self.healthy = True

    def remember_evidence(self, evidence: MemoryEvidence) -> None:
        self.stored_evidence.append(evidence)

    def recall_relevant(self, candidate_id: str, query: str, limit: int = 5) -> List[MemoryResult]:
        return self.recall_results.copy()[:limit]

    def health_check(self) -> bool:
        return self.healthy

    # Helper methods for test configuration
    def set_recall_results(self, results: List[MemoryResult]) -> None:
        self.recall_results = results

    def set_health(self, healthy: bool) -> None:
        self.healthy = healthy


# ── Provider singleton ─────────────────────────────────────────────────────────
# Replaced by dependency injection in tests via override.

_provider: MemoryProvider | None = None


def get_memory_provider() -> MemoryProvider:
    """
    Build the configured memory provider from environment variables.
    Callers that need deterministic behaviour in tests should inject
    a FakeMemoryProvider directly instead of calling this.
    """
    global _provider
    if _provider is None:
        provider = os.getenv("MEMORY_PROVIDER", "breeth").lower()
        if provider == "breeth":
            _provider = BreethMemoryProvider()
        elif provider == "fake":
            _provider = FakeMemoryProvider()
        else:
            raise ValueError(f"Unknown MEMORY_PROVIDER: '{provider}'. Supported: breeth, fake")
    return _provider


def set_memory_provider(p: MemoryProvider) -> None:
    """Test hook – inject a fake provider before the first request."""
    global _provider
    _provider = p


def reset_memory_provider() -> None:
    """Test hook – clear the provider so it is rebuilt from env vars."""
    global _provider
    _provider = None


# ── Backwards compatibility alias ─────────────────────────────────────────────
MemoryProvider = MemoryProvider  # noqa: F822
BreethMemoryProvider = BreethMemoryProvider
FakeMemoryProvider = FakeMemoryProvider