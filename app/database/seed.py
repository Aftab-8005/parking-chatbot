from app.database.facilities import FACILITIES
from app.database.models import ParkingAvailability, Pricing, WorkingHours
from app.database.session import get_session, init_db

# Realistic-but-fictional demo values, deliberately distinct per facility so
# dynamic lookups (availability/price/hours) are visibly facility-specific.
_SEED_DATA = {
    "city_center": {
        "total_spaces": 100,
        "available_spaces": 37,
        "hourly_price": 2.0,
        "daily_price": 15.0,
        "opening_time": "06:00",
        "closing_time": "23:00",
        "note": "",
    },
    "airport": {
        "total_spaces": 220,
        "available_spaces": 54,
        "hourly_price": 3.5,
        "daily_price": 22.0,
        "opening_time": "00:00",
        "closing_time": "23:59",
        "note": "Open 24 hours to match flight schedules.",
    },
    "railway_station": {
        "total_spaces": 150,
        "available_spaces": 18,
        "hourly_price": 2.5,
        "daily_price": 18.0,
        "opening_time": "05:00",
        "closing_time": "00:30",
        "note": "Closes briefly overnight for cleaning.",
    },
    "mall": {
        "total_spaces": 300,
        "available_spaces": 120,
        "hourly_price": 1.5,
        "daily_price": 10.0,
        "opening_time": "09:00",
        "closing_time": "22:00",
        "note": "Matches mall opening hours.",
    },
}


def seed_dynamic_data() -> None:
    """Populate the dynamic-data tables with initial per-facility values if empty."""
    init_db()
    session = get_session()
    try:
        for facility in FACILITIES:
            data = _SEED_DATA[facility]
            if session.query(ParkingAvailability).filter_by(facility=facility).count() == 0:
                session.add(
                    ParkingAvailability(
                        facility=facility,
                        total_spaces=data["total_spaces"],
                        available_spaces=data["available_spaces"],
                    )
                )
            if session.query(Pricing).filter_by(facility=facility).count() == 0:
                session.add(
                    Pricing(
                        facility=facility,
                        hourly_price=data["hourly_price"],
                        daily_price=data["daily_price"],
                        currency="USD",
                    )
                )
            if session.query(WorkingHours).filter_by(facility=facility).count() == 0:
                session.add(
                    WorkingHours(
                        facility=facility,
                        opening_time=data["opening_time"],
                        closing_time=data["closing_time"],
                        note=data["note"],
                    )
                )
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    seed_dynamic_data()
    print("Dynamic data seeded.")
