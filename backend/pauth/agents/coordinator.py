"""Coordinator: router that fans out to Document, Clinical, and Policy."""

from langchain_core.runnables import RunnableConfig

from pauth.graph.events import emit
from pauth.graph.state import PauthState


async def coordinator(state: PauthState, config: RunnableConfig) -> dict:
    """Increment the loop tick and emit the fan-out. Does not rewrite clinical state.

    `rerun_policy` is recorded for the UI; the Policy node itself decides whether
    to skip retrieval when payer/procedure did not change after HITL.
    """
    tick = int(state.get("tick") or 0) + 1
    hitl = state.get("hitl") or {}
    rerun_policy = True
    if hitl.get("status") == "changes":
        rerun_policy = bool(hitl.get("payer_or_procedure_changed")) or not state.get("policy_checklist")
    await emit(
        config,
        "coordinator",
        "start",
        {"tick": tick, "rerun_policy": rerun_policy},
    )
    fan_out = ["document", "clinical", "policy"]
    await emit(config, "coordinator", "end", {"fan_out": fan_out, "tick": tick})
    await emit(
        config,
        "coordinator",
        "artifact",
        {"kind": "route", "data": {"fan_out": fan_out, "tick": tick}},
    )
    return {"tick": tick}
