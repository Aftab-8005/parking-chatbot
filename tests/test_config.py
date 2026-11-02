from app.config import Settings


def test_default_app_name():
    settings = Settings(_env_file=None)
    assert settings.app_name == "Parking Reservation Chatbot"


def test_postgres_url_is_built_from_parts():
    settings = Settings(
        _env_file=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )
    assert settings.postgres_url == "postgresql+psycopg2://u:p@h:1234/d"
