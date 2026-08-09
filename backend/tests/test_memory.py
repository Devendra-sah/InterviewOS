"""
Tests for memory provider functionality.
"""
from __future__ import annotations

import os

from app.services.memory import (
    MemoryEvidence,
    MemoryProvider,
    MemoryResult,
    BreethMemoryProvider,
    FakeMemoryProvider,
    get_memory_provider,
    set_memory_provider,
    reset_memory_provider,
)


def test_memory_provider_interface():
    """Test that MemoryProvider is an abstract base class."""
    # Cannot instantiate abstract class directly
    try:
        MemoryProvider()  # type: ignore
        assert False, "Should not be able to instantiate abstract base class"
    except TypeError:
        pass  # Expected


def test_fake_memory_provider():
    """Test FakeMemoryProvider basic functionality."""
    provider = FakeMemoryProvider()

    # Test initial state
    assert provider.health_check() == True

    # Test remember_evidence
    evidence = MemoryEvidence(
        candidate_id="CAND-001",
        session_id="sess-001",
        turn_number=1,
        curriculum_day=7,
        topic="Embeddings",
        question="What are embeddings?",
        answer="Embeddings are vector representations of text.",
        strengths=["clear explanation"],
        weaknesses=[],
        missing_concepts=["positional encoding"],
        score=8.0,
        significance="good understanding"
    )

    provider.remember_evidence(evidence)
    # Note: We can't directly access stored_evidence from outside due to encapsulation
    # but we can test through behavior if needed

    # Test recall_relevant with empty results
    results = provider.recall_relevant("CAND-001", "test query")
    assert results == []

    # Test setting recall results
    mock_results = [
        MemoryResult(
            fact="Test fact",
            source_node="node1",
            target_node="node2",
            name="test",
            optional_intent_meta=None
        )
    ]
    provider.set_recall_results(mock_results)
    results = provider.recall_relevant("CAND-001", "test query")
    assert len(results) == 1
    assert results[0].fact == "Test fact"

    # Test health check
    provider.set_health(False)
    assert provider.health_check() == False
    provider.set_health(True)
    assert provider.health_check() == True


def test_memory_provider_singleton():
    """Test that get_memory_provider returns a singleton."""
    reset_memory_provider()
    os.environ["MEMORY_PROVIDER"] = "fake"

    provider1 = get_memory_provider()
    provider2 = get_memory_provider()

    # Should be the same instance
    assert provider1 is provider2

    # Test setting a custom provider
    fake_provider = FakeMemoryProvider()
    set_memory_provider(fake_provider)

    provider3 = get_memory_provider()
    assert provider3 is fake_provider

    reset_memory_provider()
    if "MEMORY_PROVIDER" in os.environ:
        del os.environ["MEMORY_PROVIDER"]


def test_breeth_memory_provider_init():
    """Test BreethMemoryProvider initialization."""
    # Test with explicit parameters
    provider = BreethMemoryProvider(
        base_url="https://test.breeth.com",
        api_key="test-key",
        timeout=5.0
    )

    assert provider.base_url == "https://test.breeth.com"
    assert provider.api_key == "test-key"
    assert provider.timeout == 5.0

    # Test group_id generation
    assert provider._group_id("CAND-001") == "candidate-CAND-001"
    assert provider._group_id("CAND/ABC") == "candidate-CANDABC"  # Special chars removed
    assert provider._group_id("user@example.com") == "candidate-userexamplecom"


def test_breeth_memory_provider_evidence_id():
    """Test evidence ID generation for deduplication."""
    provider = BreethMemoryProvider(api_key="test")

    evidence = MemoryEvidence(
        candidate_id="CAND-001",
        session_id="sess-001",
        turn_number=1,
        curriculum_day=7,
        topic="Test",
        question="Test question",
        answer="Test answer",
        score=5.0,
        significance="test"
    )

    id1 = provider._evidence_id(evidence)
    id2 = provider._evidence_id(evidence)

    # Should be deterministic
    assert id1 == id2
    assert len(id1) == 16  # SHA256 truncated to 16 chars


def test_memory_evidence_model():
    """Test MemoryEvidence model validation."""
    evidence = MemoryEvidence(
        candidate_id="CAND-001",
        session_id="sess-001",
        turn_number=1,
        curriculum_day=7,
        topic="Embeddings",
        question="What are embeddings?",
        answer="Embeddings are vector representations.",
        strengths=["clear"],
        weaknesses=["vague"],
        missing_concepts=["positional"],
        score=7.5,
        significance="decent understanding"
    )

    assert evidence.candidate_id == "CAND-001"
    assert evidence.score == 7.5
    assert len(evidence.strengths) == 1
    assert evidence.strengths[0] == "clear"


def test_memory_result_model():
    """Test MemoryResult model."""
    result = MemoryResult(
        fact="Test fact",
        source_node="src",
        target_node="tgt",
        name="test-result",
        optional_intent_meta={"key": "value"}
    )

    assert result.fact == "Test fact"
    assert result.source_node == "src"
    assert result.target_node == "tgt"
    assert result.name == "test-result"
    assert result.optional_intent_meta == {"key": "value"}