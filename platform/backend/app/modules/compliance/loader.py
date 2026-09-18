"""Framework catalogue loading.

Catalogues are YAML files bind-mounted alongside governance.yml, so an
organisation adds a framework by dropping in a file rather than by migrating a
schema. The loader runs at boot and is idempotent: requirements are matched on
(framework, ref), so re-running it updates text and adds new clauses without
disturbing any assessment or coverage assertion already recorded against them.

AINV-6 is enforced here, before anything is written. A catalogue declaring
`redistributable: false` while carrying requirement prose is refused, loudly,
with the file named. That is the difference between a licence obligation that is
documented and one that holds.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.governance import governance
from app.modules.compliance.models import ComplianceFramework, ComplianceRequirement

logger = logging.getLogger(__name__)


class CatalogueRefused(Exception):
    """A catalogue that must not be loaded. Raised at boot, never swallowed."""


REQUIRED_KEYS = ("id", "name", "version")


def _read(path: pathlib.Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise CatalogueRefused(str(path) + ": expected a mapping at the top level")
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    if missing:
        raise CatalogueRefused(
            str(path) + " is missing required keys: " + ", ".join(missing)
        )
    return data


def _check_licence(path: pathlib.Path, data: dict[str, Any]) -> None:
    """AINV-6, applied before a single row is written."""
    if data.get("redistributable"):
        return
    with_text = [
        str(r.get("ref"))
        for r in (data.get("requirements") or [])
        if r.get("requirement_text")
    ]
    if with_text:
        raise CatalogueRefused(
            str(path)
            + " declares redistributable: false but carries requirement text for: "
            + ", ".join(with_text[:5])
            + ("..." if len(with_text) > 5 else "")
            + ".\n"
            "This framework's content may not be redistributed by this "
            "repository. Remove the text and import it from your own licensed "
            "copy with tools/import_framework.py, which writes to the database "
            "and never back into the tree.\n"
            "This is AINV-6. It is a refusal rather than a warning because a "
            "warning at boot is a warning nobody reads."
        )


def load_catalogues(session: Session) -> list[str]:
    """Load every catalogue in the configured directory. Returns framework ids."""
    directory = pathlib.Path(governance.frameworks_dir)
    adopted_ids = set(governance.adopted_frameworks)
    if not directory.is_dir():
        if adopted_ids:
            # Silently reporting zero requirements for a framework somebody
            # believes is in scope is worse than not loading it at all: the
            # posture page would show an empty, confident-looking register.
            raise CatalogueRefused(
                "compliance.adopt names "
                + ", ".join(sorted(adopted_ids))
                + " but there is no catalogue directory at "
                + str(directory)
                + ". Mount config/frameworks into the container, or empty "
                "compliance.adopt if you are not using the module yet."
            )
        logger.info("no framework catalogue directory at %s; skipping", directory)
        return []

    adopted = adopted_ids
    loaded: list[str] = []

    for path in sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml")):
        data = _read(path)
        _check_licence(path, data)

        framework_id = str(data["id"])
        framework = session.execute(
            select(ComplianceFramework).where(
                ComplianceFramework.framework_id == framework_id
            )
        ).scalar_one_or_none()

        if framework is None:
            framework = ComplianceFramework(framework_id=framework_id)
            session.add(framework)

        # AINV-7: the version is identity. Changing it in place on a catalogue
        # that already has requirements would re-point existing coverage
        # assertions at renumbered clauses.
        if framework.version and framework.version != str(data["version"]):
            if framework.requirement_count:
                raise CatalogueRefused(
                    str(path)
                    + ": framework "
                    + framework_id
                    + " is already loaded at version "
                    + framework.version
                    + " with "
                    + str(framework.requirement_count)
                    + " requirements. Changing the version in place would "
                    "silently re-point every existing coverage assertion. "
                    "Publish the new version under its own id (AINV-7)."
                )

        framework.name = str(data["name"])
        framework.version = str(data["version"])
        framework.authority = data.get("authority")
        framework.source_url = data.get("source_url")
        framework.redistributable = bool(data.get("redistributable"))
        framework.licence_note = data.get("licence_note")
        framework.adopted = framework_id in adopted
        session.flush()

        existing = {
            r.ref: r
            for r in session.execute(
                select(ComplianceRequirement).where(
                    ComplianceRequirement.framework_id == framework.id
                )
            ).scalars()
        }

        for order, row in enumerate(data.get("requirements") or []):
            ref = str(row.get("ref", "")).strip()
            if not ref:
                continue
            requirement = existing.get(ref)
            if requirement is None:
                requirement = ComplianceRequirement(
                    framework_id=framework.id, ref=ref
                )
                session.add(requirement)
            requirement.title = str(row.get("title") or ref)
            requirement.requirement_text = row.get("requirement_text")
            requirement.category = row.get("category")
            requirement.sort_order = order

        session.flush()
        loaded.append(framework_id)
        logger.info(
            "loaded %s v%s: %d requirements%s",
            framework_id,
            framework.version,
            len(data.get("requirements") or []),
            " (adopted)" if framework.adopted else "",
        )

    missing_adoptions = adopted - set(loaded)
    if missing_adoptions:
        # Not fatal, but it means a posture report will silently omit a
        # framework somebody believes is in scope.
        logger.warning(
            "compliance.adopt names frameworks with no catalogue in %s: %s",
            directory,
            ", ".join(sorted(missing_adoptions)),
        )

    return loaded
