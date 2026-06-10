from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./memory_gateway.db"
    admin_key: str = "admin-demo-key"
    backend_key: str = "backend-demo-key"
    guest_key: str = "guest-demo-key"
    graph_enabled: bool = True
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "memorypassword"
    neo4j_database: str = "neo4j"
    cors_origins: str = (
        "http://127.0.0.1:1420,"
        "http://localhost:1420,"
        "http://tauri.localhost,"
        "tauri://localhost"
    )
    cors_origin_regex: str = r"^https?://(127\.0\.0\.1|localhost):\d+$"

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MEMORY_GATEWAY_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
