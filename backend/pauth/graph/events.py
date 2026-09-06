"""Run observability: persist events, upsert artifacts, fan them out over SSE."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from pauth.db import SessionLocal
from pauth.models import Artifact, RunEvent


class EventSink(Protocol):
    """Anything a graph node can emit through (DB, memory, tests)."""

    async def emit(self, node: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record one `start|token|artifact|end|error` event and return its JSON shape."""
        ...


class Broker:
    """In-process pub/sub so SSE handlers receive events as they are written."""

    def __init__(self) -> None:
        """Create an empty subscriber map keyed by run id."""
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Register a listener queue for one run's live events."""
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        """Drop a listener; remove the run key when nobody is watching."""
        listeners = self._queues.get(run_id)
        if not listeners:
            return
        if queue in listeners:
            listeners.remove(queue)
        if not listeners:
            self._queues.pop(run_id, None)

    async def publish(self, event: dict[str, Any]) -> None:
        """Push an event to every current subscriber of `event['run_id']`."""
        run_id = event.get("run_id")
        if not run_id:
            return
        for queue in list(self._queues.get(run_id, [])):
            await queue.put(event)


broker = Broker()


class DbEventSink:
    """Persist events to SQLite and mirror artifact payloads for the workbench."""

    def __init__(self, run_id: str, session_factory=SessionLocal) -> None:
        """Bind this sink to one run so nodes do not pass run_id on every emit."""
        self.run_id = run_id
        self._session_factory = session_factory

    async def emit(self, node: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Insert a `RunEvent`, upsert artifacts, then publish to SSE subscribers."""
        body = payload or {}
        event = RunEvent(
            run_id=self.run_id,
            node=node,
            type=event_type,
            payload_json=json.dumps(body, default=str),
        )
        async with self._session_factory() as session:
            session.add(event)
            if event_type == "artifact":
                await _upsert_artifact(session, self.run_id, node, body)
            await session.commit()
            await session.refresh(event)
        payload_out = {
            "id": event.id,
            "run_id": self.run_id,
            "ts": event.ts.isoformat(),
            "node": node,
            "type": event_type,
            "payload": body,
        }
        await broker.publish(payload_out)
        return payload_out


async def _upsert_artifact(session: AsyncSession, run_id: str, node: str, body: dict[str, Any]) -> None:
    """Keep one artifact row per (run, node, kind) so the UI always shows the latest."""
    kind = str(body.get("kind") or node)
    result = await session.exec(
        select(Artifact).where(Artifact.run_id == run_id, Artifact.node == node, Artifact.kind == kind)
    )
    existing = result.first()
    content = json.dumps(body.get("data", body), default=str)
    now = datetime.now(timezone.utc)
    if existing:
        existing.content_json = content
        existing.updated_at = now
        session.add(existing)
        return
    session.add(
        Artifact(
            run_id=run_id,
            node=node,
            kind=kind,
            content_json=content,
            updated_at=now,
        )
    )


async def emit(config: Any, node: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Helper for graph nodes: no-op if the run was started without an event_sink."""
    sink: EventSink | None = (config.get("configurable") or {}).get("event_sink")
    if sink is None:
        return
    await sink.emit(node, event_type, payload)


class MemorySink:
    """In-memory sink used by unit tests (no database)."""

    def __init__(self, run_id: str = "test") -> None:
        """Start an empty event list for `run_id`."""
        self.run_id = run_id
        self.events: list[dict[str, Any]] = []

    async def emit(self, node: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Append an event in the same JSON shape as `DbEventSink`."""
        event = {
            "id": str(len(self.events) + 1),
            "run_id": self.run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "type": event_type,
            "payload": payload or {},
        }
        self.events.append(event)
        return event
