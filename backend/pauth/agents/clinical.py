"""Clinical agent: extract diagnoses, trials, codes, and severity from the chart."""

from langchain_core.runnables import RunnableConfig

from pauth.agents.common import use_llm
from pauth.graph.events import emit
from pauth.graph.state import PauthState
from pauth.schemas import Citation, ClinicalFacts
from pauth.services.documents import extract_file_pages


async def clinical(state: PauthState, config: RunnableConfig) -> dict:
    """Read intake files directly so this node can run in parallel with Document."""
    await emit(config, "clinical", "start", {})
    try:
        intake = state.get("intake") or {}
        blob = _source_text(intake)
        if use_llm(config):
            await emit(config, "clinical", "token", {"text": "Extracting clinical facts"})
            facts = await _llm_clinical(intake, blob)
        else:
            facts = _stub_clinical(intake, blob)
        data = facts.model_dump()
        await emit(config, "clinical", "artifact", {"kind": "clinical", "data": data})
        await emit(config, "clinical", "end", {"diagnoses": facts.diagnoses})
        return {"clinical": data}
    except Exception as exc:
        await emit(config, "clinical", "error", {"message": str(exc)})
        raise


def _source_text(intake: dict) -> str:
    """Concatenate procedure codes, notes, and extracted file text for extraction."""
    parts = [
        f"Procedure: {intake.get('procedure', '')}",
        f"ICD: {intake.get('icd', '')}",
        f"CPT: {intake.get('cpt', '')}",
        intake.get("notes") or "",
    ]
    for file_meta in intake.get("files") or []:
        path = file_meta.get("path")
        if not path:
            continue
        for page in extract_file_pages(path, file_meta.get("content_type", "")):
            parts.append(page.get("text") or "")
    return "\n".join(parts)


def _stub_clinical(intake: dict, blob: str) -> ClinicalFacts:
    """Keyword extractor used when OpenAI is not configured."""
    lower = blob.lower()
    diagnoses = []
    failed = []
    if "rheumatoid" in lower or " ra" in f" {lower}":
        diagnoses.append("Rheumatoid arthritis")
    if "crohn" in lower:
        diagnoses.append("Crohn disease")
    if "iron" in lower or "anemia" in lower:
        diagnoses.append("Iron deficiency anemia")
    if "headache" in lower or "seizure" in lower or "mri" in lower:
        diagnoses.append("Neurologic indication for MRI")
    if not diagnoses and intake.get("procedure"):
        diagnoses.append(str(intake.get("procedure")))
    if "methotrexate" in lower:
        failed.append("Methotrexate")
    if "oral iron" in lower or "ferrous" in lower:
        failed.append("Oral iron")
    icd = [code.strip() for code in str(intake.get("icd") or "").split(",") if code.strip()]
    cpt = [code.strip() for code in str(intake.get("cpt") or "").split(",") if code.strip()]
    quote = blob[:240]
    return ClinicalFacts(
        diagnoses=diagnoses,
        icd_codes=icd,
        cpt_codes=cpt,
        failed_therapies=failed,
        severity="moderate to severe" if "severe" in lower else "unspecified",
        history=blob[:800],
        citations=[Citation(doc_id="chart", page=1, quote=quote)] if quote else [],
    )


async def _llm_clinical(intake: dict, blob: str) -> ClinicalFacts:
    """Structured extraction; chart text is truncated to keep the prompt bounded."""
    from pauth.services.llm import get_llm

    llm = get_llm().with_structured_output(ClinicalFacts)
    return await llm.ainvoke(
        [
            (
                "system",
                "Extract structured clinical facts for a prior authorization. "
                "Use only the provided intake and chart text. Cite short quotes.",
            ),
            ("human", f"INTAKE:\n{intake}\n\nCHART:\n{blob[:20000]}"),
        ]
    )
