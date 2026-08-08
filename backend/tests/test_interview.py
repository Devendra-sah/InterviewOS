"""
Tests for POST /api/interview – covers the exact contract from technical-spec.md.

Run:  cd backend && pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import session_store

client = TestClient(app)

# Minimal candidate payload (matches candidates.json schema)
CANDIDATE = {
    "member": {
        "id": "CAND-001",
        "name": "Sarah Johnson",
        "jobRole": "Senior Data Engineer",
        "yearsExperience": 9,
        "education": "MS Computer Science",
        "status": "COMPLETED",
    },
    "missions": [
        {"day": 7, "title": "Embeddings Explained", "passed": True, "attempts": 1}
    ],
    "signals": {"commitDays": 28, "missionsCompleted": 30, "missionsFirstTry": 20},
}


@pytest.fixture(autouse=True)
def clear_sessions():
    """Wipe sessions before each test so tests are isolated."""
    session_store.clear_all()
    yield
    session_store.clear_all()


# ── 1. Init turn ──────────────────────────────────────────────────────────────

class TestInitTurn:
    def test_init_returns_200(self):
        resp = client.post("/api/interview", json={"sessionId": "s1", "candidate": CANDIDATE})
        assert resp.status_code == 200

    def test_init_response_shape(self):
        resp = client.post("/api/interview", json={"sessionId": "s1", "candidate": CANDIDATE})
        body = resp.json()
        assert "reply" in body
        assert "done" in body
        assert body["done"] is False

    def test_init_reply_is_not_empty(self):
        resp = client.post("/api/interview", json={"sessionId": "s1", "candidate": CANDIDATE})
        assert len(resp.json()["reply"]) > 0

    def test_init_no_feedback_field(self):
        resp = client.post("/api/interview", json={"sessionId": "s1", "candidate": CANDIDATE})
        body = resp.json()
        # feedback must be absent or null when done=False
        assert body.get("feedback") is None

    def test_duplicate_init_returns_409(self):
        payload = {"sessionId": "dup", "candidate": CANDIDATE}
        client.post("/api/interview", json=payload)
        resp = client.post("/api/interview", json=payload)
        assert resp.status_code == 409


# ── 2. Follow-up turn ────────────────────────────────────────────────────────

class TestFollowUpTurn:
    def _init(self, sid="sess"):
        client.post("/api/interview", json={"sessionId": sid, "candidate": CANDIDATE})

    def test_followup_returns_200(self):
        self._init()
        resp = client.post("/api/interview", json={"sessionId": "sess", "message": "Hello"})
        assert resp.status_code == 200

    def test_followup_response_shape(self):
        self._init()
        resp = client.post("/api/interview", json={"sessionId": "sess", "message": "Hello"})
        body = resp.json()
        assert "reply" in body
        assert "done" in body

    def test_followup_unknown_session_returns_404(self):
        resp = client.post("/api/interview", json={"sessionId": "no-such", "message": "Hi"})
        assert resp.status_code == 404


# ── 3. End / feedback ────────────────────────────────────────────────────────

class TestEndInterview:
    def _drive_to_end(self, sid="end-sess"):
        client.post("/api/interview", json={"sessionId": sid, "candidate": CANDIDATE})
        for i in range(5):   # _MAX_TURNS = 5
            resp = client.post("/api/interview", json={"sessionId": sid, "message": f"msg {i}"})
        return resp

    def test_final_done_is_true(self):
        resp = self._drive_to_end()
        assert resp.json()["done"] is True

    def test_final_feedback_present(self):
        resp = self._drive_to_end()
        body = resp.json()
        assert body["feedback"] is not None

    def test_feedback_has_required_fields(self):
        resp = self._drive_to_end()
        fb = resp.json()["feedback"]
        for field in ("summary", "strengths", "gaps", "next"):
            assert field in fb, f"Missing field: {field}"

    def test_feedback_arrays_are_lists(self):
        resp = self._drive_to_end()
        fb = resp.json()["feedback"]
        assert isinstance(fb["strengths"], list)
        assert isinstance(fb["gaps"], list)
        assert isinstance(fb["next"], list)

    def test_post_done_session_returns_410(self):
        self._drive_to_end(sid="closed")
        resp = client.post("/api/interview", json={"sessionId": "closed", "message": "extra"})
        assert resp.status_code == 410


# ── 4. Schema validation ──────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_missing_both_fields_returns_422(self):
        resp = client.post("/api/interview", json={"sessionId": "x"})
        assert resp.status_code == 422

    def test_missing_session_id_returns_422(self):
        resp = client.post("/api/interview", json={"candidate": CANDIDATE})
        assert resp.status_code == 422

    def test_health_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
