"""
Interview router – POST /api/interview

Distinguishes init turn (candidate present) from follow-up turns (message present).
No LLM yet – stub replies allow the full API contract to be tested now.
"""
from fastapi import APIRouter, HTTPException

from app.schemas.interview import InterviewRequest, InterviewResponse, FeedbackPayload
from app.services import session_store

router = APIRouter()

_MAX_TURNS = 5   # stub: after this many follow-ups, close the interview


@router.post("/interview", response_model=InterviewResponse)
def interview(req: InterviewRequest) -> InterviewResponse:

    # ── Init turn ──────────────────────────────────────────────────────────
    if req.is_init:
        if session_store.get_session(req.sessionId):
            raise HTTPException(
                status_code=409,
                detail=f"Session '{req.sessionId}' already exists. Send a message instead.",
            )
        session_store.create_session(req.sessionId, req.candidate)
        return InterviewResponse(
            reply=(
                f"Welcome, {req.candidate.member.name}. "
                f"Let's begin your interview for the {req.candidate.member.jobRole} role."
            ),
            done=False,
        )

    # ── Follow-up turn ─────────────────────────────────────────────────────
    state = session_store.get_session(req.sessionId)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{req.sessionId}' not found. Start with a candidate payload.",
        )
    if state.done:
        raise HTTPException(
            status_code=410,
            detail="This interview session has already ended.",
        )

    state.history.append({"role": "user", "content": req.message})
    state.turn_count += 1

    # Stub: close after _MAX_TURNS follow-up messages
    if state.turn_count >= _MAX_TURNS:
        state.done = True
        feedback = FeedbackPayload(
            summary="Stub feedback – LLM evaluator not yet connected.",
            strengths=["Engaged consistently throughout the interview."],
            gaps=["No real evaluation performed in stub mode."],
            next=["Integrate the Breeth evaluator in the next task."],
        )
        reply = "Interview completed. Thank you for your time."
        state.history.append({"role": "assistant", "content": reply})
        return InterviewResponse(reply=reply, done=True, feedback=feedback)

    # Mid-interview stub reply
    reply = (
        f"[Turn {state.turn_count}] Acknowledged: '{req.message[:80]}'. "
        "Please continue."
    )
    state.history.append({"role": "assistant", "content": reply})
    return InterviewResponse(reply=reply, done=False)
