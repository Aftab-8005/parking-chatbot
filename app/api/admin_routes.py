"""Administrator API (Stage 2): list pending/decided requests and record a decision.

Deliberately separate from the user-facing chat/reservation routes so the two
surfaces (end-user vs. administrator) can be reasoned about, deployed, and
secured independently.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import AdminDecisionRequest, AdminDecisionResponse, AdminRequestOut
from app.database import dynamic_service
from app.graph.chatbot_graph import resume_with_admin_decision, retry_mcp_storage

logger = logging.getLogger("parking_chatbot.admin_api")

router = APIRouter(prefix="/admin")


@router.get("/requests", response_model=list[AdminRequestOut])
def list_requests(status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$")) -> list[dict]:
    return dynamic_service.list_admin_requests(status=status)


@router.get("/requests/{request_id}", response_model=AdminRequestOut)
def get_request(request_id: str) -> dict:
    record = dynamic_service.get_admin_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown request id.")
    return record


@router.post("/requests/{request_id}/decision", response_model=AdminDecisionResponse)
def decide_request(request_id: str, body: AdminDecisionRequest) -> AdminDecisionResponse:
    outcome = dynamic_service.record_admin_decision(request_id, body.decision, body.admin_response)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Unknown request id.")

    record, changed = outcome
    user_message = None

    if not changed:
        # Already decided earlier -- idempotent response, no graph resume.
        return AdminDecisionResponse(
            request_id=record["request_id"],
            status=record["status"],
            reservation_status=record["reservation_status"],
            user_message="This request was already decided; no action taken.",
        )

    session_id = record.get("session_id")
    if session_id:
        try:
            resumed_state = resume_with_admin_decision(session_id, body.decision)
            user_message = resumed_state.get("response")
        except Exception:
            logger.exception("Failed to resume chat graph for request %s after admin decision", request_id)
            user_message = (
                "Decision recorded, but the user-facing chatbot could not be notified automatically."
            )
    else:
        logger.warning("Admin request %s has no linked session_id; cannot resume chat graph.", request_id)

    final_record = dynamic_service.get_admin_request(request_id)
    return AdminDecisionResponse(
        request_id=final_record["request_id"],
        status=final_record["status"],
        reservation_status=final_record["reservation_status"],
        user_message=user_message,
    )


@router.post("/requests/{request_id}/retry-storage", response_model=AdminDecisionResponse)
def retry_storage(request_id: str) -> AdminDecisionResponse:
    """Manually retry MCP storage for a request stuck in
    `approved_pending_storage` (Stage 3 fallback: approvals are never lost,
    and can be retried once the MCP server is back up)."""
    record = dynamic_service.get_admin_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown request id.")
    if record["reservation_status"] != "approved_pending_storage":
        raise HTTPException(
            status_code=409,
            detail=f"Request is not pending storage (status={record['reservation_status']}).",
        )

    status, message = retry_mcp_storage(request_id)
    return AdminDecisionResponse(
        request_id=request_id,
        status=record["status"],
        reservation_status=status,
        user_message=message,
    )
