"""Pydantic contracts exchanged between agents, the API, and the frontend."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Closed objects so OpenAI structured output can set `additionalProperties: false`."""

    model_config = ConfigDict(extra="forbid")


class Citation(StrictModel):
    """A short quote back to a source document page."""

    doc_id: str = ""
    page: int = 1
    quote: str = ""


class DocumentSection(StrictModel):
    """One indexed slice of a chart file or intake note."""

    heading: str
    text: str
    citations: list[Citation] = Field(default_factory=list)


class IndexedFile(StrictModel):
    """File identity echoed on the document artifact, not invented by the model."""

    id: str = ""
    filename: str = ""
    content_type: str = ""


class DocumentSections(StrictModel):
    """LLM output for the document agent: cited sections only."""

    sections: list[DocumentSection] = Field(default_factory=list)


class DocumentBundle(StrictModel):
    """Document agent output: sections plus the files they came from."""

    sections: list[DocumentSection] = Field(default_factory=list)
    files: list[IndexedFile] = Field(default_factory=list)


class ClinicalFacts(StrictModel):
    """Clinical agent output used by Matcher and Assembler."""

    diagnoses: list[str] = Field(default_factory=list)
    icd_codes: list[str] = Field(default_factory=list)
    cpt_codes: list[str] = Field(default_factory=list)
    failed_therapies: list[str] = Field(default_factory=list)
    severity: str = ""
    history: str = ""
    citations: list[Citation] = Field(default_factory=list)


class PolicyItem(StrictModel):
    """A single coverage criterion on a payer checklist."""

    id: str
    text: str
    required: bool = True


class PolicyChecklist(StrictModel):
    """Policy agent output: retrieved (and optionally reworded) criteria."""

    payer: str = ""
    policy_id: str = ""
    title: str = ""
    items: list[PolicyItem] = Field(default_factory=list)
    source: str = ""


CriterionStatus = Literal["met", "missing", "conflict"]


class MatchItem(StrictModel):
    """Matcher verdict for one policy criterion."""

    criterion_id: str
    criterion: str
    status: CriterionStatus
    rationale: str = ""
    evidence: list[Citation] = Field(default_factory=list)


class MatchResult(StrictModel):
    """Full matcher scorecard shown in HITL review."""

    summary: str = ""
    items: list[MatchItem] = Field(default_factory=list)
    met: int = 0
    missing: int = 0
    conflict: int = 0


class HitlDecision(BaseModel):
    """Payload posted when a human resumes an interrupted graph."""

    status: Literal["approved", "changes", "pending"] = "pending"
    notes: str = ""
    payer_or_procedure_changed: bool = False
    new_file_ids: list[str] = Field(default_factory=list)


class Packet(StrictModel):
    """Assembler output: a letter of medical necessity, not a submission."""

    title: str = ""
    markdown: str = ""
    summary: str = ""


class IntakeFile(BaseModel):
    """Uploaded chart file metadata, including the local path agents read."""

    id: str = ""
    filename: str = ""
    path: str = ""
    content_type: str = ""


class Intake(BaseModel):
    """Case fields plus file metadata passed into graph state."""

    patient_initials: str
    payer: str
    plan: str = ""
    procedure: str
    cpt: str = ""
    icd: str = ""
    urgency: str = "routine"
    notes: str = ""
    files: list[IntakeFile] = Field(default_factory=list)
