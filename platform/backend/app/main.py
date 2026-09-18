"""Application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import SHIPPED_SECRETS, settings
from app.core.errors import DomainError
from app.db_init import bootstrap

# Importing the modules registers their invariants and cascade handlers.
from app.modules import cascades as _cascades  # noqa: F401
from app.modules.compliance import invariants as _compliance_invariants  # noqa: F401
from app.modules.compliance import router as compliance_router
from app.modules.control import invariants as _control_invariants  # noqa: F401
from app.modules.control import router as control_router
from app.modules.dashboard import router as dashboard_router
from app.modules.identity import router as identity_router
from app.modules.policy import invariants as _policy_invariants  # noqa: F401
from app.modules.policy import router as policy_router
from app.modules.risk import invariants as _risk_invariants  # noqa: F401
from app.modules.risk import router as risk_router
from app.modules.threat import invariants as _threat_invariants  # noqa: F401
from app.modules.threat import router as threat_router
from app.modules.treatment import router as treatment_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_development and settings.jwt_secret.strip().lower() in SHIPPED_SECRETS:
        logger.warning(
            "Running with the shipped JWT secret and demo data. This is fine for "
            "local use and refused outside development. Before exposing this to "
            "anyone: set JWT_SECRET, set SEED_DEMO_DATA=false, set ENVIRONMENT."
        )
    bootstrap()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "A GRC platform that enforces governance as a state machine. Every lifecycle "
        "transition is gated, every hard rule is an invariant checked before commit, and "
        "state changes propagate across entities rather than sitting in isolated records."
    ),
    docs_url="/api/docs" if settings.is_development else None,
    openapi_url="/api/openapi.json" if settings.is_development else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Domain failures carry the rule that caused them, so the UI can show the
    user which specification rule blocked their action and why."""
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
    """A constraint violation that reached the database means a schema-layer
    invariant caught something the service layer let through. Surface the
    constraint name; it maps directly to a rule."""
    detail = str(getattr(exc, "orig", exc))
    constraint = None
    for token in detail.split('"'):
        if token.startswith("ck_") or token.startswith("uq_"):
            constraint = token
            break

    # The constraint name maps a database rejection back to a specification rule,
    # which is the useful half. The raw driver message is not returned: for a
    # unique violation it embeds the conflicting values, which would leak record
    # data through an error path. It goes to the log instead.
    logger.warning("constraint violation (%s): %s", constraint or "unknown", detail)
    return JSONResponse(
        status_code=409,
        content={
            "code": "constraint_violation",
            "message": "A database constraint rejected this write.",
            "constraint": constraint,
        },
    )


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


for r in (
    identity_router.router,
    risk_router.router,
    control_router.router,
    control_router.assets_router,
    policy_router.router,
    policy_router.exceptions_router,
    treatment_router.router,
    threat_router.router,
    compliance_router.router,
    dashboard_router.router,
):
    app.include_router(r, prefix="/api")
