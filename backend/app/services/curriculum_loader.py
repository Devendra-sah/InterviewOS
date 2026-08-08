"""
Curriculum loader – reads curriculum.json once at import time.

Provides fast lookup by day number for the planner and question generator.
"""
from __future__ import annotations
import json
from pathlib import Path
from functools import lru_cache

_DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def _raw() -> dict:
    with open(_DATA_DIR / "curriculum.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_day_index() -> dict[int, dict]:
    """Return {day_number: day_dict} for O(1) lookup."""
    return {d["day"]: d for d in _raw()["days"]}


@lru_cache(maxsize=1)
def get_module_index() -> list[dict]:
    return _raw()["modules"]


def get_day(day: int) -> dict | None:
    return get_day_index().get(day)


def days_for_module(module_n: int) -> list[int]:
    """Return all day numbers that belong to a given module."""
    for m in get_module_index():
        if m["n"] == module_n:
            start, end = m["days"]
            return list(range(start, end + 1))
    return []


def all_days() -> list[int]:
    return sorted(get_day_index().keys())


def summarise_day(day: int) -> str:
    """Short textual summary of a curriculum day for prompt injection."""
    d = get_day(day)
    if not d:
        return ""
    objs = "\n".join(f"  - {o}" for o in d.get("objectives", []))
    tools = ", ".join(d.get("tools", []))
    return (
        f"Day {day}: {d['title']} [{d['type']}]\n"
        f"Tools: {tools}\n"
        f"Objectives:\n{objs}"
    )
