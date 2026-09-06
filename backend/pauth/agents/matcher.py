"""Matcher: score each policy criterion against clinical facts and document text."""

import json

from langchain_core.runnables import RunnableConfig

from pauth.agents.common import use_llm
from pauth.graph.events import emit
from pauth.graph.state import PauthState
from pauth.schemas import Citation, MatchItem, MatchResult


async def matcher(state: PauthState, config: RunnableConfig) -> dict:
    """Join point after the three specialists. Writes `match_result` for HITL."""
    await emit(config, "matcher", "start", {})
    try:
        if use_llm(config):
            await emit(config, "matcher", "token", {"text": "Scoring criteria"})
            result = await _llm_match(state)
        else:
            result = _stub_match(state)
        data = result.model_dump()
        await emit(config, "matcher", "artifact", {"kind": "match", "data": data})
        await emit(
            config,
            "matcher",
            "end",
            {"met": result.met, "missing": result.missing, "conflict": result.conflict},
        )
        return {"match_result": data}
    except Exception as exc:
        await emit(config, "matcher", "error", {"message": str(exc)})
        raise


def _blob(state: PauthState) -> str:
    """Lowercased bag of clinical + document + notes text for the stub scorer."""
    clinical = state.get("clinical") or {}
    documents = state.get("documents") or {}
    parts = [
        " ".join(clinical.get("diagnoses") or []),
        " ".join(clinical.get("failed_therapies") or []),
        clinical.get("history") or "",
        clinical.get("severity") or "",
    ]
    for section in documents.get("sections") or []:
        parts.append(section.get("text") or "")
    intake = state.get("intake") or {}
    parts.append(intake.get("notes") or "")
    return " ".join(parts).lower()


def _stub_match(state: PauthState) -> MatchResult:
    """Heuristic overlap scorer used without an API key. Not a clinical engine."""
    checklist = state.get("policy_checklist") or {}
    blob = _blob(state)
    items: list[MatchItem] = []
    for criterion in checklist.get("items") or []:
        text = criterion.get("text") or ""
        tokens = [token.lower() for token in text.replace(",", " ").split() if len(token) > 5]
        hits = sum(1 for token in tokens[:8] if token in blob)
        if hits >= 2 or any(token in blob for token in ("documented", "methotrexate", "ferritin", "seizure", "tb")):
            status = "met"
            rationale = "Chart language overlaps this criterion."
        else:
            status = "missing"
            rationale = "No clear supporting language was found for this criterion."
        quote = blob[:180]
        items.append(
            MatchItem(
                criterion_id=criterion.get("id") or "",
                criterion=text,
                status=status,
                rationale=rationale,
                evidence=[Citation(doc_id="chart", page=1, quote=quote)] if quote else [],
            )
        )
    met = sum(1 for item in items if item.status == "met")
    missing = sum(1 for item in items if item.status == "missing")
    conflict = sum(1 for item in items if item.status == "conflict")
    summary = f"{met} met, {missing} missing, {conflict} conflict"
    return MatchResult(summary=summary, items=items, met=met, missing=missing, conflict=conflict)


async def _llm_match(state: PauthState) -> MatchResult:
    """Model scores each criterion as met, missing, or conflict with citations."""
    from pauth.services.llm import get_llm

    llm = get_llm().with_structured_output(MatchResult)
    return await llm.ainvoke(
        [
            (
                "system",
                "Score each payer criterion against the clinical facts and document sections. "
                "Status must be met, missing, or conflict. Cite short quotes. Do not invent evidence.",
            ),
            (
                "human",
                json.dumps(
                    {
                        "clinical": state.get("clinical"),
                        "documents": state.get("documents"),
                        "policy": state.get("policy_checklist"),
                    },
                    default=str,
                ),
            ),
        ]
    )
