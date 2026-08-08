"""
In-memory session store.
Keeps interview state keyed by sessionId.
Designed to be swapped for Redis/DB in later tasks.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from app.schemas.candidate import CandidateRecord


@dataclass
class SessionState:
    session_id: str
    candidate: CandidateRecord
    history: list[dict] = field(default_factory=list)   # [{role, content}]
    done: bool = False
    turn_count: int = 0


# Module-level dict – replace with a proper store in production
_sessions: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState | None:
    return _sessions.get(session_id)


def create_session(session_id: str, candidate: CandidateRecord) -> SessionState:
    state = SessionState(session_id=session_id, candidate=candidate)
    _sessions[session_id] = state
    return state


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def clear_all() -> None:
    """Test helper – wipe all sessions."""
    _sessions.clear()
