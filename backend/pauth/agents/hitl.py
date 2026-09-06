"""HITL node: pause the graph until a human approves or sends the case back."""

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from pauth.graph.events import emit
from pauth.graph.state import PauthState
from pauth.schemas import HitlDecision


async def hitl(state: PauthState, config: RunnableConfig) -> dict:
    """Emit the review packet, then `interrupt()` until `Command(resume=...)`.

    The resume payload is the human decision (approved / changes, notes, new files).
    """
    match = state.get("match_result") or {}
    review = {
        "kind": "review",
        "data": {
            "match_result": match,
            "clinical": state.get("clinical") or {},
            "policy_checklist": state.get("policy_checklist") or {},
            "gaps": [
                item
                for item in (match.get("items") or [])
                if item.get("status") in {"missing", "conflict"}
            ],
        },
    }
    await emit(config, "hitl", "start", {"gaps": len(review["data"]["gaps"])})
    await emit(config, "hitl", "artifact", review)
    decision = interrupt(review["data"])
    parsed = HitlDecision.model_validate(decision)
    data = parsed.model_dump()
    await emit(config, "hitl", "end", data)
    return {"hitl": data}
