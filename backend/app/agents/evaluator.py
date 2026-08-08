"""
Answer Evaluator Agent
======================

Receives:
  - candidate profile (CandidateRecord)
  - curriculum day context (from curriculum_loader)
  - current question text
  - candidate answer text
  - recent interview history (list[InterviewTurn])

Produces: AnswerEvaluation

Evaluation criteria
-------------------
1. Technical correctness
2. Conceptual understanding
3. Engineering reasoning
4. Practical applicability
5. Technical depth
6. Communication clarity

The LLM is injected so tests can pass a FakeLLMProvider.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.schemas.candidate import CandidateRecord
from app.schemas.intelligence import AnswerEvaluation, InterviewTurn
from app.services import curriculum_loader

if TYPE_CHECKING:
    from app.services.llm import LLMProvider

_SYSTEM_PROMPT = """\
You are an expert technical interviewer and answer evaluator.
Evaluate the candidate's answer objectively. Base your evaluation
PRIMARILY on the actual answer content — not on the candidate's profile.
Profile signals (missions, attempts) are context only.

Return ONLY a JSON object with these exact keys:
- score          : float 0-10 (overall)
- correctness    : float 0-10
- depth          : float 0-10
- reasoning      : string (≤120 words, evaluator rationale)
- strengths      : list[string]
- weaknesses     : list[string]
- missing_concepts : list[string]
- follow_up_needed : bool
- recommended_strategy : one of baseline|clarification|conceptual_probe|
  architecture_probe|scenario|debugging|tradeoff|production|
  weakness_probe|synthesis
- recommended_difficulty : one of easy|medium|hard
"""


def _candidate_summary(candidate: CandidateRecord) -> str:
    m = candidate.member
    passed = [
        ms.title for ms in candidate.missions if ms.passed
    ]
    skipped = [ms.title for ms in candidate.missions if ms.skipped]
    return (
        f"Candidate: {m.name}, {m.jobRole}, {m.yearsExperience} yrs experience, "
        f"{m.education}.\n"
        f"Missions passed: {', '.join(passed) or 'none'}.\n"
        f"Missions skipped: {', '.join(skipped) or 'none'}.\n"
        f"Commit days: {candidate.signals.commitDays}, "
        f"missions first-try: {candidate.signals.missionsFirstTry}."
    )


def _history_excerpt(history: list[InterviewTurn], last_n: int = 3) -> str:
    if not history:
        return "No prior turns."
    lines = []
    for t in history[-last_n:]:
        lines.append(f"[Turn {t.turn_number}] Q: {t.question}\n  A: {t.answer[:200]}")
    return "\n".join(lines)


class Evaluator:
    def __init__(self, llm: "LLMProvider") -> None:
        self._llm = llm

    def evaluate(
        self,
        candidate: CandidateRecord,
        curriculum_day: int,
        question: str,
        answer: str,
        history: list[InterviewTurn],
    ) -> AnswerEvaluation:
        day_context = curriculum_loader.summarise_day(curriculum_day)
        candidate_ctx = _candidate_summary(candidate)
        history_ctx = _history_excerpt(history)

        user_content = (
            f"## Curriculum Context\n{day_context}\n\n"
            f"## Candidate Profile\n{candidate_ctx}\n\n"
            f"## Recent Interview History\n{history_ctx}\n\n"
            f"## Current Question\n{question}\n\n"
            f"## Candidate's Answer\n{answer}\n\n"
            "Evaluate the answer now."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        return self._llm.generate_structured(messages, AnswerEvaluation)
