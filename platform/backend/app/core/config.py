"""Runtime configuration. Every value is environment-driven so the same image
runs unchanged from a laptop docker-compose to a managed cloud deployment."""

import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Secrets that ship in this repository. None of them may protect a deployment
# that is not explicitly marked as development.
SHIPPED_SECRETS = frozenset(
    {"", "change-me-in-production", "dev-secret-change-me", "changeme", "secret"}
)


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

    @property
    def is_development(self) -> bool:
        return self.environment.strip().lower() in ("development", "dev", "local")

    @model_validator(mode="after")
    def _refuse_shipped_defaults_outside_development(self) -> "Settings":
        """Refuse to start on a secret that is published in this repository.

        This platform's own argument is that a policy describes intent and a
        specification enforces it. Telling operators in the README to change the
        JWT secret is a policy. Refusing to boot without it is the enforcement,
        and the same reasoning that makes `governance.py` reject an invalid
        appetite model applies here: a deployment protected by a secret anyone
        can read from GitHub is a defect, not a configuration choice.

        Development is the one place the defaults are useful, so they warn there
        rather than fail.
        """
        problems: list[str] = []

        if self.jwt_secret.strip().lower() in SHIPPED_SECRETS:
            problems.append(
                "JWT_SECRET is still the value shipped in this repository. Anyone "
                "who can read the repo can forge a token for any role. Generate "
                "one with: openssl rand -hex 32"
            )
        if self.seed_demo_data:
            problems.append(
                "SEED_DEMO_DATA is true. The demo dataset ships a published "
                "password and an account holding the Admin role. Set it to false."
            )
        if "*" in self.cors_origin_list:
            problems.append(
                "CORS_ORIGINS contains a wildcard. Name the origins the UI is "
                "actually served from."
            )

        if not problems:
            return self

        if self.is_development:
            for problem in problems:
                logger.warning("insecure default in use (development): %s", problem)
            return self

        raise ValueError(
            "refusing to start in environment '"
            + self.environment
            + "' with insecure defaults:\n  - "
            + "\n  - ".join(problems)
            + "\n\nSet ENVIRONMENT=development to run with these locally."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
