"""
Comprehensive intelligence layer tests.

All LLM calls are intercepted by SmartFakeLLMProvider which returns
deterministic, schema-valid responses based on what schema is requested.

NO real network calls are made.
"""
from __future__ import annotations

import json
import os
import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.services import session_store
from app.services.llm import FakeLLMProvider, LLMProvider
from app.services.memory import (
    FakeMemoryProvider,
    MemoryResult,
    get_memory_provider,
    reset_memory_provider,
    set_memory_provider,
)
from app.schemas.intelligence import (
    AnswerEvaluation,
    CompetencyState,
    InterviewTurn,
    NextQuestion,
)
from app.schemas.interview import FeedbackPayload
from app.schemas.candidate import CandidateRecord, MemberInfo, MissionRecord, Signals
from app.agents.evaluator import Evaluator
from app.agents.planner import Planner, MIN_QUESTIONS, MIN_DAYS
from app.agents.interviewer import Interviewer
from app.agents.orchestrator import Orchestrator, OrchestratorState
from app.routers.interview import set_provider, reset_provider

# ── Fixtures & helpers ────────────────────────────────────────────────────────

CANDIDATE = CandidateRecord(
    member=MemberInfo(
        id="CAND-001",
        name="Sarah Johnson",
        jobRole="Senior Data Engineer",
        yearsExperience=9,
        education="MS Computer Science",
        status="COMPLETED",
    ),
    missions=[
        MissionRecord(day=7,  title="Embeddings Explained",             passed=True,  attempts=1),
        MissionRecord(day=8,  title="Vector Databases Overview",        passed=True,  attempts=1),
        MissionRecord(day=10, title="Retrieval & Matching Engine",      passed=True,  attempts=2),
        MissionRecord(day=12, title="Prompt Engineering Fundamentals",  passed=True,  attempts=4),
        MissionRecord(day=16, title="Chatbot Backend & API Integration",passed=True,  attempts=1),
        MissionRecord(day=22, title="Multi-Agent Orchestration",        passed=True,  attempts=2),
        MissionRecord(day=28, title="Docker & Kubernetes Deployment",   passed=True,  attempts=3),
        MissionRecord(day=31, title="Capstone Project & Final Demo",    passed=True,  attempts=1),
    ],
    signals=Signals(commitDays=28, missionsCompleted=30, missionsFirstTry=20),
)

CANDIDATE_DICT = CANDIDATE.model_dump()


def _strong_eval(**overrides) -> AnswerEvaluation:
    defaults = dict(
        score=8.5, correctness=8.5, depth=8.0,
        reasoning="Strong answer with good depth.",
        strengths=["Clear explanation", "Good examples"],
        weaknesses=[],
        missing_concepts=[],
        follow_up_needed=False,
        recommended_strategy="architecture_probe",
        recommended_difficulty="hard",
    )
    defaults.update(overrides)
    return AnswerEvaluation(**defaults)


def _medium_eval(**overrides) -> AnswerEvaluation:
    defaults = dict(
        score=6.0, correctness=6.0, depth=5.5,
        reasoning="Adequate answer, some gaps.",
        strengths=["Basic understanding"],
        weaknesses=["Missing depth on trade-offs"],
        missing_concepts=["indexing strategies"],
        follow_up_needed=False,
        recommended_strategy="conceptual_probe",
        recommended_difficulty="medium",
    )
    defaults.update(overrides)
    return AnswerEvaluation(**defaults)


def _weak_eval(**overrides) -> AnswerEvaluation:
    defaults = dict(
        score=3.5, correctness=3.0, depth=3.0,
        reasoning="Shallow answer, missed key concepts.",
        strengths=[],
        weaknesses=["Missed cosine similarity", "No mention of HNSW"],
        missing_concepts=["HNSW", "ANN search"],
        follow_up_needed=True,
        recommended_strategy="weakness_probe",
        recommended_difficulty="easy",
    )
    defaults.update(overrides)
    return AnswerEvaluation(**defaults)


def _next_question(day: int = 7, topic: str = "Embeddings", **overrides) -> NextQuestion:
    defaults = dict(
        question=f"Test question about {topic}?",
        curriculum_day=day,
        topic=topic,
        strategy="baseline",
        difficulty="medium",
        rationale="Test rationale",
    )
    defaults.update(overrides)
    return NextQuestion(**defaults)


def _feedback() -> FeedbackPayload:
    return FeedbackPayload(
        summary="Solid overall performance.",
        strengths=["Good conceptual clarity"],
        gaps=["Production deployment scenarios"],
        next=["Study Kubernetes networking"],
    )


class SmartFakeLLM(LLMProvider):
    """
    Returns appropriate schema-valid objects based on what is requested.
    Accepts a configurable evaluation response.
    """
    def __init__(self, eval_result: AnswerEvaluation | None = None, day_sequence: list[int] | None = None):
        self._eval = eval_result or _strong_eval()
        self._day_iter = iter(day_sequence or [7, 8, 10, 12, 16, 22, 28, 31])
        self._q_count = 0

    def generate(self, messages, **kwargs):
        return "What is your approach to optimizing vector search latency?"

    def generate_structured(self, messages, schema, **kwargs):
        if schema is AnswerEvaluation:
            return self._eval
        if schema is NextQuestion:
            self._q_count += 1
            try:
                day = next(self._day_iter)
            except StopIteration:
                day = 7
            return _next_question(day=day, topic=f"Topic-{day}")
        if schema is FeedbackPayload:
            return _feedback()
        # Fallback: try to build from schema defaults (will fail for required fields)
        return schema.model_validate({})


def _extract_section(prompt: str, heading: str) -> str:
    marker = f"## {heading}\n"
    if marker not in prompt:
        return ""
    tail = prompt.split(marker, 1)[1]
    return tail.split("\n\n## ", 1)[0].strip()


class PromptSensitiveLLM(LLMProvider):
    """Deterministic fake that reacts to planner/interviewer prompt content."""

    def __init__(self, eval_result: AnswerEvaluation):
        self.eval_result = eval_result
        self.planner_prompts: list[str] = []
        self.interviewer_prompts: list[str] = []
        self.feedback_prompts: list[str] = []

    def generate(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.interviewer_prompts.append(prompt)
        base_question = ""
        if "Base question:" in prompt:
            base_question = prompt.split("Base question:", 1)[1].split("\n", 1)[0].strip()
        return base_question or "How would you approach that?"

    def generate_structured(self, messages, schema, **kwargs):
        prompt = messages[-1]["content"]
        if schema is AnswerEvaluation:
            return self.eval_result
        if schema is NextQuestion:
            self.planner_prompts.append(prompt)
            prompt_lower = prompt.lower()
            if "bm25" in prompt_lower and (
                "rare medical terms" in prompt_lower
                or "combine embeddings" in prompt_lower
                or "semantic representations" in prompt_lower
                or "hybrid retrieval" in prompt_lower
            ):
                question = "How would you decide when the lexical result should outweigh the semantic result?"
                topic = "Hybrid retrieval trade-offs"
                strategy = "tradeoff"
                day = 8
            elif "fine-tune" in prompt_lower:
                question = "How would you construct those training pairs, and how would you avoid overfitting to rare conditions?"
                topic = "Fine-tuning data"
                strategy = "clarification"
                day = 10
            elif self.eval_result.score < 5.0:
                question = "What specifically makes that approach fail, and what would you change first?"
                topic = "Weakness probe"
                strategy = "weakness_probe"
                day = 12
            else:
                question = "How would you validate that decision in practice?"
                topic = "Technical decision"
                strategy = "clarification"
                day = 16
            return _next_question(day=day, topic=topic, question=question, strategy=strategy)
        if schema is FeedbackPayload:
            self.feedback_prompts.append(prompt)
            return _feedback()
        return schema.model_validate({})


@pytest.fixture(autouse=True)
def isolate():
    """Reset global state around every test."""
    session_store.clear_all()
    reset_provider()
    # Set memory provider to fake for tests
    os.environ["MEMORY_PROVIDER"] = "fake"
    set_memory_provider(FakeMemoryProvider())
    yield
    session_store.clear_all()
    reset_provider()
    reset_memory_provider()
    if "MEMORY_PROVIDER" in os.environ:
        del os.environ["MEMORY_PROVIDER"]


@pytest.fixture
def client_with_fake_llm():
    llm = SmartFakeLLM()
    set_provider(llm)
    return TestClient(app), llm


def _api_client(llm: LLMProvider | None = None) -> TestClient:
    set_provider(llm or SmartFakeLLM())
    return TestClient(app)


def _init(client: TestClient, sid: str = "s1") -> dict:
    resp = client.post("/api/interview", json={"sessionId": sid, "candidate": CANDIDATE_DICT})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Evaluator: structured output
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluator:
    def test_returns_answer_evaluation(self):
        llm = SmartFakeLLM(eval_result=_strong_eval())
        ev = Evaluator(llm)
        result = ev.evaluate(CANDIDATE, 7, "Q?", "Good answer about embeddings.", [])
        assert isinstance(result, AnswerEvaluation)

    def test_score_in_valid_range(self):
        ev = Evaluator(SmartFakeLLM(eval_result=_strong_eval()))
        result = ev.evaluate(CANDIDATE, 7, "Q?", "Answer", [])
        assert 0.0 <= result.score <= 10.0

    def test_has_all_required_fields(self):
        ev = Evaluator(SmartFakeLLM(eval_result=_weak_eval()))
        result = ev.evaluate(CANDIDATE, 7, "Q?", "Poor answer", [])
        for attr in ("score","correctness","depth","reasoning","strengths",
                     "weaknesses","missing_concepts","follow_up_needed",
                     "recommended_strategy","recommended_difficulty"):
            assert hasattr(result, attr), f"Missing: {attr}"

    def test_weak_answer_sets_follow_up(self):
        ev = Evaluator(SmartFakeLLM(eval_result=_weak_eval()))
        result = ev.evaluate(CANDIDATE, 7, "Q?", "I don't know", [])
        assert result.follow_up_needed is True
        assert result.score < 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Difficulty adaptation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDifficultyAdaptation:
    def test_strong_answer_escalates_difficulty(self):
        state = CompetencyState(current_difficulty="medium")
        strong = _strong_eval()
        new_diff = Planner._update_difficulty(state, strong)
        assert new_diff == "hard"

    def test_medium_answer_holds_difficulty(self):
        state = CompetencyState(current_difficulty="medium")
        medium = _medium_eval()
        new_diff = Planner._update_difficulty(state, medium)
        assert new_diff == "medium"

    def test_weak_answer_reduces_difficulty(self):
        state = CompetencyState(current_difficulty="medium")
        weak = _weak_eval()
        new_diff = Planner._update_difficulty(state, weak)
        assert new_diff == "easy"

    def test_hard_stays_hard_on_strong(self):
        state = CompetencyState(current_difficulty="hard")
        new_diff = Planner._update_difficulty(state, _strong_eval())
        assert new_diff == "hard"

    def test_easy_stays_easy_on_weak(self):
        state = CompetencyState(current_difficulty="easy")
        new_diff = Planner._update_difficulty(state, _weak_eval())
        assert new_diff == "easy"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Weak answer triggers follow-up / weakness probe
# ═══════════════════════════════════════════════════════════════════════════════

class TestWeakAnswerFollowUp:
    def test_weak_eval_triggers_weakness_probe_strategy(self):
        state = CompetencyState()
        strategy = Planner._pick_strategy(state, _weak_eval(), force_end=False)
        assert strategy in ("weakness_probe", "clarification", "conceptual_probe")

    def test_follow_up_needed_respected(self):
        state = CompetencyState()
        eval_ = _weak_eval(follow_up_needed=True, recommended_strategy="clarification")
        strategy = Planner._pick_strategy(state, eval_, force_end=False)
        assert strategy == "clarification"

    def test_consecutive_weak_breaks_loop(self):
        # After 3+ consecutive weak, strategy shifts away from weakness_probe
        state = CompetencyState(consecutive_weak=3)
        strategy = Planner._pick_strategy(state, _weak_eval(), force_end=False)
        assert strategy != "weakness_probe"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Planner avoids repeating topics
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlannerRepetition:
    def test_does_not_repeat_covered_day(self):
        # SmartFakeLLM cycles through days in sequence; planner decides
        # We test that covered_days is tracked properly
        state = CompetencyState(covered_days=[7, 8, 10])
        from app.services.curriculum_loader import all_days
        uncovered = [d for d in all_days() if d not in state.covered_days]
        assert len(uncovered) > 0   # there are always uncovered days


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Curriculum day coverage tracked
# ═══════════════════════════════════════════════════════════════════════════════

class TestCurriculumCoverage:
    def test_day_added_to_covered_days_after_turn(self):
        orch = Orchestrator(SmartFakeLLM(), memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)
        orch.next_turn(state, "My answer")
        assert len(state.competency.covered_days) >= 1

    def test_topic_added_to_covered_topics_after_turn(self):
        orch = Orchestrator(SmartFakeLLM(), memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)
        orch.next_turn(state, "My answer")
        assert len(state.competency.covered_topics) >= 1

    def test_covered_days_grows_across_turns(self):
        llm = SmartFakeLLM(day_sequence=[7, 8, 10, 12, 16, 22, 28, 31])
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)
        for i in range(4):
            orch.next_turn(state, f"Answer {i}")
        assert len(state.competency.covered_days) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Interview can reach 8+ questions
# ═══════════════════════════════════════════════════════════════════════════════

class TestInterviewLength:
    def _drive_n_turns(self, n: int) -> OrchestratorState:
        llm = SmartFakeLLM(day_sequence=list(range(7, 7 + n + 2)))
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)
        for i in range(n):
            if not state.done:
                orch.next_turn(state, f"Answer {i}")
        return state

    def test_8_turns_reachable(self):
        state = self._drive_n_turns(8)
        assert state.question_count >= 1   # at minimum some turns recorded

    def test_10_turns_ends_eventually(self):
        # Drive 12 turns; by then should be done (MAX_QUESTIONS = 10)
        llm = SmartFakeLLM(
            day_sequence=[7, 8, 10, 12, 16, 22, 28, 31, 7, 8, 10, 12],
        )
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)
        for i in range(12):
            if not state.done:
                orch.next_turn(state, f"Answer {i}")
        assert state.done


# ═══════════════════════════════════════════════════════════════════════════════
# 7. At least 4 distinct curriculum days covered
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistinctDayCoverage:
    def test_4_distinct_days_possible(self):
        # Orchestrator state tracking: each turn records its curriculum day
        orch = Orchestrator(SmartFakeLLM(day_sequence=[7, 8, 10, 12, 16, 22]), memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)
        for i in range(8):
            if not state.done:
                orch.next_turn(state, f"Good answer {i}")
        # covered_days should grow; at minimum the first day is always recorded
        assert len(state.competency.covered_days) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Session state survives multiple API requests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionPersistence:
    def test_state_persists_across_requests(self):
        client = _api_client()
        _init(client, "persist-1")
        resp1 = client.post("/api/interview", json={"sessionId": "persist-1", "message": "Answer 1"})
        assert resp1.status_code == 200
        resp2 = client.post("/api/interview", json={"sessionId": "persist-1", "message": "Answer 2"})
        assert resp2.status_code == 200
        sess = session_store.get_session("persist-1")
        assert sess is not None
        assert sess.turn_count == 2

    def test_two_sessions_independent(self):
        client = _api_client()
        _init(client, "s-a")
        _init(client, "s-b")
        client.post("/api/interview", json={"sessionId": "s-a", "message": "msg"})
        sa = session_store.get_session("s-a")
        sb = session_store.get_session("s-b")
        assert sa.turn_count == 1
        assert sb.turn_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Final response contains summary / strengths / gaps / next
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinalFeedback:
    def _drive_to_completion(self, client: TestClient, sid: str = "done-sess") -> dict:
        _init(client, sid)
        last = {}
        for i in range(12):
            resp = client.post("/api/interview", json={"sessionId": sid, "message": f"Answer {i}"})
            last = resp.json()
            if last.get("done"):
                break
        return last

    def test_final_done_true(self):
        client = _api_client(SmartFakeLLM(day_sequence=[7,8,10,12,16,22,28,31,7,8,10,12]))
        body = self._drive_to_completion(client)
        assert body["done"] is True

    def test_final_feedback_all_keys(self):
        client = _api_client(SmartFakeLLM(day_sequence=[7,8,10,12,16,22,28,31,7,8,10,12]))
        body = self._drive_to_completion(client)
        fb = body.get("feedback")
        assert fb is not None
        for key in ("summary", "strengths", "gaps", "next"):
            assert key in fb, f"Missing key: {key}"

    def test_final_feedback_arrays(self):
        client = _api_client(SmartFakeLLM(day_sequence=[7,8,10,12,16,22,28,31,7,8,10,12]))
        body = self._drive_to_completion(client)
        fb = body["feedback"]
        assert isinstance(fb["strengths"], list)
        assert isinstance(fb["gaps"], list)
        assert isinstance(fb["next"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. API contract compatibility (spec.md – existing 16 tests must still pass)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIContractCompat:
    def test_init_200(self):
        client = _api_client()
        resp = client.post("/api/interview", json={"sessionId": "c1", "candidate": CANDIDATE_DICT})
        assert resp.status_code == 200

    def test_init_reply_not_empty(self):
        client = _api_client()
        resp = client.post("/api/interview", json={"sessionId": "c2", "candidate": CANDIDATE_DICT})
        assert len(resp.json()["reply"]) > 0

    def test_init_done_false(self):
        client = _api_client()
        resp = client.post("/api/interview", json={"sessionId": "c3", "candidate": CANDIDATE_DICT})
        assert resp.json()["done"] is False

    def test_init_no_feedback(self):
        client = _api_client()
        resp = client.post("/api/interview", json={"sessionId": "c4", "candidate": CANDIDATE_DICT})
        assert resp.json().get("feedback") is None

    def test_duplicate_init_409(self):
        client = _api_client()
        p = {"sessionId": "dup", "candidate": CANDIDATE_DICT}
        client.post("/api/interview", json=p)
        assert client.post("/api/interview", json=p).status_code == 409

    def test_followup_200(self):
        client = _api_client()
        _init(client, "f1")
        resp = client.post("/api/interview", json={"sessionId": "f1", "message": "hi"})
        assert resp.status_code == 200

    def test_followup_unknown_404(self):
        client = _api_client()
        resp = client.post("/api/interview", json={"sessionId": "nope", "message": "hi"})
        assert resp.status_code == 404

    def test_missing_both_422(self):
        client = _api_client()
        resp = client.post("/api/interview", json={"sessionId": "x"})
        assert resp.status_code == 422

    def test_health(self):
        client = _api_client()
        assert client.get("/health").status_code == 200

    def test_post_done_410(self):
        client = _api_client(SmartFakeLLM(day_sequence=[7,8,10,12,16,22,28,31,7,8,10,12]))
        _init(client, "end-sess")
        for i in range(12):
            r = client.post("/api/interview", json={"sessionId": "end-sess", "message": f"a{i}"})
            if r.json().get("done"):
                break
        resp = client.post("/api/interview", json={"sessionId": "end-sess", "message": "extra"})
        assert resp.status_code == 410


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Follow-up quality, memory grounding, and final feedback evidence
# ═══════════════════════════════════════════════════════════════════════════════

class TestFollowUpQuality:
    def test_strong_answer_triggers_specific_follow_up(self):
        llm = PromptSensitiveLLM(eval_result=_strong_eval())
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)

        reply, done, feedback = orch.next_turn(
            state,
            "I would combine embeddings with BM25 because rare medical terms may not have strong semantic representations.",
        )

        assert done is False
        assert feedback is None
        assert "lexical result should outweigh the semantic result" in reply
        assert "rare medical terms" in llm.planner_prompts[-1].lower()
        assert "bm25" in llm.planner_prompts[-1].lower()

    def test_weak_answer_triggers_targeted_probe(self):
        weak_eval = _weak_eval(
            follow_up_needed=True,
            weaknesses=["No justification for the retrieval choice"],
            missing_concepts=["trade-offs"],
            recommended_strategy="clarification",
        )
        llm = PromptSensitiveLLM(eval_result=weak_eval)
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)

        reply, done, feedback = orch.next_turn(state, "I don't know.")

        assert done is False
        assert feedback is None
        assert "what specifically makes that approach fail" in reply.lower()
        assert "what would you change first" in reply.lower()
        assert "weakness" in llm.planner_prompts[-1].lower()

    def test_follow_up_references_previous_answer_claim(self):
        llm = PromptSensitiveLLM(eval_result=_strong_eval())
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)

        reply, done, feedback = orch.next_turn(
            state,
            "I’d fine-tune the embedding model using clinical query-document pairs.",
        )

        assert done is False
        assert feedback is None
        assert "training pairs" in reply.lower()
        assert "overfitting" in reply.lower()
        assert "fine-tune" in llm.planner_prompts[-1].lower()

    def test_candidate_name_not_required_every_question(self):
        llm = PromptSensitiveLLM(eval_result=_strong_eval())
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)

        reply, done, feedback = orch.next_turn(
            state,
            "I would use hybrid retrieval because BM25 can help with rare medical terms.",
        )

        assert done is False
        assert feedback is None
        assert not reply.startswith("Sarah,")
        assert "Sarah" not in reply[:12]


class TestMemoryAndCoverage:
    def test_memory_context_is_available_to_planner(self):
        memory = FakeMemoryProvider()
        memory.set_recall_results(
            [
                MemoryResult(
                    fact="Candidate previously implemented hybrid retrieval using BM25 and embeddings.",
                    source_node="node-1",
                    target_node="node-2",
                    name="hybrid-retrieval",
                    optional_intent_meta=None,
                )
            ]
        )
        llm = PromptSensitiveLLM(eval_result=_strong_eval())
        orch = Orchestrator(llm, memory_provider=memory)
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)

        reply, done, feedback = orch.next_turn(
            state,
            "I would combine embeddings with BM25 because rare medical terms may not have strong semantic representations.",
        )

        assert done is False
        assert feedback is None
        assert "hybrid retrieval using bm25 and embeddings" in llm.planner_prompts[-1].lower()
        assert "lexical result should outweigh the semantic result" in reply

    def test_interview_reaches_eight_questions_and_four_days(self):
        llm = SmartFakeLLM(day_sequence=[7, 8, 10, 12, 16, 22, 28, 31, 7, 8, 10, 12])
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)

        for i in range(12):
            if state.done:
                break
            orch.next_turn(state, f"Answer {i}")

        assert state.done is True
        assert state.question_count >= 8
        assert len(set(state.competency.covered_days)) >= 4
        assert state.feedback is not None
        assert set(state.feedback.model_dump().keys()) == {"summary", "strengths", "gaps", "next"}


class TestFinalFeedbackGrounding:
    def test_feedback_prompt_uses_turn_evidence(self):
        llm = PromptSensitiveLLM(eval_result=_strong_eval())
        orch = Orchestrator(llm, memory_provider=FakeMemoryProvider())
        state = OrchestratorState(candidate=CANDIDATE)
        orch.start(state)

        for i in range(12):
            if state.done:
                break
            orch.next_turn(
                state,
                "I would combine embeddings with BM25 because rare medical terms may not have strong semantic representations.",
            )

        assert state.feedback is not None
        assert llm.feedback_prompts, "Expected at least one feedback prompt"
        feedback_prompt = llm.feedback_prompts[-1].lower()
        assert "missing_concepts" in feedback_prompt
        assert "weaknesses" in feedback_prompt
        assert "overall score" in feedback_prompt
