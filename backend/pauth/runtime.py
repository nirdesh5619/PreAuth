"""Run and resume the compiled LangGraph, keeping `Run` rows in sync."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from pauth.graph.events import DbEventSink
from pauth.models import Artifact, Case, CaseFile, Run
from pauth.schemas import Intake, IntakeFile


def _now() -> datetime:
    """UTC timestamp for run status updates."""
    return datetime.now(timezone.utc)


def intake_from_case(case: Case, files: list[CaseFile]) -> dict[str, Any]:
    """Build the graph `intake` dict, including filesystem paths agents can read."""
    return Intake(
        patient_initials=case.patient_initials,
        payer=case.payer,
        plan=case.plan,
        procedure=case.procedure,
        cpt=case.cpt,
        icd=case.icd,
        urgency=case.urgency,
        notes=case.notes,
        files=[
            IntakeFile(
                id=item.id,
                filename=item.filename,
                path=item.path,
                content_type=item.content_type,
            )
            for item in files
        ],
    ).model_dump()


async def execute_run(
    *,
    run: Run,
    case: Case,
    files: list[CaseFile],
    graph,
    use_llm: bool,
    session: AsyncSession,
) -> None:
    """Invoke the graph from the start until HITL interrupt or completion."""
    sink = DbEventSink(run.id)
    config = {
        "configurable": {
            # Same id as the Run row so resume can find the checkpoint.
            "thread_id": run.id,
            "event_sink": sink,
            "use_llm": use_llm,
        }
    }
    initial = {
        "case_id": case.id,
        "run_id": run.id,
        "intake": intake_from_case(case, files),
        "tick": 0,
    }
    try:
        await graph.ainvoke(initial, config)
        await _refresh_run_status(session, run, graph, config)
    except Exception as exc:
        run.status = "error"
        run.error = str(exc)
        run.updated_at = _now()
        session.add(run)
        await session.commit()
        await sink.emit("coordinator", "error", {"message": str(exc)})


async def resume_run(
    *,
    run: Run,
    graph,
    use_llm: bool,
    session: AsyncSession,
    decision: dict[str, Any],
    intake: dict[str, Any] | None = None,
) -> None:
    """Continue after HITL. `Command.resume` unblocks `interrupt()` in the hitl node."""
    sink = DbEventSink(run.id)
    config = {
        "configurable": {
            "thread_id": run.id,
            "event_sink": sink,
            "use_llm": use_llm,
        }
    }
    update: dict[str, Any] = {}
    if intake is not None:
        update["intake"] = intake
    command = Command(resume=decision, update=update) if update else Command(resume=decision)
    try:
        await graph.ainvoke(command, config)
        await _refresh_run_status(session, run, graph, config)
    except Exception as exc:
        run.status = "error"
        run.error = str(exc)
        run.updated_at = _now()
        session.add(run)
        await session.commit()
        await sink.emit("hitl", "error", {"message": str(exc)})


async def _refresh_run_status(session: AsyncSession, run: Run, graph, config: dict) -> None:
    """Set running/interrupted/completed from the checkpoint and persist the packet."""
    snapshot = await graph.aget_state(config)
    run.updated_at = _now()
    if snapshot.next:
        # Non-empty `next` means the graph is parked on HITL, not finished.
        run.status = "interrupted"
        payload = _interrupt_payload(snapshot)
        run.interrupt_json = json.dumps(payload, default=str)
    else:
        run.status = "completed"
        run.interrupt_json = ""
        values = snapshot.values or {}
        if values.get("packet"):
            existing = (
                await session.exec(
                    select(Artifact).where(
                        Artifact.run_id == run.id,
                        Artifact.node == "assembler",
                        Artifact.kind == "packet",
                    )
                )
            ).first()
            content = json.dumps(values["packet"], default=str)
            if existing:
                existing.content_json = content
                existing.updated_at = _now()
                session.add(existing)
            else:
                session.add(
                    Artifact(
                        run_id=run.id,
                        node="assembler",
                        kind="packet",
                        content_json=content,
                    )
                )
    session.add(run)
    await session.commit()


def _interrupt_payload(snapshot) -> dict[str, Any]:
    """Read the value passed to `interrupt()` from LangGraph task metadata."""
    tasks = getattr(snapshot, "tasks", None) or ()
    for task in tasks:
        interrupts = getattr(task, "interrupts", None) or ()
        for item in interrupts:
            value = getattr(item, "value", item)
            if isinstance(value, dict):
                return value
    values = snapshot.values or {}
    return values.get("match_result") or {}
