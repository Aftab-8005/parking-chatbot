from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Parking Reservation Chatbot"
    app_env: str = "development"

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "parking_knowledge"

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "parking_db"
    postgres_user: str = "parking_user"
    postgres_password: str = "parking_pass"

    mcp_host: str = "localhost"
    mcp_port: int = 8001
    mcp_api_key: str = "dev-mcp-shared-secret"

    admin_email: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "parking-bot@example.com"
    smtp_use_tls: bool = True

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def mcp_base_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}"


settings = Settings()
