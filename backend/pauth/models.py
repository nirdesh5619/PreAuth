"""SQLModel tables for cases, uploads, graph runs, events, and artifacts."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    """UTC timestamp used as the default for created/updated columns."""
    return datetime.now(timezone.utc)


def _uuid() -> str:
    """String UUID primary keys (SQLite has no native UUID type here)."""
    return str(uuid4())


class Case(SQLModel, table=True):
    """One prior-auth request: initials, payer, procedure, and pasted notes."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    patient_initials: str
    payer: str
    plan: str = ""
    procedure: str
    cpt: str = ""
    icd: str = ""
    urgency: str = "routine"
    notes: str = ""
    created_at: datetime = Field(default_factory=_now)


class CaseFile(SQLModel, table=True):
    """An uploaded chart file stored under `settings.uploads_dir`."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    case_id: str = Field(index=True)
    filename: str
    path: str
    content_type: str = "application/octet-stream"
    created_at: datetime = Field(default_factory=_now)


class Run(SQLModel, table=True):
    """One graph execution. `id` is also the LangGraph `thread_id`."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    case_id: str = Field(index=True)
    status: str = "running"
    error: str = ""
    interrupt_json: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class RunEvent(SQLModel, table=True):
    """Append-only observability event (`start|token|artifact|end|error`)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(index=True)
    ts: datetime = Field(default_factory=_now)
    node: str
    type: str
    payload_json: str = "{}"


class Artifact(SQLModel, table=True):
    """Latest structured output for a node (documents, match table, packet)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(index=True)
    node: str
    kind: str
    content_json: str
    created_at: datetime = Field(default_factory=_now)
    updated_at: Optional[datetime] = None
