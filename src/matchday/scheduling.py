"""Kickoff-driven rollover with periodic checks for fixture changes."""

import math

from .domain import timestamp

SAFETY_CHECK_SECONDS = 21600


def poll_after(state, now):
    if not state or state.get("stale"):
        return 60
    fixture = state.get("fixture")
    if not fixture:
        return 3600
    deadline = state.get("match_lifecycle", {}).get("next_check_at") or fixture["kickoff"]
    remaining = (timestamp(deadline) - now).total_seconds()
    if remaining <= 0:
        return 1
    return min(SAFETY_CHECK_SECONDS, max(1, math.ceil(remaining)))


def kickoff_due(state, now):
    fixture = state.get("fixture") if state else None
    deadline = (state.get("match_lifecycle", {}).get("next_check_at")
                if state else None) or (fixture["kickoff"] if fixture else None)
    return bool(deadline and timestamp(deadline) <= now)
