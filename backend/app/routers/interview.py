"""
Interview router – POST /api/interview

Distinguishes init turn (candidate present) from follow-up turns (message present).
Delegates intelligence to the Orchestrator; maintains state in session_store.
"""
from __future__ import annotations

import os

import logging

from fastapi import APIRouter, HTTPException

from app.agents.orchestrator import Orchestrator, OrchestratorState
from app.schemas.interview import InterviewRequest, InterviewResponse, FeedbackPayload
from app.services import session_store
from app.services.llm import get_provider, LLMProvider

router = APIRouter()
logger = logging.getLogger(__name__)

# ── LLM provider singleton ────────────────────────────────────────────────────
# Replaced by dependency injection in tests via override.

_provider: LLMProvider | None = None


def _get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


def set_provider(p: LLMProvider) -> None:
    """Test hook – inject a fake provider before the first request."""
    global _provider
    _provider = p


def reset_provider() -> None:
    """Test hook – clear the provider so it is rebuilt from env vars."""
    global _provider
    _provider = None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/interview", response_model=InterviewResponse)
def interview(req: InterviewRequest) -> InterviewResponse:

    # ── Init turn ─────────────────────────────────────────────────────────────
    if req.is_init:
        if session_store.get_session(req.sessionId):
            raise HTTPException(
                status_code=409,
                detail=f"Session '{req.sessionId}' already exists. Send a message instead.",
            )
        sess = session_store.create_session(req.sessionId, req.candidate)

        # Boot orchestrator
        orch_state = OrchestratorState(candidate=req.candidate)
        sess.orchestrator_state = orch_state

        orchestrator = Orchestrator(_get_provider())
        try:
            first_question = orchestrator.start(orch_state)
        except Exception as e:
            logger.error(f"Provider error: {type(e).__name__} - {str(e)}")
            with open("error.log", "a") as f:
                import traceback
                f.write(f"Provider error: {type(e).__name__} - {str(e)}\n{traceback.format_exc()}\n")
            raise HTTPException(
                status_code=500,
                detail="An error occurred communicating with the AI provider."
            )

        sess.history.append({"role": "assistant", "content": first_question})

        return InterviewResponse(reply=first_question, done=False)

    # ── Follow-up turn ────────────────────────────────────────────────────────
    sess = session_store.get_session(req.sessionId)
    if sess is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{req.sessionId}' not found. Start with a candidate payload.",
        )
    if sess.done:
        raise HTTPException(
            status_code=410,
            detail="This interview session has already ended.",
        )

    sess.history.append({"role": "user", "content": req.message})
    sess.turn_count += 1

    orchestrator = Orchestrator(_get_provider())
    try:
        reply, done, feedback = orchestrator.next_turn(sess.orchestrator_state, req.message)
    except Exception as e:
        logger.error(f"Provider error: {type(e).__name__} - {str(e)}")
        with open("error.log", "a") as f:
            import traceback
            f.write(f"Provider error: {type(e).__name__} - {str(e)}\n{traceback.format_exc()}\n")
        raise HTTPException(
            status_code=500,
            detail="An error occurred communicating with the AI provider."
        )

    sess.done = done
    sess.history.append({"role": "assistant", "content": reply})

    return InterviewResponse(reply=reply, done=done, feedback=feedback)

