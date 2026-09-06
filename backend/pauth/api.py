"""HTTP API for cases, live run events, HITL resume, and packet download."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from pauth.config import settings
from pauth.db import get_session
from pauth.graph.events import broker
from pauth.models import Artifact, Case, CaseFile, Run, RunEvent
from pauth.runtime import execute_run, intake_from_case, resume_run
from pauth.services.documents import guess_content_type

router = APIRouter(prefix="/api")
Session = Annotated[AsyncSession, Depends(get_session)]


def _now() -> datetime:
    """UTC now for run status timestamps."""
    return datetime.now(timezone.utc)


def _case_out(case: Case, files: list[CaseFile], runs: list[Run] | None = None) -> dict:
    """Serialize a case plus its latest run for the workbench list/detail views."""
    latest = None
    if runs:
        latest = max(runs, key=lambda item: item.created_at)
    return {
        "id": case.id,
        "patient_initials": case.patient_initials,
        "payer": case.payer,
        "plan": case.plan,
        "procedure": case.procedure,
        "cpt": case.cpt,
        "icd": case.icd,
        "urgency": case.urgency,
        "notes": case.notes,
        "created_at": case.created_at.isoformat(),
        "files": [
            {"id": item.id, "filename": item.filename, "content_type": item.content_type}
            for item in files
        ],
        "latest_run": _run_summary(latest) if latest else None,
    }


def _run_summary(run: Run) -> dict:
    """Compact run payload, including parsed HITL interrupt data when paused."""
    return {
        "id": run.id,
        "case_id": run.case_id,
        "status": run.status,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "interrupt": json.loads(run.interrupt_json) if run.interrupt_json else None,
    }


async def _files_for(session: AsyncSession, case_id: str) -> list[CaseFile]:
    """Load every uploaded file row for a case."""
    result = await session.exec(select(CaseFile).where(CaseFile.case_id == case_id))
    return list(result.all())


@router.get("/health")
async def health() -> dict:
    """Liveness plus whether OpenAI specialists are enabled (never the API key)."""
    return {
        "ok": True,
        "use_llm": settings.use_llm,
        "llm_model": settings.llm_model if settings.use_llm else None,
    }


@router.get("/cases")
async def list_cases(session: Session) -> dict:
    """Newest-first case list for the home screen."""
    cases = list((await session.exec(select(Case).order_by(col(Case.created_at).desc()))).all())
    payload = []
    for case in cases:
        files = await _files_for(session, case.id)
        runs = list((await session.exec(select(Run).where(Run.case_id == case.id))).all())
        payload.append(_case_out(case, files, runs))
    return {"cases": payload}


@router.post("/cases")
async def create_case(
    session: Session,
    request: Request,
    patient_initials: str = Form(...),
    payer: str = Form(...),
    plan: str = Form(""),
    procedure: str = Form(...),
    cpt: str = Form(""),
    icd: str = Form(""),
    urgency: str = Form("routine"),
    notes: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Create a case, store uploads, and start the graph without blocking the HTTP response."""
    case = Case(
        patient_initials=patient_initials.strip(),
        payer=payer.strip(),
        plan=plan.strip(),
        procedure=procedure.strip(),
        cpt=cpt.strip(),
        icd=icd.strip(),
        urgency=urgency.strip() or "routine",
        notes=notes,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    saved = await _save_uploads(session, case.id, files)
    run = Run(case_id=case.id, status="running")
    session.add(run)
    await session.commit()
    await session.refresh(run)
    graph = request.app.state.graph
    asyncio.create_task(
        _bg_execute(
            run_id=run.id,
            graph=graph,
            use_llm=settings.use_llm,
        )
    )
    return {
        "case": _case_out(case, saved, [run]),
        "run": _run_summary(run),
    }


@router.get("/cases/{case_id}")
async def get_case(case_id: str, session: Session) -> dict:
    """Single case with files and the most recent run."""
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    files = await _files_for(session, case.id)
    runs = list(
        (
            await session.exec(
                select(Run).where(Run.case_id == case.id).order_by(col(Run.created_at).desc())
            )
        ).all()
    )
    return _case_out(case, files, runs)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, session: Session) -> dict:
    """Full run snapshot: status, event history, and latest per-node artifacts."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    events = list(
        (
            await session.exec(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(col(RunEvent.ts))
            )
        ).all()
    )
    artifacts = list((await session.exec(select(Artifact).where(Artifact.run_id == run_id))).all())
    return {
        **_run_summary(run),
        "events": [_event_out(item) for item in events],
        "artifacts": [
            {
                "id": item.id,
                "node": item.node,
                "kind": item.kind,
                "data": json.loads(item.content_json),
                "updated_at": (item.updated_at or item.created_at).isoformat(),
            }
            for item in artifacts
        ],
    }


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str, session: Session) -> StreamingResponse:
    """SSE: replay stored events, then push live ones until a coordinator error."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    history = list(
        (
            await session.exec(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(col(RunEvent.ts))
            )
        ).all()
    )

    async def gen():
        """Yield historical events, then block on the in-process broker."""
        for item in history:
            yield _sse(_event_out(item))
        queue = broker.subscribe(run_id)
        try:
            while True:
                event = await queue.get()
                yield _sse(event)
                if event.get("type") == "error" and event.get("node") == "coordinator":
                    break
        finally:
            broker.unsubscribe(run_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops proxies from buffering the stream into one blob.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/resume")
async def resume(
    run_id: str,
    session: Session,
    request: Request,
    status: str = Form(...),
    notes: str = Form(""),
    payer_or_procedure_changed: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Resume a HITL interrupt: approve the packet or send the case back with notes/files."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status not in {"interrupted", "running"}:
        raise HTTPException(409, f"Run is {run.status}")
    case = await session.get(Case, run.case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    new_files = await _save_uploads(session, case.id, files)
    all_files = await _files_for(session, case.id)
    decision = {
        "status": status,
        "notes": notes,
        "payer_or_procedure_changed": payer_or_procedure_changed,
        "new_file_ids": [item.id for item in new_files],
    }
    run.status = "running"
    run.updated_at = _now()
    session.add(run)
    await session.commit()
    asyncio.create_task(
        _bg_resume(
            run_id=run.id,
            graph=request.app.state.graph,
            use_llm=settings.use_llm,
            decision=decision,
            intake=intake_from_case(case, all_files),
        )
    )
    return {"run": _run_summary(run)}


@router.get("/runs/{run_id}/packet")
async def packet(run_id: str, session: Session) -> dict:
    """Return the assembled letter JSON once the Assembler has written it."""
    artifact = (
        await session.exec(
            select(Artifact).where(
                Artifact.run_id == run_id,
                Artifact.node == "assembler",
                Artifact.kind == "packet",
            )
        )
    ).first()
    if artifact is None:
        raise HTTPException(404, "Packet not ready")
    return json.loads(artifact.content_json)


def _event_out(item: RunEvent) -> dict:
    """JSON shape consumed by the trace timeline and SSE clients."""
    return {
        "id": item.id,
        "run_id": item.run_id,
        "ts": item.ts.isoformat(),
        "node": item.node,
        "type": item.type,
        "payload": json.loads(item.payload_json or "{}"),
    }


def _sse(payload: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def _save_uploads(session: AsyncSession, case_id: str, files: list[UploadFile]) -> list[CaseFile]:
    """Persist multipart files to disk and insert `CaseFile` rows."""
    saved: list[CaseFile] = []
    for upload in files:
        if not upload.filename:
            continue
        dest_dir = settings.uploads_dir / case_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Prefix with a uuid so two uploads of the same filename do not clobber.
        dest = dest_dir / f"{uuid4().hex}-{Path(upload.filename).name}"
        content = await upload.read()
        dest.write_bytes(content)
        record = CaseFile(
            case_id=case_id,
            filename=upload.filename,
            path=str(dest),
            content_type=guess_content_type(
                upload.filename,
                upload.content_type or "",
                content,
            ),
        )
        session.add(record)
        saved.append(record)
    if saved:
        await session.commit()
        for record in saved:
            await session.refresh(record)
    return saved


async def _bg_execute(run_id: str, graph, use_llm: bool) -> None:
    """Background task: load the case and invoke the graph from START."""
    from pauth.db import SessionLocal

    async with SessionLocal() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        case = await session.get(Case, run.case_id)
        files = await _files_for(session, run.case_id)
        await execute_run(
            run=run,
            case=case,
            files=files,
            graph=graph,
            use_llm=use_llm,
            session=session,
        )


async def _bg_resume(run_id: str, graph, use_llm: bool, decision: dict, intake: dict) -> None:
    """Background task: continue a paused graph with the human's HITL payload."""
    from pauth.db import SessionLocal

    async with SessionLocal() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        await resume_run(
            run=run,
            graph=graph,
            use_llm=use_llm,
            session=session,
            decision=decision,
            intake=intake,
        )
