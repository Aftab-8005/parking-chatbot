from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ParkingAvailability(Base):
    """Dynamic data: how many spaces exist / are currently free."""

    __tablename__ = "parking_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    total_spaces: Mapped[int] = mapped_column(Integer, nullable=False)
    available_spaces: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Pricing(Base):
    """Dynamic data: current pricing, can change independently of static docs."""

    __tablename__ = "pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hourly_price: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    daily_price: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class WorkingHours(Base):
    """Dynamic data: operating hours, can change (holidays, seasons, etc.)."""

    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opening_time: Mapped[str] = mapped_column(String(5), nullable=False)
    closing_time: Mapped[str] = mapped_column(String(5), nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="")


class Reservation(Base):
    """A reservation request collected by the chatbot.

    status progresses: collected -> pending_admin_approval -> approved/rejected
    (the admin workflow is implemented in Stage 2).
    """

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    car_number: Mapped[str] = mapped_column(String(20), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="collected")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
