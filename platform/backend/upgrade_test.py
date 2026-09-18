"""Does a v0.1.0 database survive the upgrade?

v0.1.0 built its schema with `create_all` and has no alembic_version table.
Replaying the initial migration against it would fail on the first CREATE TABLE,
so db_init stamps it instead. This simulates that database and checks the
adoption works, because "upgrading loses your data" was the headline limitation
of 0.1.0 and a claim to have fixed it is worth testing.
"""
import sys

from sqlalchemy import inspect, text

from app.core.db import Base, engine
from app.db_init import _migrate, _install_immutability_triggers, _verify_immutability_triggers

# register every model
import app.modules.compliance.models  # noqa: F401
import app.modules.control.models  # noqa: F401
import app.modules.identity.models  # noqa: F401
import app.modules.policy.models  # noqa: F401
import app.modules.risk.models  # noqa: F401
import app.modules.threat.models  # noqa: F401
import app.modules.treatment.models  # noqa: F401

PASS, FAIL = [], []


def check(label, ok, detail=""):
    (PASS if ok else FAIL).append(label)
    print(("  PASS  " if ok else "  FAIL  ") + label + ("" if ok else "  -> " + str(detail)))


print("\n-- simulate a v0.1.0 database -------------------------------")
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE"))
    c.execute(text("CREATE SCHEMA public"))

# exactly what v0.1.0 did
Base.metadata.create_all(bind=engine)
with engine.begin() as c:
    _install_immutability_triggers(c)

tables = set(inspect(engine).get_table_names())
check("schema built the old way", "users" in tables and len(tables) > 30, len(tables))
check("no migration history, as on v0.1.0", "alembic_version" not in tables)

# put a row in, so we can prove data survives
with engine.begin() as c:
    c.execute(
        text(
            "INSERT INTO users (id, email, full_name, seniority, password_hash) "
            "VALUES ('legacy-user', 'legacy@example.com', 'Legacy Record', 'Director', 'x')"
        )
    )

print("\n-- run the new boot path ------------------------------------")
_migrate()

tables_after = set(inspect(engine).get_table_names())
check("migration history adopted", "alembic_version" in tables_after)

with engine.connect() as c:
    rev = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    survived = c.execute(
        text("SELECT full_name FROM users WHERE id = 'legacy-user'")
    ).scalar()
check("stamped at a revision", bool(rev), rev)
check("the pre-existing row survived", survived == "Legacy Record", survived)
check("no tables lost", tables <= tables_after, tables - tables_after)

with engine.begin() as c:
    _install_immutability_triggers(c)
    try:
        _verify_immutability_triggers(c)
        check("append-only triggers verified after upgrade", True)
    except RuntimeError as exc:
        check("append-only triggers verified after upgrade", False, exc)

print("\n-- a second boot is a no-op ---------------------------------")
_migrate()
with engine.connect() as c:
    rev2 = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
check("revision unchanged on re-run", rev2 == rev, (rev, rev2))

print("\n" + "=" * 58)
print("passed: " + str(len(PASS)) + "   failed: " + str(len(FAIL)))
print("=" * 58)
sys.exit(1 if FAIL else 0)
