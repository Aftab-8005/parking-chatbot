from fastapi import APIRouter

from app.api.schemas import ChatRequest, ChatResponse
from app.graph.chatbot_graph import get_compiled_graph
from app.graph.state import new_state

router = APIRouter()

# In-memory per-session conversation state (Stage 1 scope). A production
# deployment would back this with Redis/Postgres keyed by session_id.
_sessions: dict[str, dict] = {}


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    previous = _sessions.get(request.session_id, {})
    state = new_state(request.message, previous=previous)

    graph = get_compiled_graph()
    result = graph.invoke(state)

    _sessions[request.session_id] = {
        "reservation_slots": result.get("reservation_slots", {}),
        "reservation_in_progress": result.get("reservation_in_progress", False),
    }

    return ChatResponse(
        session_id=request.session_id,
        response=result["response"],
        intent=result["intent"],
    )
