"""Threat management API."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.errors import NotFound
from app.core.governance import governance
from app.core.security import CurrentUser, DbSession
from app.modules.threat.machine import THREAT_MODEL_MACHINE
from app.modules.threat.models import (
    ASSURANCE_LEVELS,
    COMPONENT_TYPES,
    SEVERITIES,
    STRIDE_CATEGORIES,
    ThreatScenario,
)
from app.modules.threat.service import ThreatModelService, summarise_model

router = APIRouter(prefix="/threat-models", tags=["threat models"])


class ModelCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    attack_surface_id: str
    system_owner_id: str
    appsec_partner_id: str | None = None
    description: str | None = None
    methodology: str = "STRIDE"


class ModelUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    appsec_partner_id: str | None = None
    system_owner_id: str | None = None


class ComponentCreate(BaseModel):
    name: str
    component_type: str
    description: str | None = None
    data_classification: str | None = None
    data_types: list[str] = []
    trust_zone: str | None = None
    exposure: str | None = None
    attack_surface_id: str | None = None
    source_component_id: str | None = None
    target_component_id: str | None = None


class ComponentUpdate(BaseModel):
    name: str | None = None
    component_type: str | None = None
    description: str | None = None
    data_classification: str | None = None
    data_types: list[str] | None = None
    trust_zone: str | None = None
    exposure: str | None = None
    attack_surface_id: str | None = None
    source_component_id: str | None = None
    target_component_id: str | None = None


class ScenarioUpdate(BaseModel):
    description: str | None = None
    category: str | None = None
    inherent_severity: str | None = None
    remediation_target_date: date | None = None
    status_rationale: str | None = None
    component_id: str | None = None


class CommentRequest(BaseModel):
    body: str
    parent_comment_id: str | None = None


class EvidenceRequest(BaseModel):
    title: str
    evidence_ref: str
    evidence_type: str | None = None
    notes: str | None = None
    supports: str | None = None
    supersedes_id: str | None = None


class RiskLinkRequest(BaseModel):
    risk_id: str
    link_type: str = "Represents"
    rationale: str | None = None


class ReopenRequest(BaseModel):
    rationale: str


class ScenarioCreate(BaseModel):
    component_id: str
    category: str
    description: str
    inherent_severity: str
    remediation_target_date: date | None = None


class MitigateRequest(BaseModel):
    deployment_id: str
    effectiveness_assurance: str = "Fully_Mitigated"


class AcceptRequest(BaseModel):
    acceptance_expiry: date
    acceptance_rationale: str


class PromoteRequest(BaseModel):
    title: str | None = None
    cause: str | None = None
    threat_event: str | None = None
    vulnerability: str | None = None
    impact_statement: str | None = None
    tier: str = "Tier_3"
    risk_owner_id: str | None = None
    risk_stakeholder_id: str | None = None
    risk_analyst_id: str | None = None


class SignoffRequest(BaseModel):
    as_role: str  # "appsec" or "owner"


class TransitionRequest(BaseModel):
    target: str
    reason: str | None = None


def _svc(session, user) -> ThreatModelService:
    return ThreatModelService(session, user.id, user.role_names)


def _scenario(session, scenario_id: str) -> ThreatScenario:
    scenario = session.get(ThreatScenario, scenario_id)
    if scenario is None:
        raise NotFound("threat scenario not found")
    return scenario


@router.get("")
def list_models(
    session: DbSession, user: CurrentUser, state: str | None = None
) -> list[dict[str, Any]]:
    svc = _svc(session, user)
    rows = [summarise_model(m) for m in svc.list(lifecycle_state=state)]
    rows.sort(key=lambda r: r["reference"])
    return rows


@router.post("", status_code=201)
def create_model(payload: ModelCreate, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _svc(session, user)
    return svc.detail(svc.create_model(payload.model_dump(exclude_none=True)))


@router.get("/machine")
def threat_machine(user: CurrentUser) -> dict[str, Any]:
    return THREAT_MODEL_MACHINE.describe()


@router.get("/reference-data")
def reference_data(user: CurrentUser) -> dict[str, Any]:
    return {
        "stride_categories": list(STRIDE_CATEGORIES),
        "component_types": list(COMPONENT_TYPES),
        "severities": list(SEVERITIES),
        "assurance_levels": list(ASSURANCE_LEVELS),
        "data_classifications": list(governance.data_classifications),
        "sensitive_threshold": governance.sensitive_classification_threshold,
        "trust_zones": governance.trust_zone_detail,
        "exposure_levels": list(governance.exposure_levels),
        "data_types": list(governance.data_types),
        "risk_link_types": [
            t for t in governance.risk_link_type_detail if not t.get("creates_risk")
        ],
        "evidence_types": [
            "Design_Review",
            "Penetration_Test",
            "Code_Review",
            "Scan_Result",
            "Architecture_Diagram",
            "Configuration_Export",
            "Ticket",
            "Other",
        ],
        "stride_control_families": governance.stride_control_families,
    }


@router.get("/{model_id}")
def get_model(model_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _svc(session, user)
    return svc.detail(svc.get(model_id))


@router.patch("/{model_id}")
def update_model(
    model_id: str, payload: ModelUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.apply(tm, payload.model_dump(exclude_unset=True))
    session.commit()
    return svc.detail(tm)


@router.post("/{model_id}/components", status_code=201)
def add_component(
    model_id: str, payload: ComponentCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.add_component(tm, payload.model_dump(exclude_none=True))
    return svc.detail(tm)


@router.delete("/{model_id}/components/{component_id}")
def delete_component(
    model_id: str, component_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.delete_component(tm, component_id)
    return svc.detail(tm)


@router.get("/{model_id}/context")
def model_context(model_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """The control and risk posture of the asset this model is scoped to.

    Read-only and informative. Nothing here mitigates a scenario or changes a
    severity; it exists to make control gaps visible during modelling (TINV-7).
    """
    svc = _svc(session, user)
    return svc.environment(svc.get(model_id))


@router.patch("/{model_id}/components/{component_id}")
def update_component(
    model_id: str,
    component_id: str,
    payload: ComponentUpdate,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.update_component(tm, component_id, payload.model_dump(exclude_unset=True))
    return svc.detail(tm)


@router.patch("/{model_id}/scenarios/{scenario_id}")
def update_scenario(
    model_id: str,
    scenario_id: str,
    payload: ScenarioUpdate,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.update_scenario(_scenario(session, scenario_id), payload.model_dump(exclude_unset=True))
    return svc.detail(tm)


@router.post("/{model_id}/scenarios/{scenario_id}/reopen")
def reopen_scenario(
    model_id: str,
    scenario_id: str,
    payload: ReopenRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.reopen_scenario(_scenario(session, scenario_id), payload.rationale)
    return svc.detail(tm)


@router.delete("/{model_id}/scenarios/{scenario_id}/mitigations/{link_id}")
def unlink_mitigation(
    model_id: str,
    scenario_id: str,
    link_id: str,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.unlink_mitigation(_scenario(session, scenario_id), link_id)
    return svc.detail(tm)


@router.post("/{model_id}/scenarios/{scenario_id}/comments", status_code=201)
def add_scenario_comment(
    model_id: str,
    scenario_id: str,
    payload: CommentRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.add_comment(_scenario(session, scenario_id), payload.body, payload.parent_comment_id)
    return svc.detail(tm)


@router.post("/{model_id}/scenarios/{scenario_id}/evidence", status_code=201)
def add_scenario_evidence(
    model_id: str,
    scenario_id: str,
    payload: EvidenceRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    """Append-only: the database rejects UPDATE and DELETE on evidence, so a
    correction supersedes rather than rewrites (TINV-10)."""
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.add_evidence(_scenario(session, scenario_id), payload.model_dump(exclude_none=True))
    return svc.detail(tm)


@router.post("/{model_id}/scenarios/{scenario_id}/risks", status_code=201)
def link_scenario_risk(
    model_id: str,
    scenario_id: str,
    payload: RiskLinkRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    """Reference an existing risk rather than minting a duplicate (TINV-8)."""
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.link_risk(
        _scenario(session, scenario_id),
        payload.risk_id,
        payload.link_type,
        payload.rationale,
    )
    return svc.detail(tm)


@router.delete("/{model_id}/scenarios/{scenario_id}/risks/{link_id}")
def unlink_scenario_risk(
    model_id: str,
    scenario_id: str,
    link_id: str,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.unlink_risk(_scenario(session, scenario_id), link_id)
    return svc.detail(tm)


@router.post("/{model_id}/scenarios", status_code=201)
def add_scenario(
    model_id: str, payload: ScenarioCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.add_scenario(tm, payload.model_dump(exclude_none=True))
    return svc.detail(tm)


@router.post("/{model_id}/scenarios/{scenario_id}/mitigate")
def mitigate_scenario(
    model_id: str,
    scenario_id: str,
    payload: MitigateRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.mitigate(
        _scenario(session, scenario_id),
        payload.deployment_id,
        payload.effectiveness_assurance,
    )
    return svc.detail(tm)


@router.post("/{model_id}/scenarios/{scenario_id}/accept")
def accept_scenario(
    model_id: str,
    scenario_id: str,
    payload: AcceptRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.accept_locally(
        _scenario(session, scenario_id),
        payload.acceptance_expiry,
        payload.acceptance_rationale,
    )
    return svc.detail(tm)


@router.post("/{model_id}/scenarios/{scenario_id}/promote")
def promote_scenario(
    model_id: str,
    scenario_id: str,
    payload: PromoteRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    risk = svc.promote_to_risk(
        _scenario(session, scenario_id), payload.model_dump(exclude_none=True)
    )
    return {
        "promoted_risk": {"id": risk.id, "reference": risk.reference, "title": risk.title},
        "model": svc.detail(tm),
    }


@router.post("/{model_id}/signoff")
def sign_off(
    model_id: str, payload: SignoffRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    svc.sign_off(tm, payload.as_role)
    return svc.detail(tm)


@router.post("/{model_id}/transition")
def transition_model(
    model_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    tm = svc.get(model_id)
    result = svc.transition(tm, payload.target, reason=payload.reason)
    return {"transition": result, "model": svc.detail(tm)}
