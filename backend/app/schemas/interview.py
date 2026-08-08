"""
POST /api/interview request & response schemas (technical-spec.md authoritative).

Init turn  : { sessionId, candidate }   → no `message`
Follow-up  : { sessionId, message }     → no `candidate`
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, model_validator

from app.schemas.candidate import CandidateRecord


# ── Request ──────────────────────────────────────────────────────────────────

class InterviewRequest(BaseModel):
    sessionId: str
    candidate: Optional[CandidateRecord] = None
    message: Optional[str] = None

    @model_validator(mode="after")
    def check_turn_type(self) -> "InterviewRequest":
        has_candidate = self.candidate is not None
        has_message = self.message is not None
        if not has_candidate and not has_message:
            raise ValueError(
                "Either 'candidate' (init turn) or 'message' (follow-up turn) must be present."
            )
        return self

    @property
    def is_init(self) -> bool:
        """True when this is the first (initialization) turn."""
        return self.candidate is not None


# ── Response ─────────────────────────────────────────────────────────────────

class FeedbackPayload(BaseModel):
    summary: str
    strengths: list[str]
    gaps: list[str]
    next: list[str]


class InterviewResponse(BaseModel):
    reply: str
    done: bool
    feedback: Optional[FeedbackPayload] = None
