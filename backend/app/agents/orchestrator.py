"""
Interview Orchestrator
======================

Coordinates the full interview loop:

    candidate
        ↓
    planner (decide next question)
        ↓
    interviewer (generate polished question)
        ↓
    [candidate answers via API]
        ↓
    evaluator (score the answer)
        ↓
    state update (difficulty, coverage, strengths/weaknesses)
        ↓
    planner (decide again)

The orchestrator owns all mutable interview state via OrchestratorState
and exposes two operations:

    start(candidate)   → str   (opening question)
    next_turn(answer)  → (str, done, feedback | None)

LLM providers are injected for testability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.agents.evaluator import Evaluator
from app.agents.interviewer import Interviewer
from app.agents.planner import Planner, MIN_QUESTIONS, MIN_DAYS
from app.schemas.candidate import CandidateRecord
from app.schemas.intelligence import (
    AnswerEvaluation,
    CompetencyState,
    InterviewTurn,
    NextQuestion,
)
from app.schemas.interview import FeedbackPayload
from app.services.memory import MemoryProvider, MemoryEvidence

if TYPE_CHECKING:
    from app.services.llm import LLMProvider

_FEEDBACK_SYSTEM = """\
You are a professional interview coach. Write a structured post-interview
report from the data below.

Return ONLY a JSON object with:
- summary    : string (2-4 sentences)
- strengths  : list[string] (concise, actionable, ≤5 items)
- gaps       : list[string] (concise, actionable, ≤5 items)
- next       : list[string] (learning recommendations, ≤4 items)
"""


# ── Orchestrator state ────────────────────────────────────────────────────────

@dataclass
class OrchestratorState:
    candidate: CandidateRecord
    competency: CompetencyState = field(default_factory=CompetencyState)
    turns: list[InterviewTurn] = field(default_factory=list)
    pending_question: NextQuestion | None = None   # set by planner, shown to candidate
    done: bool = False
    _memory_written_turns: set[int] = field(default_factory=set)
    feedback: FeedbackPayload | None = None

    @property
    def question_count(self) -> int:
        return len(self.turns)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Stateless worker: all state lives in OrchestratorState.
    Agents and memory providers are injected via constructor for testability.
    """

    def __init__(
        self,
        llm: "LLMProvider",
        memory_provider: MemoryProvider | None = None,
    ) -> None:
        self._evaluator = Evaluator(llm)
        self._planner = Planner(llm)
        self._interviewer = Interviewer(llm)
        self._llm = llm
        self._memory_provider = memory_provider


    def _get_memory_provider(self) -> MemoryProvider:
        """Get memory provider, initializing from environment if needed."""
        if self._memory_provider is None:
            from app.services.memory import get_memory_provider
            self._memory_provider = get_memory_provider()
        return self._memory_provider
    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, state: OrchestratorState) -> str:
        """
        Called once when the session is created.
        Plans and generates the first question.
        """
        # Recall memories for the candidate based on profile (no interview history yet)
        memories = None
        if self._memory_provider is not None:
            try:
                # Form a query from the candidate's profile
                candidate = state.candidate
                query = f"{candidate.member.jobRole}: new interview"
                memories = self._memory_provider.recall_relevant(
                    candidate.member.id, query, limit=5
                )
            except Exception as e:
                # Log warning but do not crash the interview
                print(f"Warning: Failed to recall memories in start: {e}")
                memories = []
        else:
            # Try to get the provider from environment
            try:
                provider = self._get_memory_provider()
                candidate = state.candidate
                query = f"{candidate.member.jobRole}: new interview"
                memories = provider.recall_relevant(
                    candidate.member.id, query, limit=5
                )
            except Exception as e:
                print(f"Warning: Failed to recall memories in start: {e}")
                memories = []

        decision = self._planner.decide(
            candidate=state.candidate,
            state=state.competency,
            history=[],
            last_eval=None,
            question_number=0,
            memories=memories,
        )
        state.pending_question = decision.next_question
        question_text = self._interviewer.generate_question(
            decision.next_question, state.candidate, []
        )
        return question_text

    def next_turn(
        self, state: OrchestratorState, answer: str
    ) -> tuple[str, bool, FeedbackPayload | None]:
        """
        Process a candidate answer.

        Returns (reply, done, feedback_or_None).
        """
        if state.done:
            return ("Interview already completed.", True, state.feedback)

        pq = state.pending_question
        if pq is None:
            # Defensive: shouldn't happen in normal flow
            return ("Please wait for the next question.", False, None)

        # 1. Evaluate the answer
        eval_result = self._evaluator.evaluate(
            candidate=state.candidate,
            curriculum_day=pq.curriculum_day,
            question=pq.question,
            answer=answer,
            history=state.turns,
        )

        # 2. Record turn
        turn = InterviewTurn(
            turn_number=state.question_count + 1,
            curriculum_day=pq.curriculum_day,
            topic=pq.topic,
            strategy=pq.strategy,
            difficulty=pq.difficulty,
            question=pq.question,
            answer=answer,
            evaluation=eval_result,
        )
        state.turns.append(turn)

        # 3. Update competency state
        self._update_competency(state.competency, turn, eval_result)

        # 4. Extract and remember evidence if meaningful
        if self._is_meaningful_evidence(eval_result, answer):
            evidence = self._create_evidence(state, turn, eval_result)
            self._remember_evidence(state, evidence, turn.turn_number)

        # 5. Recall relevant memories for planning the next question
        memories = None
        try:
            provider = self._get_memory_provider()
            candidate = state.candidate
            # Form a query based on the current competency state (after update)
            strengths_str = ", ".join(state.competency.strengths[:2]) if state.competency.strengths else "none"
            weaknesses_str = ", ".join(state.competency.weaknesses[:2]) if state.competency.weaknesses else "none"
            query = f"{candidate.member.jobRole}: strengths {strengths_str}; weaknesses {weaknesses_str}"
            memories = provider.recall_relevant(
                candidate.member.id, query, limit=5
            )
        except Exception as e:
            # Log warning but do not crash the interview
            print(f"Warning: Failed to recall memories: {e}")
            memories = []

        # 6. Decide what comes next
        decision = self._planner.decide(
            candidate=state.candidate,
            state=state.competency,
            history=state.turns,
            last_eval=eval_result,
            question_number=state.question_count,
            memories=memories,
        )

        # 7. If interview complete, build feedback
        if decision.should_end:
            state.done = True
            state.feedback = self._build_feedback(state)
            state.pending_question = None
            return ("Interview completed.", True, state.feedback)

        # 8. Generate next question
        state.pending_question = decision.next_question
        next_q = self._interviewer.generate_question(
            decision.next_question, state.candidate, state.turns
        )
        return (next_q, False, None)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _update_competency(
        c: CompetencyState,
        turn: InterviewTurn,
        eval_: AnswerEvaluation,
    ) -> None:
        # Rolling average of score
        n = 1  # weight: this evaluation counts once
        c.overall_score = (c.overall_score * (turn.turn_number - 1) + eval_.score) / turn.turn_number

        # Track coverage
        if turn.curriculum_day not in c.covered_days:
            c.covered_days.append(turn.curriculum_day)
        if turn.topic not in c.covered_topics:
            c.covered_topics.append(turn.topic)

        # Accumulate strengths / weaknesses (deduplicated)
        for s in eval_.strengths:
            if s not in c.strengths:
                c.strengths.append(s)
        for w in eval_.weaknesses:
            if w not in c.weaknesses:
                c.weaknesses.append(w)

        # Difficulty
        c.current_difficulty = eval_.recommended_difficulty
        c.current_strategy = turn.strategy

        # Streak counters
        if eval_.score >= 7.0:
            c.consecutive_strong += 1
            c.consecutive_weak = 0
        elif eval_.score < 5.0:
            c.consecutive_weak += 1
            c.consecutive_strong = 0
        else:
            c.consecutive_strong = 0
            c.consecutive_weak = 0

    def _is_meaningful_evidence(self, eval_result: AnswerEvaluation, answer: str) -> bool:
        """
        Determine if an answer produces meaningful evidence for memory.
        Do not store trivial answers unless the evaluation indicates it's evidence of a gap.
        """
        # Don't store very short answers unless they reveal a weakness
        if len(answer.strip()) < 3:
            # Only store if it's a weakness (score < 5) or indicates lack of knowledge
            return eval_result.score < 5.0 or "don't know" in answer.lower() or "unsure" in answer.lower()

        # Store if there are weaknesses or missing concepts
        if eval_result.weaknesses or eval_result.missing_concepts:
            return True

        # Store if score is low (indicates struggle)
        if eval_result.score < 5.0:
            return True

        # Store if evaluator recommends follow-up (indicates something to explore)
        if eval_result.follow_up_needed:
            return True

        # Otherwise, for high scores with no weaknesses, we might still store as strength evidence
        # but let's be selective - only store if there are notable strengths
        if eval_result.score >= 8.0 and eval_result.strengths:
            return True

        return False

    def _create_evidence(
        self,
        state: OrchestratorState,
        turn: InterviewTurn,
        eval_result: AnswerEvaluation,
    ) -> MemoryEvidence:
        """Create a MemoryEvidence object from current turn and evaluation."""
        # Determine significance based on evaluation
        significance_parts = []
        if eval_result.score >= 8.0:
            significance_parts.append("strong understanding demonstrated")
        elif eval_result.score >= 6.0:
            significance_parts.append("moderate understanding")
        else:
            significance_parts.append("knowledge gap identified")

        if eval_result.weaknesses:
            significance_parts.append(f"weaknesses: {', '.join(eval_result.weaknesses[:2])}")
        if eval_result.missing_concepts:
            significance_parts.append(f"missing concepts: {', '.join(eval_result.missing_concepts[:2])}")
        if eval_result.strengths:
            significance_parts.append(f"strengths: {', '.join(eval_result.strengths[:2])}")

        significance = "; ".join(significance_parts) if significance_parts else "interview evidence"

        return MemoryEvidence(
            candidate_id=state.candidate.member.id,
            session_id=state.session_id if hasattr(state, 'session_id') else "unknown",
            turn_number=turn.turn_number,
            curriculum_day=turn.curriculum_day,
            topic=turn.topic,
            question=turn.question,
            answer=turn.answer[:500],  # Limit answer length
            strengths=eval_result.strengths,
            weaknesses=eval_result.weaknesses,
            missing_concepts=eval_result.missing_concepts,
            score=eval_result.score,
            significance=significance,
        )

    def _remember_evidence(
        self,
        state: OrchestratorState,
        evidence: MemoryEvidence,
        turn_number: int,
    ) -> None:
        """Write evidence to memory provider with deduplication."""
        # Avoid duplicate writes for the same turn
        if turn_number in state._memory_written_turns:
            return

        try:
            provider = self._get_memory_provider()
            provider.remember_evidence(evidence)
            state._memory_written_turns.add(turn_number)
        except Exception as e:
            # Log warning but do not crash the interview
            print(f"Warning: Failed to write memory: {e}")

    def _build_feedback(self, state: OrchestratorState) -> FeedbackPayload:
        """Ask the LLM to synthesise final feedback from all turns."""
        turns_data = [
            {
                "turn": t.turn_number,
                "day": t.curriculum_day,
                "topic": t.topic,
                "strategy": t.strategy,
                "difficulty": t.difficulty,
                "question": t.question,
                "answer": t.answer[:300],
                "score": t.evaluation.score if t.evaluation else None,
                "strengths": t.evaluation.strengths if t.evaluation else [],
                "weaknesses": t.evaluation.weaknesses if t.evaluation else [],
                "missing_concepts": t.evaluation.missing_concepts if t.evaluation else [],
                "follow_up_needed": t.evaluation.follow_up_needed if t.evaluation else None,
            }
            for t in state.turns
        ]
        user_content = (
            f"Candidate: {state.candidate.member.name}, "
            f"{state.candidate.member.jobRole}\n\n"
            f"Interview turns:\n{json.dumps(turns_data, indent=2)}\n\n"
            f"Overall score: {state.competency.overall_score:.1f}/10\n"
            f"Covered days: {state.competency.covered_days}\n"
            "Use only the evidence above. Do not invent gaps that are contradicted\n"
            "by the candidate's answers or evaluator notes.\n"
            "Write the final report."
        )
        messages = [
            {"role": "system", "content": _FEEDBACK_SYSTEM},
            {"role": "user", "content": user_content},
        ]
        raw = self._llm.generate_structured(messages, FeedbackPayload)
        return raw
