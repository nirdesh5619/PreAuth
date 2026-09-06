"""Compile the prior-auth StateGraph: fan-out specialists, then HITL, then packet."""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Checkpointer

from pauth.agents import assembler, clinical, coordinator, document, hitl, matcher, policy
from pauth.graph.state import PauthState


def _after_hitl(state: PauthState) -> str:
    """Route to Assembler on approve; otherwise loop back to the coordinator."""
    decision = (state.get("hitl") or {}).get("status")
    if decision == "approved":
        return "assembler"
    return "coordinator"


def build_graph(checkpointer: Checkpointer | None = None):
    """Wire coordinator → (document, clinical, policy) → matcher → hitl → assembler.

    Three edges into `matcher` make LangGraph wait for all three specialists
    before scoring. HITL uses `interrupt()` inside the node, not `interrupt_before`.
    """
    graph = StateGraph(PauthState)
    graph.add_node("coordinator", coordinator)
    graph.add_node("document", document)
    graph.add_node("clinical", clinical)
    graph.add_node("policy", policy)
    graph.add_node("matcher", matcher)
    graph.add_node("hitl", hitl)
    graph.add_node("assembler", assembler)

    graph.add_edge(START, "coordinator")
    graph.add_edge("coordinator", "document")
    graph.add_edge("coordinator", "clinical")
    graph.add_edge("coordinator", "policy")
    graph.add_edge("document", "matcher")
    graph.add_edge("clinical", "matcher")
    graph.add_edge("policy", "matcher")
    graph.add_edge("matcher", "hitl")
    graph.add_conditional_edges(
        "hitl",
        _after_hitl,
        {"assembler": "assembler", "coordinator": "coordinator"},
    )
    graph.add_edge("assembler", END)
    return graph.compile(checkpointer=checkpointer)
