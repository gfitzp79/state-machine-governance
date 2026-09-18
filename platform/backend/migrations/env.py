"""Alembic environment.

Two things here are not boilerplate.

The database URL comes from the application's own settings rather than from
alembic.ini, so a deployment configures its database in one place and a
migration cannot run against a different database from the API that will use it.

Every model module is imported before `target_metadata` is read. Alembic
compares the live database against whatever happens to be registered on
`Base.metadata` at that moment, so a module nobody imported is a table Alembic
believes should be dropped. Autogenerate would then cheerfully write a migration
deleting it.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.db import Base

# Importing for the side effect of registering each model on Base.metadata.
from app.modules.compliance import models as _compliance  # noqa: F401
from app.modules.control import models as _control  # noqa: F401
from app.modules.identity import models as _identity  # noqa: F401
from app.modules.policy import models as _policy  # noqa: F401
from app.modules.risk import models as _risk  # noqa: F401
from app.modules.threat import models as _threat  # noqa: F401
from app.modules.treatment import models as _treatment  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _compare_server_default(
    context,
    inspected_column,
    metadata_column,
    inspected_default,
    metadata_default,
    rendered_metadata_default,
) -> bool | None:
    """Treat functionally identical defaults as identical.

    Alembic's built-in server-default comparison is textual, and PostgreSQL
    reflects `now()` in a form that never matches what SQLAlchemy renders for
    `func.now()`. Left alone it reports drift on all fifteen timestamp columns,
    on every run, forever.

    The tempting fix is to turn `compare_server_default` off. That would make
    the check pass by making it blind: a genuine default change would then go
    unnoticed too. This normalises the pair instead, so `now()` stops being
    reported and an actual change still is.

    Returning False means "no difference". Returning None hands the decision
    back to Alembic's own comparison.
    """

    def normalise(value: object) -> str | None:
        if value is None:
            return None
        text_value = str(getattr(value, "arg", value)).strip().lower()
        # Postgres reflects casts and parentheses that the metadata side omits.
        for suffix in ("::timestamp with time zone", "::timestamptz", "::text"):
            text_value = text_value.replace(suffix, "")
        text_value = text_value.strip().strip("()").strip()
        # now() and current_timestamp are the same instant in the same
        # transaction, and Postgres reports one where the model declares the
        # other depending on how it was written.
        if text_value in ("now", "now()", "current_timestamp", "statement_timestamp()"):
            return "now()"
        return text_value

    if normalise(inspected_default) == normalise(rendered_metadata_default):
        return False
    return None


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=_compare_server_default,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # A column whose type changed is a schema change. Without this,
            # Alembic ignores it and the migration history stops describing the
            # database it produced.
            compare_type=True,
            compare_server_default=_compare_server_default,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
