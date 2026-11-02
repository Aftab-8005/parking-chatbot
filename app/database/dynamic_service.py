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


def get_reservation(reservation_id: int) -> dict | None:
    session = get_session()
    try:
        row = session.get(Reservation, reservation_id)
        if row is None:
            return None
        return _reservation_to_dict(row)
    finally:
        session.close()


def list_pending_reservations() -> list[dict]:
    session = get_session()
    try:
        rows = (
            session.query(Reservation)
            .filter(Reservation.status == "pending_admin_approval")
            .order_by(Reservation.created_at.asc())
            .all()
        )
        return [_reservation_to_dict(row) for row in rows]
    finally:
        session.close()


def update_reservation_status(
    reservation_id: int, status: str, decided_at: datetime | None = None
) -> dict | None:
    session = get_session()
    try:
        row = session.get(Reservation, reservation_id)
        if row is None:
            return None
        row.status = status
        if decided_at is not None:
            row.decided_at = decided_at
        session.commit()
        return _reservation_to_dict(row)
    finally:
        session.close()


def _reservation_to_dict(row: Reservation) -> dict:
    return {
        "id": row.id,
        "first_name": row.first_name,
        "last_name": row.last_name,
        "car_number": row.car_number,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "status": row.status,
        "created_at": row.created_at,
        "decided_at": row.decided_at,
    }
