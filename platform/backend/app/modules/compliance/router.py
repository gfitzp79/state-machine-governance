"""Compliance and assurance API."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.governance import governance
from app.core.security import CurrentUser, DbSession
from app.modules.compliance.machine import REQUIREMENT_ASSESSMENT_MACHINE
from app.modules.compliance.service import ComplianceService

router = APIRouter(prefix="/compliance", tags=["compliance"])


class AssessBody(BaseModel):
    target: str
    rationale: str | None = None
    owner_id: str | None = None
    compensating_expiry: date | None = None


class LinkBody(BaseModel):
    objective_id: str
    coverage_level: str = Field(default="Full")
    rationale: str | None = None


class CoverageBody(BaseModel):
    coverage_level: str


class AdoptBody(BaseModel):
    adopted: bool


class ScopeBody(BaseModel):
    compliance_scopes: list[str]


def _service(session: DbSession, user: CurrentUser) -> ComplianceService:
    # role_names, not roles: `roles` is the ORM relationship, and passing it
    # would make every role check compare strings against UserRole objects.
    return ComplianceService(session, user.id, user.role_names)


@router.get("/frameworks")
def list_frameworks(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _service(session, user)
    return {
        "frameworks": [
            {
                "id": f.id,
                "framework_id": f.framework_id,
                "name": f.name,
                "version": f.version,
                "authority": f.authority,
                "adopted": f.adopted,
                "redistributable": f.redistributable,
                "licence_note": f.licence_note,
                "source_url": f.source_url,
                "requirements": f.requirement_count,
            }
            for f in svc.frameworks()
        ],
        # Surfaced so the UI can explain an empty catalogue rather than looking
        # broken: a licensed framework ships with no requirements by design.
        "licensed_frameworks": list(governance.licensed_frameworks),
    }


@router.post("/frameworks/{framework_id}/adoption")
def set_adoption(
    framework_id: str, body: AdoptBody, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    f = svc.set_adoption(framework_id, body.adopted)
    return {"framework_id": f.framework_id, "adopted": f.adopted}


@router.get("/frameworks/{framework_id}/requirements")
def list_requirements(
    framework_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    rows = []
    for r in svc.requirements(framework_id):
        assessment = r.assessment
        rows.append(
            {
                "id": r.id,
                "ref": r.ref,
                "title": r.title,
                "requirement_text": r.requirement_text,
                "category": r.category,
                "state": assessment.lifecycle_state if assessment else "Not_Assessed",
                "rationale": assessment.rationale if assessment else None,
                "gap_reason": assessment.gap_reason if assessment else None,
                "compensating_expiry": (
                    assessment.compensating_expiry.isoformat()
                    if assessment and assessment.compensating_expiry
                    else None
                ),
                "links": [
                    {
                        "link_id": link.id,
                        "objective_id": link.objective_id,
                        "reference": link.objective.reference if link.objective else None,
                        "title": link.objective.title if link.objective else None,
                        "lifecycle_state": (
                            link.objective.lifecycle_state if link.objective else None
                        ),
                        "coverage_level": link.coverage_level,
                        "satisfies": link.satisfies,
                        "rationale": link.rationale,
                    }
                    for link in r.control_links
                ],
            }
        )
    return {"requirements": rows}


@router.get("/requirements/{requirement_id}/gates")
def requirement_gates(
    requirement_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    assessment = svc.assessment_for(requirement_id)
    session.commit()
    return {
        "state": assessment.lifecycle_state,
        "gates": svc.gate_report(assessment),
        "invariants": svc.invariant_report(assessment),
    }


@router.post("/requirements/{requirement_id}/assess")
def assess(
    requirement_id: str, body: AssessBody, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    payload = body.model_dump(exclude_none=True)
    target = payload.pop("target")
    return svc.assess(requirement_id, target, **payload)


@router.post("/requirements/{requirement_id}/controls")
def link_control(
    requirement_id: str, body: LinkBody, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    link = svc.link_control(
        requirement_id, body.objective_id, body.coverage_level, body.rationale
    )
    return {"link_id": link.id, "coverage_level": link.coverage_level}


@router.patch("/links/{link_id}")
def set_coverage(
    link_id: str, body: CoverageBody, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    link = svc.set_coverage_level(link_id, body.coverage_level)
    return {"link_id": link.id, "coverage_level": link.coverage_level}


@router.delete("/links/{link_id}")
def unlink(link_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    _service(session, user).unlink_control(link_id)
    return {"unlinked": link_id}


@router.post("/assets/{asset_id}/scopes")
def set_asset_scopes(
    asset_id: str, body: ScopeBody, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    asset = svc.set_asset_scopes(asset_id, body.compliance_scopes)
    return {"asset_id": asset.id, "compliance_scopes": asset.compliance_scopes}


@router.get("/posture")
def posture(
    session: DbSession, user: CurrentUser, framework_id: str | None = None
) -> dict[str, Any]:
    return _service(session, user).posture(framework_id)


@router.get("/gaps")
def gaps(
    session: DbSession, user: CurrentUser, framework_id: str | None = None
) -> dict[str, Any]:
    return {"gaps": _service(session, user).gaps(framework_id)}


@router.get("/controls/{objective_id}/requirements")
def requirements_for_control(
    objective_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    return {"requirements": _service(session, user).requirements_for_control(objective_id)}


@router.get("/machine")
def machine(user: CurrentUser) -> dict[str, Any]:
    return REQUIREMENT_ASSESSMENT_MACHINE.describe()


@router.get("/taxonomy")
def taxonomy(user: CurrentUser) -> dict[str, Any]:
    return {
        "coverage_levels": governance.coverage_level_detail,
        "satisfying": list(governance.satisfying_coverage_levels),
        "compensating_max_days": governance.compensating_max_days,
        "assessment_states": list(REQUIREMENT_ASSESSMENT_MACHINE.states),
    }
