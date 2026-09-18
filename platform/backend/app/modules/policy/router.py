"""Policy API: policies, standards, exceptions."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.governance import governance
from app.core.security import CurrentUser, DbSession
from app.modules.policy.machine import POLICY_EXCEPTION_MACHINE, POLICY_MACHINE
from app.modules.policy.models import (
    ANNUAL_AUDIT_FRAMEWORKS,
    POLICY_TYPES,
    REVIEW_CYCLES,
)
from app.modules.policy.service import (
    ExceptionService,
    PolicyService,
    StandardService,
    summarise_exception,
    summarise_policy,
)

router = APIRouter(prefix="/policies", tags=["policies"])
exceptions_router = APIRouter(prefix="/exceptions", tags=["exceptions"])


class PolicyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    policy_type: str = "Information_Security"
    scope: str | None = None
    purpose: str | None = None
    body: str | None = None
    review_cycle: str = "Annual"
    effective_date: date | None = None
    compliance_mappings: list[str] = []
    policy_owner_id: str | None = None


class PolicyUpdate(BaseModel):
    title: str | None = None
    policy_type: str | None = None
    scope: str | None = None
    purpose: str | None = None
    body: str | None = None
    version: str | None = None
    review_cycle: str | None = None
    effective_date: date | None = None
    compliance_mappings: list[str] | None = None
    policy_owner_id: str | None = None
    change_summary: str | None = None


class ApproveRequest(BaseModel):
    approver_id: str


class LinkRequest(BaseModel):
    id: str


class TransitionRequest(BaseModel):
    target: str
    reason: str | None = None
    version: str | None = None


class ExceptionCreate(BaseModel):
    policy_id: str
    title: str
    business_justification: str
    risk_statement: str | None = None
    compensating_controls: str | None = None
    expiry_date: date


class ExceptionUpdate(BaseModel):
    title: str | None = None
    business_justification: str | None = None
    risk_statement: str | None = None
    compensating_controls: str | None = None
    expiry_date: date | None = None
    approved_by: str | None = None
    rejection_rationale: str | None = None


class StandardCreate(BaseModel):
    title: str
    parent_policy_id: str | None = None
    scope: str | None = None
    body: str | None = None
    compliance_mappings: list[str] = []


@router.get("")
def list_policies(
    session: DbSession, user: CurrentUser, state: str | None = None
) -> list[dict[str, Any]]:
    svc = PolicyService(session, user.id, user.role_names)
    rows = [summarise_policy(p) for p in svc.list(lifecycle_state=state)]
    rows.sort(key=lambda r: r["reference"])
    return rows


@router.post("", status_code=201)
def create_policy(payload: PolicyCreate, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = PolicyService(session, user.id, user.role_names)
    return svc.detail(svc.create_policy(payload.model_dump(exclude_none=True)))


@router.get("/machine")
def policy_machine() -> dict[str, Any]:
    return {
        "policy": POLICY_MACHINE.describe(),
        "exception": POLICY_EXCEPTION_MACHINE.describe(),
    }


@router.get("/reference-data")
def reference_data() -> dict[str, Any]:
    return {
        "policy_types": list(POLICY_TYPES),
        "review_cycles": list(REVIEW_CYCLES),
        "annual_audit_frameworks": list(ANNUAL_AUDIT_FRAMEWORKS),
        "frameworks": list(governance.compliance_frameworks),
        "exception_max_days": governance.exception_max_days,
        "exception_extended_max_days": governance.exception_extended_max_days,
    }


@router.post("/standards", status_code=201)
def create_standard(
    payload: StandardCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = StandardService(session, user.id, user.role_names)
    std = svc.create_standard(payload.model_dump(exclude_none=True))
    return {"id": std.id, "reference": std.reference, "title": std.title}


@router.get("/{policy_id}")
def get_policy(policy_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = PolicyService(session, user.id, user.role_names)
    return svc.detail(svc.get(policy_id))


@router.patch("/{policy_id}")
def update_policy(
    policy_id: str, payload: PolicyUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = PolicyService(session, user.id, user.role_names)
    policy = svc.get(policy_id)
    svc.update_policy(policy, payload.model_dump(exclude_unset=True))
    return svc.detail(policy)


@router.post("/{policy_id}/approve")
def approve_policy(
    policy_id: str, payload: ApproveRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = PolicyService(session, user.id, user.role_names)
    policy = svc.get(policy_id)
    svc.approve(policy, payload.approver_id)
    return svc.detail(policy)


@router.post("/{policy_id}/controls")
def link_control(
    policy_id: str, payload: LinkRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = PolicyService(session, user.id, user.role_names)
    policy = svc.get(policy_id)
    svc.link_control(policy, payload.id)
    return svc.detail(policy)


@router.delete("/{policy_id}/controls/{link_id}")
def unlink_control(
    policy_id: str, link_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = PolicyService(session, user.id, user.role_names)
    policy = svc.get(policy_id)
    svc.unlink_control(policy, link_id)
    return svc.detail(policy)


@router.post("/{policy_id}/transition")
def transition_policy(
    policy_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = PolicyService(session, user.id, user.role_names)
    policy = svc.get(policy_id)
    result = svc.transition(
        policy, payload.target, reason=payload.reason, version=payload.version
    )
    return {"transition": result, "policy": svc.detail(policy)}


# -- exceptions ------------------------------------------------------------


@exceptions_router.get("")
def list_exceptions(
    session: DbSession, user: CurrentUser, state: str | None = None
) -> list[dict[str, Any]]:
    svc = ExceptionService(session, user.id, user.role_names)
    rows = [summarise_exception(e) for e in svc.list(lifecycle_state=state)]
    rows.sort(key=lambda r: r["expiry_date"])
    return rows


@exceptions_router.post("", status_code=201)
def create_exception(
    payload: ExceptionCreate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ExceptionService(session, user.id, user.role_names)
    return svc.detail(svc.create_exception(payload.model_dump(exclude_none=True)))


@exceptions_router.get("/{exception_id}")
def get_exception(exception_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = ExceptionService(session, user.id, user.role_names)
    return svc.detail(svc.get(exception_id))


@exceptions_router.patch("/{exception_id}")
def update_exception(
    exception_id: str, payload: ExceptionUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ExceptionService(session, user.id, user.role_names)
    exc = svc.get(exception_id)
    svc.apply(exc, payload.model_dump(exclude_unset=True))
    session.commit()
    return svc.detail(exc)


@exceptions_router.post("/{exception_id}/transition")
def transition_exception(
    exception_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = ExceptionService(session, user.id, user.role_names)
    exc = svc.get(exception_id)
    result = svc.transition(exc, payload.target, reason=payload.reason)
    return {"transition": result, "exception": svc.detail(exc)}
