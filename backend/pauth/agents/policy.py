"""Policy agent: retrieve fixture payer criteria for the intake procedure."""

from langchain_core.runnables import RunnableConfig

from pauth.agents.common import use_llm
from pauth.graph.events import emit
from pauth.graph.state import PauthState
from pauth.services.policies import retrieve_policy


async def policy(state: PauthState, config: RunnableConfig) -> dict:
    """Load a checklist from on-disk fixtures. Skip re-retrieval after HITL unless payer/procedure changed."""
    await emit(config, "policy", "start", {})
    try:
        hitl = state.get("hitl") or {}
        existing = state.get("policy_checklist")
        if existing and hitl.get("status") == "changes" and not hitl.get("payer_or_procedure_changed"):
            await emit(config, "policy", "end", {"passthrough": True})
            await emit(config, "policy", "artifact", {"kind": "policy", "data": existing})
            # Empty update keeps the previous checklist on state.
            return {}

        intake = state.get("intake") or {}
        checklist = retrieve_policy(
            payer=str(intake.get("payer") or ""),
            procedure=str(intake.get("procedure") or ""),
            cpt=str(intake.get("cpt") or ""),
        )
        data = checklist.model_dump()
        if use_llm(config):
            await emit(config, "policy", "token", {"text": "Refining retrieved criteria"})
            data = await _llm_refine(intake, data)
        await emit(config, "policy", "artifact", {"kind": "policy", "data": data})
        await emit(config, "policy", "end", {"policy_id": data.get("policy_id"), "items": len(data.get("items") or [])})
        return {"policy_checklist": data}
    except Exception as exc:
        await emit(config, "policy", "error", {"message": str(exc)})
        raise


async def _llm_refine(intake: dict, checklist: dict) -> dict:
    """Tighten fixture wording without adding coverage rules the file does not contain."""
    from pauth.schemas import PolicyChecklist, StrictModel
    from pauth.services.llm import get_llm

    class Refined(StrictModel):
        """Wrapper so structured output returns a full checklist object."""

        checklist: PolicyChecklist

    llm = get_llm().with_structured_output(Refined)
    result = await llm.ainvoke(
        [
            (
                "system",
                "You map a retrieved payer policy to a prior-auth checklist. "
                "Keep the same criteria. You may tighten wording. Do not invent coverage rules.",
            ),
            ("human", f"INTAKE:\n{intake}\n\nPOLICY:\n{checklist}"),
        ]
    )
    return result.checklist.model_dump()
