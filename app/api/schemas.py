from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: str
    response: str
    intent: str
    request_id: str | None = None
    reservation_status: str | None = None


class ReservationStatusResponse(BaseModel):
    request_id: str
    reservation_status: str | None
    admin_status: str
    first_name: str | None
    last_name: str | None
    car_number: str | None
    start_time: datetime | None
    end_time: datetime | None
    created_at: datetime
    responded_at: datetime | None
    facility: str | None = None


class AdminRequestOut(BaseModel):
    request_id: str
    status: str
    admin_response: str
    created_at: datetime
    responded_at: datetime | None
    reservation_id: int
    session_id: str | None
    first_name: str | None
    last_name: str | None
    car_number: str | None
    start_time: datetime | None
    end_time: datetime | None
    reservation_status: str | None
    facility: str | None = None


class AdminDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    admin_response: str = Field(default="", max_length=255)


class AdminDecisionResponse(BaseModel):
    request_id: str
    status: str
    reservation_status: str | None
    user_message: str | None = None
