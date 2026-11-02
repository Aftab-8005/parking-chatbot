from app.database.models import ParkingAvailability, Pricing, WorkingHours
from app.database.session import get_session, init_db


def seed_dynamic_data() -> None:
    """Populate the dynamic-data tables with initial values if empty."""
    init_db()
    session = get_session()
    try:
        if session.query(ParkingAvailability).count() == 0:
            session.add(ParkingAvailability(total_spaces=100, available_spaces=37))
        if session.query(Pricing).count() == 0:
            session.add(Pricing(hourly_price=2.0, daily_price=15.0, currency="USD"))
        if session.query(WorkingHours).count() == 0:
            session.add(WorkingHours(opening_time="06:00", closing_time="23:00"))
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    seed_dynamic_data()
    print("Dynamic data seeded.")
