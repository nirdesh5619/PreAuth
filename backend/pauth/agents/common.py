"""Shared helpers for specialist nodes."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from pauth.graph.events import emit


def use_llm(config: RunnableConfig) -> bool:
    """Whether this run should call OpenAI (`configurable.use_llm` from the API)."""
    return bool((config.get("configurable") or {}).get("use_llm"))


async def emit_event(
    config: RunnableConfig,
    node: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Forward an observability event to the run's event sink."""
    await emit(config, node, event_type, payload)
