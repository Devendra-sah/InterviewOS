"""
Intelligence-layer Pydantic models.

These are the structured outputs produced and consumed by the
evaluator, planner, and interviewer agents.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Strategy & Difficulty literals ────────────────────────────────────────────

Strategy = Literal[
    "baseline",
    "clarification",
    "conceptual_probe",
    "architecture_probe",
    "scenario",
    "debugging",
    "tradeoff",
    "production",
    "weakness_probe",
    "synthesis",
]

Difficulty = Literal["easy", "medium", "hard"]


# ── Answer Evaluation ─────────────────────────────────────────────────────────

class AnswerEvaluation(BaseModel):
    """Structured output from the evaluator agent."""

    score: float = Field(..., ge=0.0, le=10.0, description="Overall score 0–10")
    correctness: float = Field(..., ge=0.0, le=10.0)
    depth: float = Field(..., ge=0.0, le=10.0)
    reasoning: str = Field(..., description="Evaluator's concise rationale")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    follow_up_needed: bool = False
    recommended_strategy: Strategy = "baseline"
    recommended_difficulty: Difficulty = "medium"


# ── Next Question Decision ────────────────────────────────────────────────────

class NextQuestion(BaseModel):
    """Planner decision: what the next question should look like."""

    question: str
    curriculum_day: int
    topic: str
    strategy: Strategy
    difficulty: Difficulty
    rationale: str = ""


# ── Supporting models ─────────────────────────────────────────────────────────

class InterviewTurn(BaseModel):
    """A single Q&A pair in the interview history."""

    turn_number: int
    curriculum_day: int
    topic: str
    strategy: Strategy
    difficulty: Difficulty
    question: str
    answer: str
    evaluation: Optional[AnswerEvaluation] = None


class CompetencyState(BaseModel):
    """Running aggregated picture of the candidate's demonstrated competency."""

    overall_score: float = 5.0        # rolling average
    current_difficulty: Difficulty = "medium"
    current_strategy: Strategy = "baseline"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    covered_days: list[int] = Field(default_factory=list)
    covered_topics: list[str] = Field(default_factory=list)
    consecutive_weak: int = 0         # weak answers in a row (for recovery)
    consecutive_strong: int = 0       # strong answers in a row (for escalation)


class InterviewDecision(BaseModel):
    """Minimal wrapper so callers can inspect planner output before generation."""

    next_question: NextQuestion
    should_end: bool = False
    end_reason: str = ""
