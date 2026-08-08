"""
Typed schemas for the candidate data (mirrors candidates.json exactly).
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class MissionRecord(BaseModel):
    day: int
    title: str
    passed: Optional[bool] = None
    attempts: Optional[int] = None
    skipped: Optional[bool] = None


class MemberInfo(BaseModel):
    id: str
    name: str
    jobRole: str
    yearsExperience: int
    education: str
    status: str


class Signals(BaseModel):
    commitDays: int
    missionsCompleted: int
    missionsFirstTry: int


class CandidateRecord(BaseModel):
    member: MemberInfo
    missions: list[MissionRecord]
    signals: Signals


class CandidatesFile(BaseModel):
    candidates: list[CandidateRecord]
