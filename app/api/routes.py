import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import ChatRequest, ChatResponse, ReservationStatusResponse
from app.database import dynamic_service
from app.graph.chatbot_graph import get_compiled_graph
from app.security.guardrails import validate_user_message

logger = logging.getLogger("parking_chatbot.api")

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    is_valid, rejection_reason = validate_user_message(request.message)
    if not is_valid:
        return ChatResponse(session_id=request.session_id, response=rejection_reason, intent="blocked")

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": request.session_id}}

    try:
        result = graph.invoke({"user_message": request.message}, config=config)
    except Exception:
        logger.exception("Chat graph invocation failed for session %s", request.session_id)
        raise HTTPException(status_code=502, detail="The chatbot is temporarily unavailable. Please try again.")

    return ChatResponse(
        session_id=request.session_id,
        response=result["response"],
        intent=result["intent"],
        request_id=result.get("request_id"),
        reservation_status=result.get("reservation_status"),
    )


@router.get("/reservations/{request_id}", response_model=ReservationStatusResponse)
def get_reservation_status(request_id: str) -> ReservationStatusResponse:
    record = dynamic_service.get_admin_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown reservation reference.")

    return ReservationStatusResponse(
        request_id=record["request_id"],
        reservation_status=record["reservation_status"],
        admin_status=record["status"],
        first_name=record["first_name"],
        last_name=record["last_name"],
        car_number=record["car_number"],
        start_time=record["start_time"],
        end_time=record["end_time"],
        created_at=record["created_at"],
        responded_at=record["responded_at"],
        facility=record.get("facility"),
    )
