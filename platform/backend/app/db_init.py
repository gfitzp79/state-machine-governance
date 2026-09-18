"""Schema migration, immutability triggers, catalogue loading, and demo seeding.

The schema is owned by Alembic. `create_all` built the tables correctly on a
fresh database and offered nothing at all on the second version, which is why
v0.1.0 shipped saying that upgrading meant export, recreate and re-import.

Three things happen on every boot, in this order and for these reasons:

  1. migrate. `alembic upgrade head`, so a container started against an older
     database brings it forward rather than running against a schema it does
     not match.
  2. re-assert the append-only triggers. The initial migration installs them so
     that `alembic upgrade head` alone yields a correct database, and this runs
     again because APPEND_ONLY_TABLES here is the authoritative list.
  3. verify. Confirming the triggers are present, rather than assuming the
     statement that created them worked, is the difference between applying a
     control and evidencing it. CINV-7 and PINV-9 are why this module exists;
     checking costs one query.
"""

from __future__ import annotations

import logging
import pathlib

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.db import SessionLocal, engine

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

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


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


def _verify_immutability_triggers(connection) -> None:
    """Confirm every append-only table actually carries its trigger.

    Applying a control and confirming it is in place are different acts, and
    this project is an argument for the second one.
    """
    present = {
        row[0]
        for row in connection.execute(
            text(
                "SELECT c.relname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE NOT t.tgisinternal AND t.tgname LIKE 'trg\\_%\\_append\\_only'"
            )
        )
    }
    missing = [t for t in APPEND_ONLY_TABLES if t not in present]
    if missing:
        raise RuntimeError(
            "append-only triggers missing on: "
            + ", ".join(missing)
            + ". These tables enforce CINV-7, PINV-9 and TSE-1 at the database "
            "layer, and without them a direct SQL connection can rewrite the "
            "audit trail. Refusing to start."
        )


def _migrate() -> None:
    """Bring the database to head, adopting one created before Alembic existed.

    A v0.1.0 database was built by `create_all` and has no `alembic_version`
    table. Replaying the initial migration against it would fail on the first
    CREATE TABLE. Its tables are the ones that migration would have produced,
    so it is stamped rather than replayed.
    """
    config = _alembic_config()
    tables = set(inspect(engine).get_table_names())

    if tables and "alembic_version" not in tables:
        head = ScriptDirectory.from_config(config).get_current_head()
        logger.warning(
            "database has %d tables and no migration history, so it predates "
            "Alembic. Stamping it at %s. Confirm the schema matches before "
            "relying on later migrations.",
            len(tables),
            head,
        )
        command.stamp(config, "head")

    with engine.connect() as connection:
        before = MigrationContext.configure(connection).get_current_revision()

    command.upgrade(config, "head")

    with engine.connect() as connection:
        after = MigrationContext.configure(connection).get_current_revision()

    if before == after:
        logger.info("database already at %s", after)
    else:
        logger.info("database migrated from %s to %s", before or "empty", after)


def bootstrap() -> None:
    """Migrate, enforce immutability, load catalogues, seed the demo dataset."""
    # Imported for the side effect of registering every model, so anything
    # reading Base.metadata after boot sees the whole schema.
    from app.modules.compliance import models as _compliance  # noqa: F401
    from app.modules.control import models as _control  # noqa: F401
    from app.modules.identity import models as _identity  # noqa: F401
    from app.modules.policy import models as _policy  # noqa: F401
    from app.modules.risk import models as _risk  # noqa: F401
    from app.modules.threat import models as _threat  # noqa: F401
    from app.modules.treatment import models as _treatment  # noqa: F401

    fresh = "users" not in set(inspect(engine).get_table_names())

    _migrate()

    with engine.begin() as connection:
        _install_immutability_triggers(connection)
        _verify_immutability_triggers(connection)
    logger.info("append-only triggers verified on %s", ", ".join(APPEND_ONLY_TABLES))

    # Framework catalogues load on every boot, not only a fresh one: adding a
    # catalogue file should be enough to make it available. The loader is
    # idempotent and matches on (framework, ref), so re-running it never
    # disturbs an assessment already recorded against a requirement.
    #
    # AINV-6 is enforced inside it, and a refusal is deliberately fatal. A
    # licence breach that logs a warning and boots anyway is the failure mode
    # this whole project argues against.
    from app.modules.compliance.loader import load_catalogues

    session = SessionLocal()
    try:
        loaded = load_catalogues(session)
        session.commit()
        if loaded:
            logger.info("compliance catalogues loaded: %s", ", ".join(loaded))
    finally:
        session.close()

    if fresh and settings.seed_demo_data:
        from app.seed import seed

        session = SessionLocal()
        try:
            seed(session)
            logger.info("demo dataset seeded")
        finally:
            session.close()
