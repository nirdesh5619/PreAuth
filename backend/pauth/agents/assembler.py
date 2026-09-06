"""Assembler: draft a letter of medical necessity. Does not submit to a payer."""

from datetime import date
import json

from langchain_core.runnables import RunnableConfig

from pauth.agents.common import use_llm
from pauth.graph.events import emit
from pauth.graph.state import PauthState
from pauth.schemas import Packet


async def assembler(state: PauthState, config: RunnableConfig) -> dict:
    """Write the packet after HITL approval. Stores markdown on `packet`."""
    await emit(config, "assembler", "start", {})
    try:
        if use_llm(config):
            await emit(config, "assembler", "token", {"text": "Drafting letter of medical necessity"})
            packet = await _llm_packet(state)
        else:
            packet = _stub_packet(state)
        data = packet.model_dump()
        await emit(config, "assembler", "artifact", {"kind": "packet", "data": data})
        await emit(config, "assembler", "end", {"title": packet.title})
        return {"packet": data}
    except Exception as exc:
        await emit(config, "assembler", "error", {"message": str(exc)})
        raise


def _stub_packet(state: PauthState) -> Packet:
    """Template letter from intake, clinical facts, match table, and reviewer notes."""
    intake = state.get("intake") or {}
    clinical = state.get("clinical") or {}
    match = state.get("match_result") or {}
    policy = state.get("policy_checklist") or {}
    hitl = state.get("hitl") or {}
    title = f"Letter of medical necessity — {intake.get('procedure') or 'procedure'}"
    lines = [
        f"# {title}",
        "",
        f"Date: {date.today().isoformat()}",
        f"Patient: {intake.get('patient_initials') or 'n/a'}",
        f"Payer / plan: {intake.get('payer') or ''} {intake.get('plan') or ''}".strip(),
        f"Procedure: {intake.get('procedure') or ''}",
        f"CPT: {intake.get('cpt') or 'n/a'}  ICD: {intake.get('icd') or 'n/a'}",
        "",
        "## Clinical summary",
        f"- Diagnoses: {', '.join(clinical.get('diagnoses') or []) or 'see chart'}",
        f"- Failed therapies: {', '.join(clinical.get('failed_therapies') or []) or 'none extracted'}",
        f"- Severity: {clinical.get('severity') or 'unspecified'}",
        "",
        f"## Policy: {policy.get('title') or policy.get('policy_id') or 'n/a'}",
    ]
    for item in match.get("items") or []:
        lines.append(f"- **{item.get('status')}** — {item.get('criterion')}")
        if item.get("rationale"):
            lines.append(f"  - {item.get('rationale')}")
    lines += [
        "",
        "## Human review",
        f"Status: {hitl.get('status') or 'n/a'}",
        hitl.get("notes") or "No additional reviewer notes.",
        "",
        "## Request",
        "Please approve this prior authorization based on the attached evidence. This packet is a draft for human submission; it has not been sent to the payer.",
    ]
    markdown = "\n".join(lines)
    return Packet(title=title, markdown=markdown, summary=match.get("summary") or "")


async def _llm_packet(state: PauthState) -> Packet:
    """Model-written LMN constrained to facts already on state."""
    from pauth.services.llm import get_llm

    llm = get_llm().with_structured_output(Packet)
    return await llm.ainvoke(
        [
            (
                "system",
                "Write a concise letter of medical necessity in markdown for a prior authorization. "
                "Use only provided facts. Include a criteria table. Do not claim the request was submitted.",
            ),
            (
                "human",
                json.dumps(
                    {
                        "intake": state.get("intake"),
                        "clinical": state.get("clinical"),
                        "policy": state.get("policy_checklist"),
                        "match": state.get("match_result"),
                        "hitl": state.get("hitl"),
                    },
                    default=str,
                ),
            ),
        ]
    )
