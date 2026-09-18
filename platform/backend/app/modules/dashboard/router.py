"""Dashboard, engine introspection, and the scheduled governance jobs.

The engine endpoints serve the live machine definitions and invariant catalogue
straight out of the running registry, so the UI renders the specification as the
system actually implements it rather than a copy that can drift.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.core.governance import governance
from app.core.security import CurrentUser, DbSession
from app.engine import cascades, invariants
from app.engine.scoring import RATING_BANDS, ScoringEngine
from app.modules.control.machine import (
    CONTROL_ACTIVITY_MACHINE,
    CONTROL_DEPLOYMENT_MACHINE,
    CONTROL_OBJECTIVE_MACHINE,
)
from app.modules.control.models import ControlDeployment, ControlObjective
from app.modules.policy.machine import POLICY_EXCEPTION_MACHINE, POLICY_MACHINE
from app.modules.policy.models import Policy, PolicyException
from app.modules.risk.machine import RISK_MACHINE
from app.modules.risk.models import RISK_PHASES, Risk
from app.modules.threat.machine import THREAT_MODEL_MACHINE
from app.modules.threat.models import ThreatModel, ThreatScenario
from app.modules.treatment.machine import TREATMENT_MACHINE
from app.modules.treatment.models import Treatment

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    risks = session.execute(select(Risk)).scalars().all()
    open_risks = [r for r in risks if r.lifecycle_state != "Closed"]
    objectives = session.execute(select(ControlObjective)).scalars().all()
    deployments = session.execute(select(ControlDeployment)).scalars().all()
    policies = session.execute(select(Policy)).scalars().all()
    exceptions = session.execute(select(PolicyException)).scalars().all()
    treatments = session.execute(select(Treatment)).scalars().all()
    models = session.execute(select(ThreatModel)).scalars().all()
    scenarios = session.execute(select(ThreatScenario)).scalars().all()

    by_rating = {rating: 0 for _, _, rating in RATING_BANDS}
    for risk in open_risks:
        rating = risk.reported_rating
        if rating in by_rating:
            by_rating[rating] += 1

    by_phase = {name: 0 for name in RISK_PHASES}
    for risk in open_risks:
        if risk.lifecycle_state in by_phase:
            by_phase[risk.lifecycle_state] += 1

    heatmap: dict[str, int] = {}
    for risk in open_risks:
        impact = risk.residual_impact if not risk.residual_score_locked else risk.impact
        likelihood = (
            risk.residual_likelihood if not risk.residual_score_locked else risk.likelihood
        )
        if impact and likelihood:
            key = str(impact) + "x" + str(likelihood)
            heatmap[key] = heatmap.get(key, 0) + 1

    today = date.today()
    soon = today + timedelta(days=30)

    return {
        "risk": {
            "total": len(risks),
            "open": len(open_risks),
            "by_rating": by_rating,
            "by_phase": by_phase,
            "above_appetite": sum(
                1 for r in open_risks if ScoringEngine.is_above_appetite(r.reported_rating)
            ),
            "residual_locked": sum(1 for r in open_risks if r.residual_score_locked),
            "escalated": sum(1 for r in open_risks if r.escalation_flag),
            "control_changed": sum(1 for r in open_risks if r.control_change_flag),
            "review_overdue": sum(
                1 for r in open_risks if r.next_review_date and r.next_review_date < today
            ),
            "acceptances_expiring": sum(
                1
                for r in open_risks
                if r.acceptance_expiry_date and today <= r.acceptance_expiry_date <= soon
            ),
            "heatmap": heatmap,
        },
        "control": {
            "objectives": len(objectives),
            "operating": sum(1 for o in objectives if o.lifecycle_state == "Operating"),
            "in_failure": sum(1 for o in objectives if o.lifecycle_state == "Failure"),
            "deployments": len(deployments),
            "deployments_failed": sum(
                1 for d in deployments if d.deployment_status == "Failed"
            ),
            "deployments_degraded": sum(
                1 for d in deployments if d.deployment_status == "Degraded"
            ),
            "ce_expired": sum(
                1
                for d in deployments
                if d.deployment_status in ("Active", "Degraded")
                and ScoringEngine.ce_expired(d.ce_assessed_at, d.test_frequency)
            ),
            "tests_overdue": sum(
                1 for d in deployments if d.next_test_due and d.next_test_due < today
            ),
        },
        "policy": {
            "total": len(policies),
            "active": sum(1 for p in policies if p.lifecycle_state == "Active"),
            "under_revision": sum(1 for p in policies if p.lifecycle_state == "Under_Revision"),
            "review_overdue": sum(
                1 for p in policies if p.next_review_date and p.next_review_date < today
            ),
            "realignment_pending": sum(p.realignment_pending for p in policies),
            "exceptions_active": sum(1 for e in exceptions if e.lifecycle_state == "Approved"),
            "exceptions_expiring": sum(
                1
                for e in exceptions
                if e.lifecycle_state == "Approved" and 0 <= e.days_to_expiry <= 30
            ),
            "exceptions_overdue": sum(
                1 for e in exceptions if e.lifecycle_state == "Approved" and e.days_to_expiry < 0
            ),
        },
        "treatment": {
            "total": len(treatments),
            "in_progress": sum(1 for t in treatments if t.lifecycle_state == "In_Progress"),
            "complete": sum(1 for t in treatments if t.lifecycle_state == "Complete"),
            "awaiting_validation": sum(1 for t in treatments if not t.grc_eng_validated),
            "awaiting_commitment": sum(
                1 for t in treatments if t.grc_eng_validated and not t.owner_committed
            ),
            "overdue": sum(
                1
                for t in treatments
                if t.target_date and t.target_date < today and t.lifecycle_state != "Complete"
            ),
        },
        "threat": {
            "models": len(models),
            "active": sum(1 for m in models if m.lifecycle_state == "Active"),
            "in_review": sum(1 for m in models if m.lifecycle_state == "Review"),
            "scenarios": len(scenarios),
            "unresolved": sum(1 for s in scenarios if s.status == "Identified"),
            "mitigated": sum(1 for s in scenarios if s.status == "Mitigated"),
            "promoted": sum(1 for s in scenarios if s.status == "Promoted_To_Risk"),
            "reopened": sum(1 for s in scenarios if s.reopened_at is not None),
        },
    }


@router.get("/config")
def governance_config() -> dict[str, Any]:
    # The whole configured operating model, served unauthenticated so the
    # sign-in page can carry the organisation's name. Contains no data, only
    # the taxonomy and thresholds from config/governance.yml.
    return governance.public()


@router.get("/engine/machines")
def machines() -> dict[str, Any]:
    """Every lifecycle in the platform, as the engine holds it."""
    return {
        "risk": RISK_MACHINE.describe(),
        "control_objective": CONTROL_OBJECTIVE_MACHINE.describe(),
        "control_activity": CONTROL_ACTIVITY_MACHINE.describe(),
        "control_deployment": CONTROL_DEPLOYMENT_MACHINE.describe(),
        "policy": POLICY_MACHINE.describe(),
        "policy_exception": POLICY_EXCEPTION_MACHINE.describe(),
        "treatment": TREATMENT_MACHINE.describe(),
        "threat_model": THREAT_MODEL_MACHINE.describe(),
    }


@router.get("/engine/invariants")
def invariant_catalogue() -> dict[str, Any]:
    """The live catalogue. Every entry here is evaluated on writes to its entity."""
    catalogue = invariants.catalogue()
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for item in catalogue:
        by_entity.setdefault(item["entity"], []).append(item)
    return {"total": len(catalogue), "by_entity": by_entity, "all": catalogue}


@router.get("/engine/cascades")
def cascade_registry() -> dict[str, Any]:
    return {"events": cascades.registered()}


@router.get("/engine/scoring")
def scoring_model() -> dict[str, Any]:
    from app.engine.scoring import (
        ACCEPTANCE_RULES,
        CE_EXPIRY_MONTHS,
        CE_MAX_LIKELIHOOD_REDUCTION,
        REVIEW_CADENCE_DAYS,
    )

    return {
        "matrix": ScoringEngine.matrix(),
        "bands": [
            {"min": lo, "max": hi, "rating": r, "appetite": governance.appetite.get(r)}
            for lo, hi, r in RATING_BANDS
        ],
        "ce_likelihood_reduction": CE_MAX_LIKELIHOOD_REDUCTION,
        "ce_expiry_months": CE_EXPIRY_MONTHS,
        "acceptance_rules": ACCEPTANCE_RULES,
        "review_cadence_days": REVIEW_CADENCE_DAYS,
        "source": "config/governance.yml",
    }


@router.post("/engine/jobs/run")
def run_scheduled_jobs(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """The time-based invariants: CE expiry, acceptance expiry, exception expiry,
    SLA breach. In production these run on a scheduler; exposing them here makes
    them observable and testable rather than invisible background behaviour."""
    from app.modules.jobs import run_all

    return run_all(session, actor_id=user.id)
