from datetime import datetime

from app.database.models import ParkingAvailability, Pricing, Reservation, WorkingHours
from app.database.session import get_session


def get_availability() -> dict:
    session = get_session()
    try:
        row = session.query(ParkingAvailability).order_by(ParkingAvailability.id.desc()).first()
        if row is None:
            return {"total_spaces": None, "available_spaces": None}
        return {"total_spaces": row.total_spaces, "available_spaces": row.available_spaces}
    finally:
        session.close()


def get_pricing() -> dict:
    session = get_session()
    try:
        row = session.query(Pricing).order_by(Pricing.id.desc()).first()
        if row is None:
            return {"hourly_price": None, "daily_price": None, "currency": None}
        return {
            "hourly_price": float(row.hourly_price),
            "daily_price": float(row.daily_price),
            "currency": row.currency,
        }
    finally:
        session.close()


def get_working_hours() -> dict:
    session = get_session()
    try:
        row = session.query(WorkingHours).order_by(WorkingHours.id.desc()).first()
        if row is None:
            return {"opening_time": None, "closing_time": None}
        return {"opening_time": row.opening_time, "closing_time": row.closing_time}
    finally:
        session.close()


def create_reservation(
    first_name: str,
    last_name: str,
    car_number: str,
    start_time: datetime,
    end_time: datetime,
    status: str = "collected",
) -> int:
    session = get_session()
    try:
        reservation = Reservation(
            first_name=first_name,
            last_name=last_name,
            car_number=car_number,
            start_time=start_time,
            end_time=end_time,
            status=status,
        )
        session.add(reservation)
        session.commit()
        return reservation.id
    finally:
        session.close()
