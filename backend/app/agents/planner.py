"""
Interview Planner Agent
=======================

Decides what the next question should look like based on:
  - Candidate profile
  - CompetencyState (running picture of the interview so far)
  - InterviewTurn history
  - Curriculum coverage constraints
  - Relevant memories from Breeth

Supported strategies
--------------------
baseline, clarification, conceptual_probe, architecture_probe,
scenario, debugging, tradeoff, production, weakness_probe, synthesis

Difficulty policy (adaptive)
-----------------------------
strong answer  (score >= 7)  → escalate difficulty or hold hard
medium answer  (5 <= score < 7) → hold current difficulty
weak answer    (score < 5)   → reduce or probe weakness

Coverage requirement
--------------------
The interview targets >= 8 questions across >= 4 distinct curriculum days.
After >= 6 follow-up weakness probes in a row, the planner forces a new day.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, List, Optional

from app.schemas.candidate import CandidateRecord
from app.schemas.intelligence import (
    AnswerEvaluation,
    CompetencyState,
    Difficulty,
    InterviewDecision,
    InterviewTurn,
    NextQuestion,
    Strategy,
)
from app.services.memory import MemoryResult, MemoryProvider
from app.services import curriculum_loader

if TYPE_CHECKING:
    from app.services.llm import LLMProvider

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_QUESTIONS = 8
MIN_DAYS = 4
MAX_QUESTIONS = 10

_ESCALATE: dict[Difficulty, Difficulty] = {
    "easy": "medium",
    "medium": "hard",
    "hard": "hard",
}
_REDUCE: dict[Difficulty, Difficulty] = {
    "easy": "easy",
    "medium": "easy",
    "hard": "medium",
}

_SYSTEM_PROMPT = """\
You are an expert interview planner. Decide the NEXT question for a
technical interview.

Return ONLY a JSON object with these exact keys:
- question         : string (the actual question text, ≤80 words)
- curriculum_day   : int
- topic            : string
- strategy         : one of baseline|clarification|conceptual_probe|
  architecture_probe|scenario|debugging|tradeoff|production|
  weakness_probe|synthesis
- difficulty       : one of easy|medium|hard
- rationale        : string (≤60 words, private planner reasoning)

Rules:
- Do NOT repeat a question already asked.
- Prioritize meaningful follow-ups if the last evaluation recommended one.
- Must eventually cover at least 4 distinct curriculum days.
- Use only curriculum days provided in the context.
- Consider relevant memories from the candidate's interview history.
- If the candidate made a concrete technical claim, ask about that claim
    before moving to a new curriculum topic.
- Do not ask a generic follow-up just to satisfy a follow-up quota.
- Use candidate names sparingly and only when it reads naturally.
- Vary openings naturally: direct, probe, challenge, scenario,
    trade-off, clarification, transition, or deepening.
"""


_FOLLOW_UP_MARKERS = (
        "because",
        "trade-off",
        "tradeoff",
        "when",
        "if ",
        "however",
        "instead",
        "hybrid",
        "balance",
        "decide",
        "prefer",
        "compare",
        "choose",
        "fine-tune",
        "construct",
        "evaluate",
        "overfit",
        "rare",
        "specific",
)


def _next_uncovered_day(
    candidate: CandidateRecord,
    covered_days: List[int],
    preferred_days: List[int],
) -> int:
    """Pick the best uncovered day the candidate has worked on."""
    candidate_days = {m.day for m in candidate.missions}
    # Prefer days the candidate actually attempted
    options = [
        d for d in preferred_days
        if d not in covered_days and d in candidate_days
    ]
    if not options:
        # Fall back to any uncovered curriculum day
        options = [d for d in curriculum_loader.all_days() if d not in covered_days]
    if not options:
        # All days covered – pick any candidate day not recently covered
        options = list(candidate_days - set(covered_days[-3:]))
    return random.choice(options) if options else (preferred_days[0] if preferred_days else 7)


class Planner:
    def __init__(self, llm: "LLMProvider") -> None:
        self._llm = llm

    # ── Public entry point ────────────────────────────────────────────────────

    def decide(
        self,
        candidate: CandidateRecord,
        state: CompetencyState,
        history: List[InterviewTurn],
        last_eval: AnswerEvaluation | None,
        question_number: int,
        memories: Optional[List[MemoryResult]] = None,
    ) -> InterviewDecision:
        """
        Determine whether the interview should end and, if not, what
        the next question should look like.
        """
        should_end = self._should_end(state, history, question_number)
        if should_end:
            # Generate a closing question (synthesis) then end
            nq = self._plan(candidate, state, history, last_eval, force_end=True, memories=memories)
            return InterviewDecision(next_question=nq, should_end=True, end_reason="target reached")

        nq = self._plan(candidate, state, history, last_eval, memories=memories)
        return InterviewDecision(next_question=nq, should_end=False)

    # ── Completion check ──────────────────────────────────────────────────────

    def _should_end(
        self,
        state: CompetencyState,
        history: List[InterviewTurn],
        question_number: int,
    ) -> bool:
        if question_number < MIN_QUESTIONS:
            return False
        enough_days = len(set(state.covered_days)) >= MIN_DAYS
        return enough_days or question_number >= MAX_QUESTIONS

    # ── Difficulty update ─────────────────────────────────────────────────────

    @staticmethod
    def _update_difficulty(state: CompetitiveState, eval_: AnswerEvaluation) -> Difficulty:
        if eval_.score >= 7.0:
            return _ESCALATE[state.current_difficulty]
        elif eval_.score >= 5.0:
            return state.current_difficulty
        else:
            return _REDUCE[state.current_difficulty]

    # ── Strategy selection ────────────────────────────────────────────────────

    @staticmethod
    def _pick_strategy(
        state: CompetencyState,
        last_eval: AnswerEvaluation | None,
        force_end: bool,
        last_answer: str | None = None,
        memories: Optional[List[MemoryResult]] = None,
    ) -> Strategy:
        if force_end:
            return "synthesis"
        if last_eval is None:
            return "baseline"

        answer_text = (last_answer or "").lower()
        memory_text = " ".join(m.fact for m in memories or ()).lower()
        has_specific_signal = (
            len((last_answer or "").split()) >= 12
            and any(marker in answer_text for marker in _FOLLOW_UP_MARKERS)
        ) or any(marker in memory_text for marker in ("hybrid", "bm25", "rare", "trade-off", "compare"))

        # Break repeated weakness-probe loops before asking yet another probe.
        if last_eval.score < 5.0 and state.consecutive_weak >= 3:
            return "conceptual_probe"

        # Follow the evaluator when it explicitly asks for a follow-up.
        if last_eval.follow_up_needed:
            return last_eval.recommended_strategy

        # Strong and medium answers can still deserve a targeted follow-up if
        # they contain a concrete technical decision, trade-off, or claim.
        if last_eval.score >= 7.0:
            if has_specific_signal:
                if any(marker in answer_text for marker in ("trade-off", "tradeoff", "compare", "balance", "prefer", "choose")):
                    return "tradeoff"
                if any(marker in answer_text for marker in ("scale", "production", "deploy", "latency", "throughput")):
                    return "scenario"
                if any(marker in answer_text for marker in ("architecture", "system", "design", "pipeline")):
                    return "architecture_probe"
                return "clarification"
            if state.consecutive_strong >= 2:
                return "scenario"
            return "conceptual_probe"

        if last_eval.score >= 5.0:
            if has_specific_signal:
                if any(marker in answer_text for marker in ("trade-off", "tradeoff", "compare", "balance", "prefer", "choose")):
                    return "tradeoff"
                return "clarification"
            return "conceptual_probe"

        # Weak answer: probe once, but do not keep hammering the same weakness.
        if state.consecutive_weak >= 2:
            return "conceptual_probe"
        return "weakness_probe"

    @staticmethod
    def _should_follow_up(
        state: CompetencyState,
        history: List[InterviewTurn],
        last_eval: AnswerEvaluation,
        last_answer: str,
        memories: Optional[List[MemoryResult]] = None,
    ) -> bool:
        if not history:
            return False

        current_day = history[-1].curriculum_day
        same_day_turns = sum(1 for turn in history if turn.curriculum_day == current_day)

        # Keep at most one follow-up per curriculum day so coverage keeps moving.
        if same_day_turns >= 2:
            return False

        if last_eval.score < 5.0:
            return state.consecutive_weak < 3 and (
                last_eval.follow_up_needed
                or bool(last_eval.weaknesses)
                or bool(last_eval.missing_concepts)
            )

        if last_eval.follow_up_needed:
            return True

        answer_text = last_answer.lower()
        memory_text = " ".join(m.fact for m in memories or ()).lower()
        specific_signal = (
            len(last_answer.split()) >= 12
            and any(marker in answer_text for marker in _FOLLOW_UP_MARKERS)
        ) or any(marker in memory_text for marker in ("hybrid", "bm25", "rare", "trade-off", "compare"))

        if last_eval.score >= 7.0:
            return specific_signal

        return specific_signal or bool(last_eval.weaknesses) or bool(last_eval.missing_concepts)

    # ── LLM call ─────────────────────────────────────────────────────────────

    def _plan(
        self,
        candidate: CandidateRecord,
        state: CompetencyState,
        history: List[InterviewTurn],
        last_eval: AnswerEvaluation | None,
        force_end: bool = False,
        memories: Optional[List[MemoryResult]] = None,
    ) -> NextQuestion:
        # Pick next curriculum day
        candidate_days = sorted({m.day for m in candidate.missions})
        last_answer = history[-1].answer if history else ""
        target_day = _next_uncovered_day(candidate, state.covered_days, candidate_days)

        # Allow follow-ups on the same day when appropriate
        if last_eval and self._should_follow_up(state, history, last_eval, last_answer, memories):
            target_day = history[-1].curriculum_day

        strategy = self._pick_strategy(
            state,
            last_eval,
            force_end,
            last_answer=last_answer,
            memories=memories,
        )
        difficulty = (
            self._update_difficulty(state, last_eval)
            if last_eval
            else state.current_difficulty
        )

        day_context = curriculum_loader.summarise_day(target_day)
        asked_questions = "\n".join(
            f"- [Day {t.curriculum_day}] {t.question}" for t in history
        )
        weaknesses = "\n".join(f"- {w}" for w in state.weaknesses) or "none yet"
        last_evaluation = "none yet"
        if last_eval is not None:
            last_evaluation = (
                f"score={last_eval.score:.1f}, follow_up_needed={last_eval.follow_up_needed}, "
                f"strategy={last_eval.recommended_strategy}, difficulty={last_eval.recommended_difficulty}, "
                f"strengths={last_eval.strengths}, weaknesses={last_eval.weaknesses}, "
                f"missing_concepts={last_eval.missing_concepts}, reasoning={last_eval.reasoning}"
            )

        last_answer_text = last_answer[:350] if last_answer else "none yet"

        # Format memories for the prompt
        memories_text = ""
        if memories:
            memories_list = []
            for m in memories:
                # Truncate fact to avoid too long prompt
                fact = m.fact
                if len(fact) > 200:
                    fact = fact[:200] + "..."
                memories_list.append(f"- {fact}")
            memories_text = "\nRelevant candidate memories:\n" + "\n".join(memories_list) if memories_list else ""

        user_content = (
            f"## Candidate\n"
            f"{candidate.member.name}, {candidate.member.jobRole}, "
            f"{candidate.member.yearsExperience} yrs exp\n\n"
            f"## Target Curriculum Day\n{day_context}\n\n"
            f"## Questions Already Asked\n{asked_questions or 'none yet'}\n\n"
            f"## Last Candidate Answer\n{last_answer_text}\n\n"
            f"## Last Evaluation Signals\n{last_evaluation}\n\n"
            f"## Known Weaknesses\n{weaknesses}\n\n"
            f"## Current State\n"
            f"Difficulty: {difficulty}, Strategy: {strategy}\n"
            f"Covered days: {state.covered_days}\n"
            f"Question #{len(history) + 1}"
            f"{memories_text}\n\n"
            "## Decision Policy\n"
            "- If the candidate made a concrete claim, probe that claim directly.\n"
            "- If the answer was weak, ask one targeted corrective follow-up.\n"
            "- If the current topic has already been explored, move to a new curriculum day.\n"
            "- Avoid generic filler questions that do not respond to the answer.\n\n"
            f"Generate the next interview question."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        return self._llm.generate_structured(messages, NextQuestion)