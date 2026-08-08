"""
Tests for LLM providers (Groq and missing API key behaviors).
"""
import os
import pytest
from unittest.mock import patch, MagicMock

from app.services.llm import get_provider, GroqAdapter, OpenAIAdapter

from app.routers.interview import set_provider, reset_provider

def test_groq_adapter_initialization():
    # Test GroqAdapter initialization without requiring real network
    with patch.dict(os.environ, {"GROQ_API_KEY": "fake-key"}):
        adapter = GroqAdapter(model="llama-test-model")
        assert adapter._model == "llama-test-model"
        assert adapter._client is not None

def test_groq_missing_api_key():
    # Test that GroqAdapter can instantiate even if API key is missing
    # but the SDK might fail if trying to use it. Our code allows instantiation
    # when key is None for test mock purposes.
    with patch.dict(os.environ, {}):
        if "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]
            
        adapter = GroqAdapter(model="llama-test-model")
        assert adapter._model == "llama-test-model"

def test_get_provider_groq_default():
    # Ensure get_provider returns Groq by default
    with patch.dict(os.environ, {"GROQ_API_KEY": "fake-key"}):
        provider = get_provider()
        assert isinstance(provider, GroqAdapter)
        assert provider._model == "llama-3.3-70b-versatile"

def test_get_provider_groq_custom_model():
    # Ensure custom model is respected
    with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_MODEL": "custom-model", "GROQ_API_KEY": "fake-key"}):
        provider = get_provider()
        assert isinstance(provider, GroqAdapter)
        assert provider._model == "custom-model"

def test_get_provider_openai():
    # Ensure we can still fall back to openai
    with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "fake-key"}):
        with patch("app.services.llm.OpenAIAdapter") as mock_openai:
            provider = get_provider()
            assert provider == mock_openai.return_value

def test_get_provider_unknown():
    # Ensure ValueError on unknown provider
    with patch.dict(os.environ, {"LLM_PROVIDER": "unknown"}):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER: 'unknown'"):
            get_provider()

def test_interview_api_handles_provider_errors():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import session_store
    
    client = TestClient(app)
    session_store.clear_all()
    
    CANDIDATE = {
        "member": {
            "id": "CAND-001",
            "name": "Sarah Johnson",
            "jobRole": "Senior Data Engineer",
            "yearsExperience": 9,
            "education": "MS Computer Science",
            "status": "COMPLETED",
        },
        "missions": [],
        "signals": {"commitDays": 28, "missionsCompleted": 30, "missionsFirstTry": 20},
    }

    class ErrorLLMProvider:
        def generate(self, *args, **kwargs):
            raise Exception("API failure")
            
        def generate_structured(self, *args, **kwargs):
            raise Exception("API failure")

    set_provider(ErrorLLMProvider())
    
    # Init turn should return 500
    resp = client.post("/api/interview", json={"sessionId": "err1", "candidate": CANDIDATE})
    assert resp.status_code == 500
    assert "An error occurred communicating with the AI provider." in resp.text
    
    reset_provider()
    session_store.clear_all()
