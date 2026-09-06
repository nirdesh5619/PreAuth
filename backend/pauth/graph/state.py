"""Shared LangGraph state. Each specialist writes only its own keys."""

from typing import Any, TypedDict


class PauthState(TypedDict, total=False):
    """Thread state for one prior-auth run.

    `tick` increments each time the coordinator fans out, including HITL loops.
    """

    case_id: str
    run_id: str
    intake: dict[str, Any]
    documents: dict[str, Any]
    clinical: dict[str, Any]
    policy_checklist: dict[str, Any]
    match_result: dict[str, Any]
    hitl: dict[str, Any]
    packet: dict[str, Any]
    tick: int
