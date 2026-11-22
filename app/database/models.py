from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.database.facilities import DEFAULT_FACILITY


class Base(DeclarativeBase):
    pass


class ParkingAvailability(Base):
    """Dynamic data: how many spaces exist / are currently free, per facility."""

    __tablename__ = "parking_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility: Mapped[str] = mapped_column(String(50), default=DEFAULT_FACILITY, index=True)
    total_spaces: Mapped[int] = mapped_column(Integer, nullable=False)
    available_spaces: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Pricing(Base):
    """Dynamic data: current pricing per facility, can change independently of static docs."""

    __tablename__ = "pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility: Mapped[str] = mapped_column(String(50), default=DEFAULT_FACILITY, index=True)
    hourly_price: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    daily_price: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class WorkingHours(Base):
    """Dynamic data: operating hours per facility, can change (holidays, seasons, etc.)."""

    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility: Mapped[str] = mapped_column(String(50), default=DEFAULT_FACILITY, index=True)
    opening_time: Mapped[str] = mapped_column(String(5), nullable=False)
    closing_time: Mapped[str] = mapped_column(String(5), nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="")


class Reservation(Base):
    """A reservation request collected by the chatbot.

    status progresses:
      collected -> pending_admin_approval -> approved -> stored
                                           -> approved_pending_storage (MCP was down, retry later)
                                           \\-> rejected
    """

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    facility: Mapped[str] = mapped_column(String(50), default=DEFAULT_FACILITY, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    car_number: Mapped[str] = mapped_column(String(20), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="collected", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AdminRequest(Base):
    """A pending/decided approval request routed to the administrator.

    One row per reservation submitted for human-in-the-loop review. `request_id`
    is the public reference shown to both the user and the admin dashboard.
    """

    __tablename__ = "admin_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    reservation_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    admin_response: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
