"""Runtime configuration. Every value is environment-driven so the same image
runs unchanged from a laptop docker-compose to a managed cloud deployment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "State Machine Governance"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://grc:grc@db:5432/grc"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 12 * 60

    cors_origins: str = "http://localhost:8080,http://localhost:5173"

    # Seeds a demo dataset on first boot. Never enable outside development.
    seed_demo_data: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
