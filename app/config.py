from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Parking Reservation Chatbot"
    app_env: str = "development"

    # LLM / embeddings provider: EPAM DIAL proxy, accessed via the Azure OpenAI SDK.
    dial_api_key: str = ""
    dial_endpoint: str = "https://ai-proxy.lab.epam.com"
    dial_api_version: str = "2025-04-01-preview"
    dial_chat_deployment: str = "gpt-6-luna-2026-09-22"
    dial_embedding_deployment: str = "text-embedding-3-small-1"
    llm_request_timeout_seconds: float = 12.0

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "parking_knowledge"

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "parking_db"
    postgres_user: str = "parking_user"
    postgres_password: str = "parking_pass"

    mcp_host: str = "localhost"
    mcp_port: int = 8010
    mcp_auth_token: str = "change-me-mcp-token"
    mcp_request_timeout_seconds: float = 5.0

    admin_email: str = ""

    checkpoint_db_path: str = "data/state/checkpoints.sqlite"
    reservations_file_path: str = "data/reservations/confirmed_reservations.txt"

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def mcp_url(self) -> str:
        return f"http://{self.mcp_host}:{self.mcp_port}/mcp"


settings = Settings()
