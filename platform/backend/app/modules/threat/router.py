"""Threat management API."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.errors import NotFound
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
def threat_machine() -> dict[str, Any]:
    return THREAT_MODEL_MACHINE.describe()


@router.get("/reference-data")
def reference_data() -> dict[str, Any]:
    return {
        "stride_categories": list(STRIDE_CATEGORIES),
        "component_types": list(COMPONENT_TYPES),
        "severities": list(SEVERITIES),
        "assurance_levels": list(ASSURANCE_LEVELS),
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
