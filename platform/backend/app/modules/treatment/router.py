"""Treatment API."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.governance import governance
from app.core.security import CurrentUser, DbSession
from app.modules.treatment.machine import TREATMENT_MACHINE
from app.modules.treatment.models import CHECKIN_FREQUENCIES, LOE_BANDS, TREATMENT_TYPES
from app.modules.treatment.service import TreatmentService, summarise_treatment

router = APIRouter(prefix="/treatments", tags=["treatments"])


class TreatmentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = None
    treatment_type: str = "Mitigate"
    treatment_owner_id: str | None = None
    target_date: date | None = None
    loe: str | None = None
    check_in_frequency: str | None = "Monthly"
    expected_impact_delta: int = Field(default=0, ge=-4, le=0)
    expected_likelihood_delta: int = Field(default=0, ge=-4, le=0)
    loe_implementation_hours: int | None = None
    loe_operational_hours_pa: int | None = None
    cost_implementation: float | None = None
    cost_operational_pa: float | None = None


class TreatmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    treatment_owner_id: str | None = None
    target_date: date | None = None
    loe: str | None = None
    check_in_frequency: str | None = None
    evidence_ref: str | None = None
    expected_impact_delta: int | None = Field(default=None, ge=-4, le=0)
    expected_likelihood_delta: int | None = Field(default=None, ge=-4, le=0)
    loe_implementation_hours: int | None = None
    loe_operational_hours_pa: int | None = None
    cost_implementation: float | None = None
    cost_operational_pa: float | None = None


class ValidateRequest(BaseModel):
    notes: str | None = None


class CheckinRequest(BaseModel):
    status: str
    notes: str
    blockers: str | None = None


class ApprovalRequest(BaseModel):
    approval_type: str = "treatment_approval"
    assigned_to: str | None = None
    proposed_new_date: date | None = None


class DecisionRequest(BaseModel):
    decision: str
    notes: str | None = None


class TransitionRequest(BaseModel):
    target: str
    reason: str | None = None


def _svc(session, user) -> TreatmentService:
    return TreatmentService(session, user.id, user.role_names)


@router.get("")
def list_treatments(
    session: DbSession, user: CurrentUser, state: str | None = None, owner: str | None = None
) -> list[dict[str, Any]]:
    svc = _svc(session, user)
    rows = [
        summarise_treatment(t)
        for t in svc.list(lifecycle_state=state, treatment_owner_id=owner)
    ]
    rows.sort(key=lambda r: (r["target_date"] is None, r["target_date"], r["reference"]))
    return rows


@router.post("", status_code=201)
def create_treatment(
    payload: TreatmentCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    return svc.detail(svc.create_treatment(payload.model_dump(exclude_none=True)))


@router.get("/machine")
def treatment_machine(user: CurrentUser) -> dict[str, Any]:
    return TREATMENT_MACHINE.describe()


@router.get("/reference-data")
def reference_data(user: CurrentUser) -> dict[str, Any]:
    return {
        "types": list(TREATMENT_TYPES),
        "loe_bands": list(LOE_BANDS),
        "checkin_frequencies": list(CHECKIN_FREQUENCIES),
        "checkin_statuses": list(governance.checkin_statuses),
    }


@router.get("/{treatment_id}")
def get_treatment(treatment_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _svc(session, user)
    return svc.detail(svc.get(treatment_id))


@router.patch("/{treatment_id}")
def update_treatment(
    treatment_id: str, payload: TreatmentUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    treatment = svc.get(treatment_id)
    svc.apply(treatment, payload.model_dump(exclude_unset=True))
    session.commit()
    return svc.detail(treatment)


@router.post("/{treatment_id}/validate")
def validate_feasibility(
    treatment_id: str, payload: ValidateRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    treatment = svc.get(treatment_id)
    svc.validate_feasibility(treatment, payload.notes)
    return svc.detail(treatment)


@router.post("/{treatment_id}/commit")
def commit_owner(treatment_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _svc(session, user)
    treatment = svc.get(treatment_id)
    svc.commit_owner(treatment)
    return svc.detail(treatment)


@router.post("/{treatment_id}/checkins", status_code=201)
def add_checkin(
    treatment_id: str, payload: CheckinRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    treatment = svc.get(treatment_id)
    svc.add_checkin(treatment, payload.model_dump())
    return svc.detail(treatment)


@router.post("/{treatment_id}/approvals", status_code=201)
def request_approval(
    treatment_id: str, payload: ApprovalRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    treatment = svc.get(treatment_id)
    svc.request_approval(treatment, payload.model_dump(exclude_none=True))
    return svc.detail(treatment)


@router.post("/{treatment_id}/approvals/{approval_id}/decide")
def decide_approval(
    treatment_id: str,
    approval_id: str,
    payload: DecisionRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    svc = _svc(session, user)
    treatment = svc.get(treatment_id)
    svc.decide_approval(approval_id, payload.decision, payload.notes)
    return svc.detail(treatment)


@router.post("/{treatment_id}/transition")
def transition_treatment(
    treatment_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    treatment = svc.get(treatment_id)
    result = svc.transition(treatment, payload.target, reason=payload.reason)
    return {"transition": result, "treatment": svc.detail(treatment)}
