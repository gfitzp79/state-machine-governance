"""Import a licensed framework's requirements from your own copy.

ISO 27001, CIS, PCI DSS and the AICPA Trust Services Criteria cannot be
redistributed by this repository, so their catalogue files ship with the
framework record and no requirements. This tool fills them in from a file you
produce from your own licensed copy.

It writes to the DATABASE and never back into the repository tree, which is
deliberate: it means running it cannot put licensed content somewhere a
`git commit -a` would pick it up.

Usage, from the repository root with the stack running:

    docker compose -f platform/docker-compose.yml cp \\
        my-annex-a.csv api:/tmp/annex-a.csv
    docker compose -f platform/docker-compose.yml exec api \\
        python /srv/../tools/import_framework.py ISO-27001-2022 /tmp/annex-a.csv

or, if you run the backend directly:

    python tools/import_framework.py ISO-27001-2022 my-annex-a.csv

Input is CSV with a header row. Recognised columns, case-insensitive:

    ref          required   the identifier, e.g. A.5.15
    title        required   the control name
    text         optional   full requirement prose
    category     optional   grouping, e.g. "Organizational controls"

Anything else is ignored, so exporting more columns than you need is fine.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "platform" / "backend"))

ALIASES = {
    "ref": {"ref", "reference", "id", "control", "control_id", "clause"},
    "title": {"title", "name", "control_name", "summary"},
    "text": {"text", "requirement_text", "description", "requirement", "detail"},
    "category": {"category", "group", "theme", "section", "domain"},
}


def _column_map(header: list[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for column in header:
        key = column.strip().lower().replace(" ", "_")
        for canonical, names in ALIASES.items():
            if key in names and canonical not in mapped:
                mapped[canonical] = column
    return mapped


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    framework_id, source = argv[1], argv[2]
    path = Path(source)
    if not path.is_file():
        print("no such file: " + source)
        return 1

    # Imported late so the usage message works without a database.
    import app.db_init  # noqa: F401  registers every model
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.compliance.models import ComplianceFramework, ComplianceRequirement

    session = SessionLocal()
    try:
        framework = session.execute(
            select(ComplianceFramework).where(
                ComplianceFramework.framework_id == framework_id
            )
        ).scalar_one_or_none()
        if framework is None:
            print(
                "framework " + framework_id + " is not loaded. Add a catalogue "
                "file for it in platform/config/frameworks/ first, declaring "
                "redistributable: false and an empty requirements list."
            )
            return 1

        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                print("the file has no header row")
                return 1
            columns = _column_map(list(reader.fieldnames))
            missing = [c for c in ("ref", "title") if c not in columns]
            if missing:
                print(
                    "could not find a column for: " + ", ".join(missing)
                    + "\nheader was: " + ", ".join(reader.fieldnames)
                )
                return 1

            existing = {
                r.ref: r
                for r in session.execute(
                    select(ComplianceRequirement).where(
                        ComplianceRequirement.framework_id == framework.id
                    )
                ).scalars()
            }

            added = updated = 0
            for order, row in enumerate(reader):
                ref = (row.get(columns["ref"]) or "").strip()
                if not ref:
                    continue
                requirement = existing.get(ref)
                if requirement is None:
                    requirement = ComplianceRequirement(
                        framework_id=framework.id, ref=ref
                    )
                    session.add(requirement)
                    added += 1
                else:
                    updated += 1
                requirement.title = (row.get(columns["title"]) or ref).strip()
                if "text" in columns:
                    requirement.requirement_text = (row.get(columns["text"]) or "").strip() or None
                if "category" in columns:
                    requirement.category = (row.get(columns["category"]) or "").strip() or None
                requirement.sort_order = order

        session.commit()
        print(
            "imported into " + framework_id + ": "
            + str(added) + " added, " + str(updated) + " updated."
        )
        if not framework.adopted:
            print(
                "note: " + framework_id + " is not adopted, so its requirements "
                "are reference material and cannot be assessed (AINV-8). Add it "
                "to compliance.adopt in governance.yml, or adopt it in the UI."
            )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
