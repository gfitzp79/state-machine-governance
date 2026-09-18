"""Schema creation, immutability triggers, and demo seeding.

The immutability triggers are the reason this is not just `create_all`. CINV-7
and PINV-9 require that test history and policy versions cannot be altered. A
service-layer rule cannot deliver that, because anyone with a database connection
bypasses the service layer. A trigger cannot be bypassed.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

# Tables that accept INSERT only. UPDATE and DELETE raise at the database layer.
APPEND_ONLY_TABLES = (
    "audit_log",
    "risk_phase_history",
    "policy_versions",
    "control_tests",
    "treatment_checkins",
    "threat_scenario_evidence",
)

IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION grc_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'Table % is append-only: % is not permitted. This enforces the immutability '
        'invariants (CINV-7, PINV-9). Corrections create a new superseding record.',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def _install_immutability_triggers(connection) -> None:
    connection.execute(text(IMMUTABILITY_FUNCTION))
    for table in APPEND_ONLY_TABLES:
        trigger = "trg_" + table + "_append_only"
        connection.execute(text("DROP TRIGGER IF EXISTS " + trigger + " ON " + table))
        connection.execute(
            text(
                "CREATE TRIGGER "
                + trigger
                + " BEFORE UPDATE OR DELETE ON "
                + table
                + " FOR EACH ROW EXECUTE FUNCTION grc_reject_mutation()"
            )
        )


def bootstrap() -> None:
    """Create the schema on first boot, install triggers, seed demo data."""
    # Importing every model module first so create_all sees the full metadata.
    from app.modules.control import models as _control  # noqa: F401
    from app.modules.identity import models as _identity  # noqa: F401
    from app.modules.policy import models as _policy  # noqa: F401
    from app.modules.risk import models as _risk  # noqa: F401
    from app.modules.threat import models as _threat  # noqa: F401
    from app.modules.treatment import models as _treatment  # noqa: F401

    inspector = inspect(engine)
    fresh = "users" not in inspector.get_table_names()

    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        _install_immutability_triggers(connection)
    logger.info("append-only triggers installed on %s", ", ".join(APPEND_ONLY_TABLES))

    if fresh and settings.seed_demo_data:
        from app.seed import seed

        session = SessionLocal()
        try:
            seed(session)
            logger.info("demo dataset seeded")
        finally:
            session.close()
