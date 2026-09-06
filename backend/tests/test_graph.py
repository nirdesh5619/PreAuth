import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from pauth.graph.builder import build_graph
from pauth.graph.events import MemorySink
from pauth.services.policies import retrieve_policy


def _intake(**overrides):
    """RA/infliximab demo intake used by graph tests."""
    base = {
        "patient_initials": "A.R.",
        "payer": "Aetna",
        "plan": "PPO",
        "procedure": "Infliximab infusion",
        "cpt": "J1745",
        "icd": "M05.9",
        "urgency": "routine",
        "notes": (
            "54yo with moderately to severely active rheumatoid arthritis. "
            "Failed 16 weeks of methotrexate. IGRA negative 2 months ago. "
            "No active infection. Requesting infliximab 3 mg/kg."
        ),
        "files": [],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_policy_retrieval_prefers_cpt():
    """J1745 should beat a generic payer match and return the infliximab fixture."""
    policy = retrieve_policy("Aetna", "Infliximab", "J1745")
    assert policy.policy_id == "aetna-j1745-infliximab"
    assert len(policy.items) >= 4


@pytest.mark.asyncio
async def test_graph_fans_in_then_interrupts():
    """All three specialists should finish before the graph parks on HITL."""
    sink = MemorySink("run-1")
    graph = build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "run-1", "event_sink": sink, "use_llm": False}}
    await graph.ainvoke(
        {"case_id": "c1", "run_id": "run-1", "intake": _intake(), "tick": 0},
        config,
    )
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("hitl",)
    nodes = {event["node"] for event in sink.events if event["type"] == "end"}
    assert {"coordinator", "document", "clinical", "policy", "matcher"} <= nodes
    assert snapshot.values["match_result"]["items"]
    assert any(event["type"] == "artifact" and event["node"] == "hitl" for event in sink.events)


@pytest.mark.asyncio
async def test_hitl_approve_assembles_packet():
    """Approving HITL should compile through Assembler and leave a markdown packet."""
    sink = MemorySink("run-2")
    graph = build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "run-2", "event_sink": sink, "use_llm": False}}
    await graph.ainvoke(
        {"case_id": "c2", "run_id": "run-2", "intake": _intake(), "tick": 0},
        config,
    )
    await graph.ainvoke(
        Command(resume={"status": "approved", "notes": "Looks complete.", "new_file_ids": []}),
        config,
    )
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ()
    packet = snapshot.values["packet"]
    assert "Letter of medical necessity" in packet["markdown"]
    assert snapshot.values["hitl"]["status"] == "approved"


@pytest.mark.asyncio
async def test_hitl_changes_reruns_specialists():
    """Sending a case back should fan out again and interrupt a second time."""
    sink = MemorySink("run-3")
    graph = build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "run-3", "event_sink": sink, "use_llm": False}}
    await graph.ainvoke(
        {"case_id": "c3", "run_id": "run-3", "intake": _intake(), "tick": 0},
        config,
    )
    first_coord = [event for event in sink.events if event["node"] == "coordinator" and event["type"] == "end"]
    await graph.ainvoke(
        Command(
            resume={
                "status": "changes",
                "notes": "Please note oral iron trial.",
                "payer_or_procedure_changed": False,
                "new_file_ids": [],
            },
            update={
                "intake": _intake(
                    notes=(
                        "54yo RA, failed methotrexate. IGRA negative. "
                        "Also failed oral iron for unrelated anemia. No infection."
                    )
                )
            },
        ),
        config,
    )
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("hitl",)
    coord_ends = [event for event in sink.events if event["node"] == "coordinator" and event["type"] == "end"]
    assert len(coord_ends) > len(first_coord)
    matcher_ends = [event for event in sink.events if event["node"] == "matcher" and event["type"] == "end"]
    assert len(matcher_ends) >= 2
