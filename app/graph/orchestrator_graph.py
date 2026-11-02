"""Stage 4: LangGraph orchestration of the reservation-approval pipeline.

This graph is the "human-in-the-loop" continuation of a reservation that the
Stage-1 chatbot graph (`app/graph/chatbot_graph.py`) has already collected
from the user. It implements the three stages called out in the spec --
user interaction, administrator approval, data recording -- as:

    user_interaction -> notify_admin -> await_admin_decision -> data_recording | reject_reservation

START
  |
  v
user_interaction        (loads the reservation collected by the RAG chatbot)
  |
  v
notify_admin             (sends the approval-request notification)
  |
  v
await_admin_decision     (PAUSES via interrupt() until the admin posts a
  |                        decision through the REST API)
  v
 route_after_decision
  |-- approved --> data_recording      (writes the approved reservation to
  |                                      file via the Stage-3 MCP server)
  `-- rejected --> reject_reservation   (marks it rejected in the DB)

`notify_admin` and `await_admin_decision` are deliberately two separate
nodes: LangGraph re-runs a node containing `interrupt()` *from the start*
every time execution resumes, so any side effect (sending the notification,
writing to the DB) placed before the `interrupt()` call in the same node
would otherwise fire a second time on resume.

Because `await_admin_decision` calls `interrupt()`, a single
`graph.invoke(...)` that reaches it returns immediately (the admin may take
minutes or days to respond). The graph is resumed later -- from a completely
separate HTTP request, in `app/api/admin_routes.py` -- with
`graph.invoke(Command(resume=...), config=...)`, using the same `thread_id`
so the checkpointer restores exactly where execution paused.

The in-memory `MemorySaver` checkpointer is sufficient for this project's
scope (single process); a production deployment would swap it for a
persistent checkpointer (e.g. Postgres) so pending approvals survive a
restart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import admin_agent
from app.database import dynamic_service
from app.mcp_client.client import write_confirmed_reservation


class ApprovalState(TypedDict, total=False):
    reservation_id: int
    reservation: dict
    decision: str
    final_status: str
    recorded_line: str


def user_interaction(state: ApprovalState) -> ApprovalState:
    """Hand-off point from the RAG chatbot: the reservation's details were
    already collected interactively by `app.agents.reservation_agent` /
    `app.graph.chatbot_graph`. This node just loads the persisted record so
    the rest of the pipeline has it in-state."""
    reservation = dynamic_service.get_reservation(state["reservation_id"])
    if reservation is None:
        raise ValueError(f"Reservation #{state['reservation_id']} not found.")
    state["reservation"] = reservation
    return state


def notify_admin(state: ApprovalState) -> ApprovalState:
    """Send the approval-request notification. Kept in its own node, separate
    from `await_admin_decision`: LangGraph re-runs a node containing
    `interrupt()` *from the start* every time it resumes, so any side effect
    (sending an email, writing to the DB) placed before an `interrupt()` call
    in the same node would otherwise fire a second time on resume."""
    reservation = state["reservation"]
    admin_agent.request_approval(reservation)
    dynamic_service.update_reservation_status(reservation["id"], "pending_admin_approval")
    return state


def await_admin_decision(state: ApprovalState) -> ApprovalState:
    """Pause the pipeline until the administrator posts a decision via the
    REST API (`POST /admin/reservations/{id}/decision`), which resumes this
    exact point with `Command(resume={"decision": ...})`."""
    reservation = state["reservation"]
    resumed = interrupt({"type": "admin_decision_required", "reservation_id": reservation["id"]})
    state["decision"] = resumed["decision"]
    return state


def route_after_decision(state: ApprovalState) -> str:
    return "approved" if state["decision"] == "approved" else "rejected"


def data_recording(state: ApprovalState) -> ApprovalState:
    """Approved path: write the confirmed reservation to file via the MCP
    server and mark it as recorded in the DB."""
    reservation = state["reservation"]
    decided_at = datetime.now(timezone.utc)

    period = f"{reservation['start_time']} - {reservation['end_time']}"
    line = write_confirmed_reservation(
        name=f"{reservation['first_name']} {reservation['last_name']}",
        car_number=reservation["car_number"],
        period=period,
        approval_time=decided_at.isoformat(),
    )

    dynamic_service.update_reservation_status(reservation["id"], "recorded", decided_at=decided_at)
    state["final_status"] = "recorded"
    state["recorded_line"] = line
    return state


def reject_reservation(state: ApprovalState) -> ApprovalState:
    """Rejected path: mark the reservation as rejected, no file write."""
    reservation = state["reservation"]
    dynamic_service.update_reservation_status(
        reservation["id"], "rejected", decided_at=datetime.now(timezone.utc)
    )
    state["final_status"] = "rejected"
    return state


def build_graph():
    graph = StateGraph(ApprovalState)

    graph.add_node("user_interaction", user_interaction)
    graph.add_node("notify_admin", notify_admin)
    graph.add_node("await_admin_decision", await_admin_decision)
    graph.add_node("data_recording", data_recording)
    graph.add_node("reject_reservation", reject_reservation)

    graph.add_edge(START, "user_interaction")
    graph.add_edge("user_interaction", "notify_admin")
    graph.add_edge("notify_admin", "await_admin_decision")
    graph.add_conditional_edges(
        "await_admin_decision",
        route_after_decision,
        {"approved": "data_recording", "rejected": "reject_reservation"},
    )
    graph.add_edge("data_recording", END)
    graph.add_edge("reject_reservation", END)

    return graph.compile(checkpointer=MemorySaver())


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def thread_config(reservation_id: int) -> dict:
    return {"configurable": {"thread_id": f"reservation-{reservation_id}"}}


def start_approval_pipeline(reservation_id: int) -> dict:
    """Kick off the pipeline for a freshly collected reservation. Runs
    `user_interaction` + `admin_approval` (which sends the notification and
    then pauses) and returns immediately -- this does not block waiting for
    the admin.

    The returned dict includes `awaiting_admin_decision=True` when the graph
    is paused at the `interrupt()` in `admin_approval` (the expected outcome
    on a fresh reservation).
    """
    graph = get_compiled_graph()
    config = thread_config(reservation_id)
    result = graph.invoke({"reservation_id": reservation_id}, config=config)
    result["awaiting_admin_decision"] = bool(graph.get_state(config).next)
    return result


def resume_with_decision(reservation_id: int, decision: str) -> dict:
    """Resume a paused pipeline with the administrator's decision
    ('approved' or 'rejected'), completing the data-recording/rejection
    step.

    The `MemorySaver` checkpointer only lives in process memory, so if the
    app restarted since the reservation was escalated (or the pipeline
    somehow never started), there's no paused `interrupt()` to resume into
    and `Command(resume=...)` would fail. Self-heal by re-running
    `start_approval_pipeline` first to recreate that pause point -- the
    reservation is still `pending_admin_approval` in the DB either way, so
    this is a safe, idempotent recovery rather than a double-submission.
    """
    from langgraph.types import Command

    graph = get_compiled_graph()
    config = thread_config(reservation_id)

    if not graph.get_state(config).next:
        start_approval_pipeline(reservation_id)

    return graph.invoke(Command(resume={"decision": decision}), config=config)
