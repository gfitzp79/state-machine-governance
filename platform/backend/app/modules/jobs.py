"""Scheduled governance jobs.

These implement the time-based invariants, the ones that cannot be enforced
per-transaction because nothing happens at the moment they become true. An
acceptance does not expire because someone saved a record; it expires because a
date passed.

RINV-11  expired acceptances escalate; no silent expiry
CINV-10  expired control effectiveness auto-downgrades to CE-Unvalidated
PE-4     exceptions within 30 days of expiry notify the owner
PE-5     exceptions past expiry are flagged as governance gaps
CINV-5   controls in Failure for more than 15 business days escalate to the CISO
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.governance import governance
from app.engine import AuditTrail, cascades
from app.engine.scoring import ScoringEngine
from app.modules.control.models import ControlDeployment, ControlObjective
from app.modules.policy.models import PolicyException
from app.modules.risk.models import Risk, RiskControlLink


def expire_control_effectiveness(session: Session, actor_id: str | None = None) -> list[str]:
    """CINV-10. No manual override exists, by design."""
    downgraded: list[str] = []
    deployments = session.execute(select(ControlDeployment)).scalars().all()
    for dep in deployments:
        if dep.ce_rating == "CE-Unvalidated":
            continue
        if dep.deployment_status not in ("Active", "Degraded"):
            continue
        if not ScoringEngine.ce_expired(dep.ce_assessed_at, dep.test_frequency):
            continue
        previous = dep.ce_rating
        dep.ce_rating = "CE-Unvalidated"
        dep.ce_notes = (
            "Auto-downgraded from " + previous + " on " + date.today().isoformat()
            + ": evidence expired per the "
            + dep.test_frequency
            + " cadence (CINV-10)."
        )
        AuditTrail.record(
            session,
            actor_id=None,
            entity_type="control_deployment",
            entity_id=dep.id,
            action="CE_EXPIRED",
            changed_fields={"from": previous, "to": "CE-Unvalidated", "invariant": "CINV-10"},
        )
        cascades.emit("deployment.degraded", session, "control_deployment", dep.id, actor_id)
        downgraded.append(dep.reference)
    return downgraded


def escalate_expired_acceptances(session: Session, actor_id: str | None = None) -> list[str]:
    """RINV-11."""
    escalated: list[str] = []
    risks = (
        session.execute(
            select(Risk)
            .where(Risk.treatment_strategy == "Accept")
            .where(Risk.lifecycle_state != "Closed")
        )
        .scalars()
        .all()
    )
    for risk in risks:
        if risk.acceptance_expiry_date is None:
            continue
        if risk.acceptance_expiry_date >= date.today():
            continue
        if risk.escalation_flag:
            continue
        risk.escalation_flag = True
        risk.sla_status = "Breached"
        risk.escalation_reason = (
            "Acceptance expired on "
            + risk.acceptance_expiry_date.isoformat()
            + ". Escalation path: Risk Owner, then Risk Stakeholder, then CISO (RINV-11)."
        )
        risk.acceptance_reassessment_count += 1
        risk.residual_score_locked = True
        for recipient in {risk.risk_owner_id, risk.risk_stakeholder_id, risk.risk_analyst_id}:
            AuditTrail.notify(
                session,
                recipient_id=recipient,
                entity_type="risk",
                entity_id=risk.id,
                event_type="acceptance_expired",
                title="Acceptance expired on " + risk.reference,
                body="The risk is now above appetite and requires re-assessment.",
            )
        AuditTrail.record(
            session,
            actor_id=None,
            entity_type="risk",
            entity_id=risk.id,
            action="ACCEPTANCE_EXPIRED",
            changed_fields={
                "expiry": risk.acceptance_expiry_date.isoformat(),
                "invariant": "RINV-11",
            },
        )
        escalated.append(risk.reference)
    return escalated


def expire_policy_exceptions(session: Session, actor_id: str | None = None) -> dict[str, list[str]]:
    """PE-4 and PE-5."""
    expired: list[str] = []
    notified: list[str] = []
    exceptions = (
        session.execute(
            select(PolicyException).where(PolicyException.lifecycle_state == "Approved")
        )
        .scalars()
        .all()
    )
    for exc in exceptions:
        days = exc.days_to_expiry
        if days < 0:
            exc.lifecycle_state = "Expired"
            AuditTrail.record(
                session,
                actor_id=None,
                entity_type="policy_exception",
                entity_id=exc.id,
                action="EXCEPTION_EXPIRED",
                changed_fields={"expiry": exc.expiry_date.isoformat(), "invariant": "PE-5"},
            )
            cascades.emit(
                "exception.expired", session, "policy_exception", exc.id, actor_id
            )
            expired.append(exc.reference)
        elif days <= governance.exception_expiry_warning_days:
            AuditTrail.notify(
                session,
                recipient_id=exc.requested_by,
                entity_type="policy_exception",
                entity_id=exc.id,
                event_type="exception_expiring",
                title=exc.reference + " expires in " + str(days) + " days",
                body="Renew or allow it to lapse. An unrenewed expiry is a governance gap.",
            )
            notified.append(exc.reference)
    return {"expired": expired, "notified": notified}


def escalate_prolonged_control_failures(
    session: Session, actor_id: str | None = None
) -> list[str]:
    """CINV-5 cascade step 4: failure persisting beyond 15 business days."""
    escalated: list[str] = []
    cutoff = date.today() - timedelta(days=governance.control_failure_escalation_days)
    objectives = (
        session.execute(
            select(ControlObjective).where(ControlObjective.lifecycle_state == "Failure")
        )
        .scalars()
        .all()
    )
    for obj in objectives:
        if obj.failure_declared_at is None:
            continue
        if obj.failure_declared_at.date() > cutoff:
            continue
        if obj.remediation_plan:
            continue
        links = (
            session.execute(
                select(RiskControlLink).where(RiskControlLink.objective_id == obj.id)
            )
            .scalars()
            .all()
        )
        risk_ids = [link.risk_id for link in links]
        risks = (
            session.execute(select(Risk).where(Risk.id.in_(risk_ids))).scalars().all()
            if risk_ids
            else []
        )
        for risk in risks:
            risk.escalation_flag = True
            risk.escalation_reason = (
                "Linked control " + obj.reference + " has been in Failure for more than "
                + str(governance.control_failure_escalation_days)
                + " days with no remediation plan (CINV-5)."
            )
        AuditTrail.record(
            session,
            actor_id=None,
            entity_type="control_objective",
            entity_id=obj.id,
            action="FAILURE_ESCALATED",
            changed_fields={"invariant": "CINV-5", "linked_risks": len(risks)},
        )
        escalated.append(obj.reference)
    return escalated


def refresh_risk_sla(session: Session, actor_id: str | None = None) -> list[str]:
    """Review cadence tracking for risks in monitoring."""
    breached: list[str] = []
    risks = (
        session.execute(select(Risk).where(Risk.lifecycle_state == "Monitoring"))
        .scalars()
        .all()
    )
    for risk in risks:
        if risk.next_review_date is None:
            risk.next_review_date = ScoringEngine.next_review_date(risk.reported_rating)
            continue
        days_over = (date.today() - risk.next_review_date).days
        if days_over > 0:
            risk.sla_status = "Breached"
            breached.append(risk.reference)
        elif days_over > -7:
            risk.sla_status = "At_Risk"
        else:
            risk.sla_status = "On_Track"
    return breached


def run_all(session: Session, actor_id: str | None = None) -> dict[str, Any]:
    result = {
        "ce_expired": expire_control_effectiveness(session, actor_id),
        "acceptances_escalated": escalate_expired_acceptances(session, actor_id),
        "exceptions": expire_policy_exceptions(session, actor_id),
        "control_failures_escalated": escalate_prolonged_control_failures(session, actor_id),
        "sla_breached": refresh_risk_sla(session, actor_id),
    }
    session.commit()
    return result
