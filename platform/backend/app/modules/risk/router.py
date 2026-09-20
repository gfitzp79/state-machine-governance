"""Risk API."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.governance import TREATMENT_STRATEGIES, governance
from app.core.security import CurrentUser, DbSession
from app.modules.risk.machine import RISK_MACHINE
from app.modules.risk.models import INTAKE_SOURCES, RISK_TIERS, Risk
from app.modules.risk.service import RiskService, summarise

router = APIRouter(prefix="/risks", tags=["risks"])


def _service(session, user) -> RiskService:
    return RiskService(session, user.id, user.role_names)


# -- payloads --------------------------------------------------------------


class RiskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=300)
    cause: str | None = None
    threat_event: str | None = None
    vulnerability: str | None = None
    impact_statement: str | None = None
    intake_source: str | None = None
    identified_by: str | None = None
    tier: str | None = None
    tier_rationale: str | None = None
    risk_owner_id: str | None = None
    risk_stakeholder_id: str | None = None
    risk_analyst_id: str | None = None


class RiskUpdate(BaseModel):
    # extra="forbid": a field this schema does not know is dropped silently
    # by default, so a client still sending a removed precondition field
    # would get 200 and no change. Three Phase 2 attestations were removed
    # in favour of derived values, and a stale client should be told.
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    cause: str | None = None
    threat_event: str | None = None
    vulnerability: str | None = None
    impact_statement: str | None = None
    intake_source: str | None = None
    identified_by: str | None = None
    tier: str | None = None
    tier_rationale: str | None = None
    risk_owner_id: str | None = None
    risk_stakeholder_id: str | None = None
    risk_analyst_id: str | None = None
    pre_true_risk_confirmed: bool | None = None
    gate_mitigations_implemented: bool | None = None
    gate_evidence_provided: bool | None = None
    gate_effectiveness_confirmed: bool | None = None
    gate_governance_approved: bool | None = None
    gate_drift_tracked: bool | None = None
    evidence_ref: str | None = None
    readout_confirmed: bool | None = None
    readout_conducted_at: Any | None = None
    readout_adjustment_rationale: str | None = None
    escalation_flag: bool | None = None
    escalation_reason: str | None = None
    closure_rationale: str | None = None


class InherentScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    impact: int = Field(ge=1, le=5)
    likelihood: int = Field(ge=1, le=5)
    impact_justification: str | None = None
    likelihood_justification: str | None = None


class ResidualScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    residual_impact: int = Field(ge=1, le=5)
    residual_likelihood: int = Field(ge=1, le=5)
    residual_impact_rationale: str | None = None
    residual_likelihood_rationale: str | None = None


class TreatmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    treatment_strategy: str
    acceptance_expiry_date: date | None = None
    acceptance_rationale: str | None = None
    acceptance_approved_by: str | None = None
    transfer_description: str | None = None
    avoidance_description: str | None = None
    partial_treatment_rationale: str | None = None
    control_framework_mapping: str | None = None


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    reason: str | None = None
    treatments_proposed: int | None = None


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    is_primary: bool = False


class CommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
    parent_comment_id: str | None = None


# -- routes ----------------------------------------------------------------


@router.get("")
def list_risks(
    session: DbSession,
    user: CurrentUser,
    state: str | None = Query(None),
    rating: str | None = Query(None),
    owner: str | None = Query(None),
    above_appetite: bool | None = Query(None),
) -> list[dict[str, Any]]:
    from app.engine.scoring import ScoringEngine

    svc = _service(session, user)
    risks = svc.list(lifecycle_state=state, risk_owner_id=owner)
    rows = [summarise(r) for r in risks]
    if rating:
        rows = [r for r in rows if r["reported_rating"] == rating]
    if above_appetite:
        rows = [r for r in rows if ScoringEngine.is_above_appetite(r["reported_rating"])]
    rows.sort(key=lambda r: (-(r["reported_score"] or 0), r["reference"]))
    return rows


@router.post("", status_code=201)
def create_risk(payload: RiskCreate, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.create_risk(payload.model_dump(exclude_none=True))
    return svc.detail(risk)


@router.get("/machine")
def risk_machine(user: CurrentUser) -> dict[str, Any]:
    return RISK_MACHINE.describe()


@router.get("/reference-data")
def reference_data(user: CurrentUser) -> dict[str, Any]:
    from app.engine.scoring import ACCEPTANCE_RULES, RATING_BANDS, ScoringEngine

    return {
        "tiers": list(RISK_TIERS),
        "tier_detail": governance.risk_tier_detail,
        "intake_sources": list(INTAKE_SOURCES),
        "strategies": list(TREATMENT_STRATEGIES),
        "rating_bands": [
            {"min": lo, "max": hi, "rating": r} for lo, hi, r in RATING_BANDS
        ],
        "acceptance_rules": ACCEPTANCE_RULES,
        "matrix": ScoringEngine.matrix(),
    }


@router.get("/{risk_id}")
def get_risk(risk_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _service(session, user)
    return svc.detail(svc.get(risk_id))


@router.patch("/{risk_id}")
def update_risk(
    risk_id: str, payload: RiskUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.apply(risk, payload.model_dump(exclude_unset=True))
    session.commit()
    return svc.detail(risk)


@router.post("/{risk_id}/score/inherent")
def score_inherent(
    risk_id: str, payload: InherentScore, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.score_inherent(
        risk,
        payload.impact,
        payload.likelihood,
        impact_justification=payload.impact_justification,
        likelihood_justification=payload.likelihood_justification,
    )
    return svc.detail(risk)


@router.post("/{risk_id}/score/residual")
def score_residual(
    risk_id: str, payload: ResidualScore, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.score_residual(
        risk,
        payload.residual_impact,
        payload.residual_likelihood,
        residual_impact_rationale=payload.residual_impact_rationale,
        residual_likelihood_rationale=payload.residual_likelihood_rationale,
    )
    return svc.detail(risk)


@router.get("/{risk_id}/ce-resolution")
def ce_resolution(risk_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Shows exactly which controls counted toward the score and which did not,
    with the rule that excluded each one."""
    svc = _service(session, user)
    risk = svc.get(risk_id)
    return {
        **svc.resolve_ce(risk).as_dict(),
        # Without this the panel cannot tell "scope matched everything" from
        # "no scope declared, so nothing was filtered".
        "scope_declared": bool(risk.asset_links),
        "scope_assets": [
            {"id": l.attack_surface_id, "name": getattr(l.surface, "name", None)}
            for l in risk.asset_links
        ],
    }


@router.post("/{risk_id}/residual/unlock")
def unlock_residual(risk_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.release_residual_lock(risk)
    return svc.detail(risk)


@router.post("/{risk_id}/treatment-decision")
def treatment_decision(
    risk_id: str, payload: TreatmentDecision, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.set_treatment_decision(risk, payload.model_dump(exclude_none=True))
    return svc.detail(risk)


@router.get("/{risk_id}/gates")
def gates(risk_id: str, session: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    svc = _service(session, user)
    return svc.gate_report(svc.get(risk_id))


@router.post("/{risk_id}/transition")
def transition(
    risk_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    result = svc.transition(risk, payload.target, **payload.model_dump(exclude={"target"}))
    return {"transition": result, "risk": svc.detail(risk)}


@router.post("/{risk_id}/assets")
def link_asset(
    risk_id: str, payload: LinkRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    """Name an asset this risk concerns (RINV-14)."""
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.link_asset(risk, payload.id)
    return svc.detail(risk)


@router.delete("/{risk_id}/assets/{attack_surface_id}")
def unlink_asset(
    risk_id: str, attack_surface_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.unlink_asset(risk, attack_surface_id)
    return svc.detail(risk)


@router.post("/{risk_id}/controls")
def link_control(
    risk_id: str, payload: LinkRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.link_control(risk, payload.id)
    return svc.detail(risk)


@router.delete("/{risk_id}/controls/{link_id}")
def unlink_control(
    risk_id: str, link_id: str, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.unlink_control(risk, link_id)
    return svc.detail(risk)


@router.post("/{risk_id}/treatments")
def link_treatment(
    risk_id: str, payload: LinkRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.link_treatment(risk, payload.id, payload.is_primary)
    return svc.detail(risk)


@router.post("/{risk_id}/policies")
def link_policy(
    risk_id: str, payload: LinkRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.link_policy(risk, payload.id)
    return svc.detail(risk)


@router.post("/{risk_id}/comments", status_code=201)
def add_comment(
    risk_id: str, payload: CommentRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _service(session, user)
    risk = svc.get(risk_id)
    svc.add_comment(risk, payload.body, payload.parent_comment_id)
    return svc.detail(risk)
