"""
Question Generator (Interviewer Agent)
=======================================

Receives a NextQuestion decision from the planner and the relevant
curriculum context, then generates a polished, personalized,
conversational question.

Key design goals:
- Questions must feel like a real senior engineer asking them.
- They are grounded in curriculum objectives.
- They are personalised to the candidate's missions/role.
- They are NOT generic ("Explain RAG.").
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.candidate import CandidateRecord
from app.schemas.intelligence import InterviewTurn, NextQuestion
from app.services import curriculum_loader

if TYPE_CHECKING:
    from app.services.llm import LLMProvider

_SYSTEM_PROMPT = """\
You are a thoughtful senior technical interviewer conducting a live interview.
Your job is to turn a structured question spec into a single, natural,
conversational question.

Rules:
- The question must be ≤90 words.
- It must be specific — reference the candidate's background or past work.
- It must avoid generic phrasing like "Explain X" or "What is X?".
- It must be technically rigorous but conversational in tone.
- Do NOT include any preamble, greeting, or explanation.
- Do not prepend the candidate's name to every question.
- Use the candidate name only when it sounds natural, usually near the
    beginning of the interview or as an occasional acknowledgment.
- Prefer natural openings such as direct, probe, challenge, scenario,
    trade-off, clarification, transition, or deepening.
- If the prompt is a follow-up, anchor it to the concrete claim in the
    prior answer rather than restating the curriculum topic.
- Return ONLY the question text, nothing else.
"""


class Interviewer:
    def __init__(self, llm: "LLMProvider") -> None:
        self._llm = llm

    def generate_question(
        self,
        decision: NextQuestion,
        candidate: CandidateRecord,
        history: list[InterviewTurn],
    ) -> str:
        """
        Returns the final question string shown to the candidate.
        If the LLM returns the decision.question verbatim, that is also
        acceptable — the planner already produced a reasonable question.
        """
        day_context = curriculum_loader.summarise_day(decision.curriculum_day)
        missions_ctx = ", ".join(
            m.title for m in candidate.missions
            if m.day == decision.curriculum_day
        ) or "no specific mission on this day"
        last_q = history[-1].question if history else "none yet"
        last_a = history[-1].answer if history else "none yet"

        user_content = (
            f"## Question spec\n"
            f"Strategy: {decision.strategy} | Difficulty: {decision.difficulty}\n"
            f"Topic: {decision.topic}\n"
            f"Base question: {decision.question}\n\n"
            f"## Curriculum context\n{day_context}\n\n"
            f"## Candidate\n"
            f"{candidate.member.name}, {candidate.member.jobRole}, "
            f"{candidate.member.yearsExperience} yrs exp\n"
            f"Candidate's work on this day: {missions_ctx}\n\n"
            f"## Previous question asked\n{last_q}\n\n"
            f"## Previous candidate answer\n{last_a}\n\n"
            "Now write the final, polished interview question."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        result = self._llm.generate(messages)
        return result.strip() or decision.question
