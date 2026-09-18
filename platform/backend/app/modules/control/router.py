"""Control API: objectives, activities, deployments, CE assessment, testing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.security import CurrentUser, DbSession
from app.modules.control.machine import (
    CONTROL_ACTIVITY_MACHINE,
    CONTROL_DEPLOYMENT_MACHINE,
    CONTROL_OBJECTIVE_MACHINE,
)
from app.modules.control.models import (
    ASSET_TIERS,
    CE_RATINGS,
    CONTROL_FAMILIES,
    CONTROL_TYPES,
    TEST_FREQUENCIES,
    TEST_RESULTS,
)
from app.modules.control.service import (
    ActivityService,
    AssetService,
    DeploymentService,
    ObjectiveService,
    summarise_activity,
    summarise_deployment,
    summarise_objective,
)

router = APIRouter(prefix="/controls", tags=["controls"])
assets_router = APIRouter(prefix="/assets", tags=["assets"])


class ObjectiveCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = None
    family: str = "Governance"
    control_type: str = "Preventive"
    control_owner_id: str | None = None


class ObjectiveUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    family: str | None = None
    control_type: str | None = None
    control_owner_id: str | None = None
    remediation_plan: str | None = None
    deprecation_rationale: str | None = None


class ActivityCreate(BaseModel):
    objective_id: str
    title: str
    description: str | None = None
    control_operator_id: str | None = None


class ActivityUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    control_operator_id: str | None = None
    suspension_rationale: str | None = None


class DeploymentCreate(BaseModel):
    activity_id: str
    attack_surface_id: str
    test_frequency: str = "Quarterly"


class DeploymentUpdate(BaseModel):
    test_frequency: str | None = None
    decommission_rationale: str | None = None


class CEAssessment(BaseModel):
    ce_rating: str
    ce_evidence_ref: str | None = None
    ce_notes: str | None = None


class TestResult(BaseModel):
    result: str
    evidence_ref: str | None = None
    notes: str | None = None
    supersedes_id: str | None = None


class TransitionRequest(BaseModel):
    target: str
    reason: str | None = None


class AssetCreate(BaseModel):
    name: str
    tier: str = "Tier_3"
    description: str | None = None
    system_owner_id: str | None = None


# -- objectives ------------------------------------------------------------


@router.get("")
def list_objectives(
    session: DbSession, user: CurrentUser, state: str | None = None, family: str | None = None
) -> list[dict[str, Any]]:
    svc = ObjectiveService(session, user.id, user.role_names)
    rows = [summarise_objective(o) for o in svc.list(lifecycle_state=state, family=family)]
    rows.sort(key=lambda r: r["reference"])
    return rows


@router.post("", status_code=201)
def create_objective(
    payload: ObjectiveCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ObjectiveService(session, user.id, user.role_names)
    return svc.detail(svc.create_objective(payload.model_dump(exclude_none=True)))


@router.get("/machines")
def machines(user: CurrentUser) -> dict[str, Any]:
    return {
        "objective": CONTROL_OBJECTIVE_MACHINE.describe(),
        "activity": CONTROL_ACTIVITY_MACHINE.describe(),
        "deployment": CONTROL_DEPLOYMENT_MACHINE.describe(),
    }


@router.get("/reference-data")
def reference_data(user: CurrentUser) -> dict[str, Any]:
    from app.engine.scoring import CE_EXPIRY_MONTHS, CE_MAX_LIKELIHOOD_REDUCTION

    return {
        "families": list(CONTROL_FAMILIES),
        "types": list(CONTROL_TYPES),
        "ce_ratings": list(CE_RATINGS),
        "test_results": list(TEST_RESULTS),
        "test_frequencies": list(TEST_FREQUENCIES),
        "asset_tiers": list(ASSET_TIERS),
        "ce_expiry_months": CE_EXPIRY_MONTHS,
        "ce_likelihood_reduction": CE_MAX_LIKELIHOOD_REDUCTION,
    }


@router.get("/{objective_id}")
def get_objective(objective_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = ObjectiveService(session, user.id, user.role_names)
    return svc.detail(svc.get(objective_id))


@router.patch("/{objective_id}")
def update_objective(
    objective_id: str, payload: ObjectiveUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ObjectiveService(session, user.id, user.role_names)
    obj = svc.get(objective_id)
    svc.apply(obj, payload.model_dump(exclude_unset=True))
    session.commit()
    return svc.detail(obj)


@router.post("/{objective_id}/transition")
def transition_objective(
    objective_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ObjectiveService(session, user.id, user.role_names)
    obj = svc.get(objective_id)
    result = svc.transition(obj, payload.target, reason=payload.reason)
    return {"transition": result, "objective": svc.detail(obj)}


@router.post("/{objective_id}/confirm-alignment/{policy_id}")
def confirm_alignment(
    objective_id: str, policy_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ObjectiveService(session, user.id, user.role_names)
    obj = svc.get(objective_id)
    svc.confirm_alignment(obj, policy_id)
    return svc.detail(obj)


# -- activities ------------------------------------------------------------


@router.post("/activities", status_code=201)
def create_activity(
    payload: ActivityCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ActivityService(session, user.id, user.role_names)
    act = svc.create_activity(payload.model_dump(exclude_none=True))
    return summarise_activity(act)


@router.patch("/activities/{activity_id}")
def update_activity(
    activity_id: str, payload: ActivityUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ActivityService(session, user.id, user.role_names)
    act = svc.get(activity_id)
    svc.apply(act, payload.model_dump(exclude_unset=True))
    session.commit()
    return summarise_activity(act)


@router.get("/activities/{activity_id}/gates")
def activity_gates(
    activity_id: str, session: DbSession, user: CurrentUser
) -> list[dict[str, Any]]:
    svc = ActivityService(session, user.id, user.role_names)
    return svc.gate_report(svc.get(activity_id))


@router.post("/activities/{activity_id}/transition")
def transition_activity(
    activity_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ActivityService(session, user.id, user.role_names)
    act = svc.get(activity_id)
    result = svc.transition(act, payload.target, reason=payload.reason)
    return {"transition": result, "activity": summarise_activity(act)}


# -- deployments -----------------------------------------------------------


@router.post("/deployments", status_code=201)
def create_deployment(
    payload: DeploymentCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = DeploymentService(session, user.id, user.role_names)
    return svc.detail(svc.create_deployment(payload.model_dump(exclude_none=True)))


@router.get("/deployments/{deployment_id}")
def get_deployment(
    deployment_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = DeploymentService(session, user.id, user.role_names)
    return svc.detail(svc.get(deployment_id))


@router.patch("/deployments/{deployment_id}")
def update_deployment(
    deployment_id: str, payload: DeploymentUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = DeploymentService(session, user.id, user.role_names)
    dep = svc.get(deployment_id)
    svc.apply(dep, payload.model_dump(exclude_unset=True))
    session.commit()
    return svc.detail(dep)


@router.post("/deployments/{deployment_id}/ce")
def assess_ce(
    deployment_id: str, payload: CEAssessment, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = DeploymentService(session, user.id, user.role_names)
    dep = svc.get(deployment_id)
    svc.assess_ce(dep, payload.model_dump(exclude_none=True))
    return svc.detail(dep)


@router.post("/deployments/{deployment_id}/tests", status_code=201)
def record_test(
    deployment_id: str, payload: TestResult, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = DeploymentService(session, user.id, user.role_names)
    dep = svc.get(deployment_id)
    svc.record_test(dep, payload.model_dump(exclude_none=True))
    return svc.detail(dep)


@router.post("/deployments/{deployment_id}/transition")
def transition_deployment(
    deployment_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = DeploymentService(session, user.id, user.role_names)
    dep = svc.get(deployment_id)
    result = svc.transition(dep, payload.target, reason=payload.reason)
    return {"transition": result, "deployment": svc.detail(dep)}


# -- assets ----------------------------------------------------------------


@assets_router.get("")
def list_assets(session: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    svc = AssetService(session, user.id, user.role_names)
    return [
        {
            "id": a.id,
            "name": a.name,
            "tier": a.tier,
            "description": a.description,
            "system_owner_id": a.system_owner_id,
        }
        for a in sorted(svc.list(), key=lambda a: a.name)
    ]


@assets_router.post("", status_code=201)
def create_asset(payload: AssetCreate, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = AssetService(session, user.id, user.role_names)
    asset = svc.create_asset(payload.model_dump(exclude_none=True))
    return {"id": asset.id, "name": asset.name, "tier": asset.tier}
