import uuid
from datetime import datetime

from app.database.facilities import DEFAULT_FACILITY, facility_name
from app.database.models import AdminRequest, ParkingAvailability, Pricing, Reservation, WorkingHours
from app.database.session import get_session


def get_availability(facility: str | None = None) -> dict:
    session = get_session()
    try:
        query = session.query(ParkingAvailability)
        if facility:
            query = query.filter_by(facility=facility)
        row = query.order_by(ParkingAvailability.id.desc()).first()
        if row is None:
            return {"total_spaces": None, "available_spaces": None}
        return {"total_spaces": row.total_spaces, "available_spaces": row.available_spaces}
    finally:
        session.close()


def get_pricing(facility: str | None = None) -> dict:
    session = get_session()
    try:
        query = session.query(Pricing)
        if facility:
            query = query.filter_by(facility=facility)
        row = query.order_by(Pricing.id.desc()).first()
        if row is None:
            return {"hourly_price": None, "daily_price": None, "currency": None}
        return {
            "hourly_price": float(row.hourly_price),
            "daily_price": float(row.daily_price),
            "currency": row.currency,
        }
    finally:
        session.close()


def get_working_hours(facility: str | None = None) -> dict:
    session = get_session()
    try:
        query = session.query(WorkingHours)
        if facility:
            query = query.filter_by(facility=facility)
        row = query.order_by(WorkingHours.id.desc()).first()
        if row is None:
            return {"opening_time": None, "closing_time": None}
        return {"opening_time": row.opening_time, "closing_time": row.closing_time}
    finally:
        session.close()


def create_reservation(
    session_id: str,
    first_name: str,
    last_name: str,
    car_number: str,
    start_time: datetime,
    end_time: datetime,
    status: str = "collected",
    facility: str = DEFAULT_FACILITY,
) -> int:
    session = get_session()
    try:
        reservation = Reservation(
            session_id=session_id,
            first_name=first_name,
            last_name=last_name,
            car_number=car_number,
            start_time=start_time,
            end_time=end_time,
            status=status,
            facility=facility,
        )
        session.add(reservation)
        session.commit()
        return reservation.id
    finally:
        session.close()


_ACTIVE_STATUSES = ("collected", "pending_admin_approval", "approved", "approved_pending_storage", "stored")


def find_conflicting_reservation(car_number: str, start_time: datetime, end_time: datetime) -> dict | None:
    """Return an existing active (not rejected) reservation for the same car
    whose time window overlaps [start_time, end_time), or None if there's no
    conflict. Used to stop the same car being double-booked for an overlapping
    slot while an earlier request for it is still pending/approved."""
    session = get_session()
    try:
        candidates = (
            session.query(Reservation)
            .filter(
                Reservation.car_number == car_number,
                Reservation.status.in_(_ACTIVE_STATUSES),
                Reservation.start_time < end_time,
                Reservation.end_time > start_time,
            )
            .first()
        )
        if candidates is None:
            return None
        return {
            "id": candidates.id,
            "status": candidates.status,
            "start_time": candidates.start_time,
            "end_time": candidates.end_time,
        }
    finally:
        session.close()


def get_reservation(reservation_id: int) -> Reservation | None:
    session = get_session()
    try:
        return session.get(Reservation, reservation_id)
    finally:
        session.close()


def create_admin_request(reservation_id: int) -> str:
    """Create a pending admin-approval request for a reservation and return its request_id."""
    request_id = str(uuid.uuid4())
    session = get_session()
    try:
        session.add(AdminRequest(request_id=request_id, reservation_id=reservation_id, status="pending"))
        reservation = session.get(Reservation, reservation_id)
        if reservation is not None:
            reservation.status = "pending_admin_approval"
        session.commit()
        return request_id
    finally:
        session.close()


def get_admin_request(request_id: str) -> dict | None:
    session = get_session()
    try:
        admin_request = session.query(AdminRequest).filter_by(request_id=request_id).first()
        if admin_request is None:
            return None
        reservation = session.get(Reservation, admin_request.reservation_id)
        return _admin_request_to_dict(admin_request, reservation)
    finally:
        session.close()


def list_admin_requests(status: str | None = None) -> list[dict]:
    session = get_session()
    try:
        query = session.query(AdminRequest)
        if status:
            query = query.filter_by(status=status)
        results = []
        for admin_request in query.order_by(AdminRequest.created_at.desc()).all():
            reservation = session.get(Reservation, admin_request.reservation_id)
            results.append(_admin_request_to_dict(admin_request, reservation))
        return results
    finally:
        session.close()


def _admin_request_to_dict(admin_request: AdminRequest, reservation: Reservation | None) -> dict:
    return {
        "request_id": admin_request.request_id,
        "status": admin_request.status,
        "admin_response": admin_request.admin_response,
        "created_at": admin_request.created_at,
        "responded_at": admin_request.responded_at,
        "reservation_id": admin_request.reservation_id,
        "session_id": reservation.session_id if reservation else None,
        "first_name": reservation.first_name if reservation else None,
        "last_name": reservation.last_name if reservation else None,
        "car_number": reservation.car_number if reservation else None,
        "start_time": reservation.start_time if reservation else None,
        "end_time": reservation.end_time if reservation else None,
        "reservation_status": reservation.status if reservation else None,
        "facility": facility_name(reservation.facility) if reservation else None,
    }


def record_admin_decision(request_id: str, decision: str, admin_response: str = "") -> tuple[dict, bool] | None:
    """Persist the administrator's approve/reject decision.

    Returns (record, changed) where `changed` is False if the request had
    already been decided previously (idempotent re-submission), or None if
    `request_id` is unknown.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError(f"Invalid decision: {decision!r}")

    session = get_session()
    try:
        admin_request = session.query(AdminRequest).filter_by(request_id=request_id).first()
        if admin_request is None:
            return None
        if admin_request.status != "pending":
            reservation = session.get(Reservation, admin_request.reservation_id)
            return _admin_request_to_dict(admin_request, reservation), False

        now = datetime.utcnow()
        admin_request.status = decision
        admin_request.admin_response = admin_response
        admin_request.responded_at = now

        reservation = session.get(Reservation, admin_request.reservation_id)
        if reservation is not None:
            reservation.status = decision
            if decision == "approved":
                reservation.approved_at = now
            else:
                reservation.rejected_at = now

        session.commit()
        return _admin_request_to_dict(admin_request, reservation), True
    finally:
        session.close()


def find_admin_request_by_reference(reference: str) -> dict | None:
    """Look up an admin request by the short reference number shown to users
    (the first 8 characters of `request_id`), accepting either `#abcd1234` or
    bare `abcd1234` form."""
    reference = reference.lstrip("#").strip().lower()
    if not reference:
        return None
    session = get_session()
    try:
        admin_request = (
            session.query(AdminRequest)
            .filter(AdminRequest.request_id.like(f"{reference}%"))
            .first()
        )
        if admin_request is None:
            return None
        reservation = session.get(Reservation, admin_request.reservation_id)
        return _admin_request_to_dict(admin_request, reservation)
    finally:
        session.close()


def mark_reservation_stored(reservation_id: int) -> None:
    session = get_session()
    try:
        reservation = session.get(Reservation, reservation_id)
        if reservation is not None:
            reservation.status = "stored"
            reservation.stored_at = datetime.utcnow()
            session.commit()
    finally:
        session.close()


def mark_reservation_pending_storage(reservation_id: int) -> None:
    session = get_session()
    try:
        reservation = session.get(Reservation, reservation_id)
        if reservation is not None:
            reservation.status = "approved_pending_storage"
            session.commit()
    finally:
        session.close()
