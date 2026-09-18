"""Cross-lifecycle cascade handlers.

This module is deliberately the only place where one module reaches into
another's state. Everything here implements a specific row from the cascade rules
table in the state transitions specification.

The behaviour that matters most: a control entering Failure does not just record
a failure. It re-locks the residual score on every risk whose score that control
was reducing, and it re-opens every threat scenario that control was mitigating,
which in turn strips the sign-off from the threat model. That chain is the whole
argument for modelling governance as connected state machines.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.governance import governance
from app.core.model_base import utcnow
from app.engine import AuditTrail, CascadeEvent, cascades
from app.engine.scoring import CE_DEGRADATION_SLA_DAYS, ScoringEngine

# -- lookup helpers --------------------------------------------------------


def _risks_linked_to_objective(session, objective_id: str):
    from app.modules.risk.models import Risk, RiskControlLink

    links = session.query(RiskControlLink).filter(
        RiskControlLink.objective_id == objective_id
    ).all()
    if not links:
        return []
    return (
        session.query(Risk)
        .filter(Risk.id.in_([link.risk_id for link in links]))
        .filter(Risk.lifecycle_state != "Closed")
        .all()
    )


def _risks_linked_to_deployment(session, deployment_id: str):
    from app.modules.control.models import ControlDeployment

    deployment = session.get(ControlDeployment, deployment_id)
    if deployment is None:
        return []
    activity = deployment.activity
    if activity is None:
        return []
    return _risks_linked_to_objective(session, activity.objective_id)


def _scenarios_mitigated_by_deployment(session, deployment_id: str):
    from app.modules.threat.models import ThreatMitigationLink, ThreatScenario

    links = session.query(ThreatMitigationLink).filter(
        ThreatMitigationLink.deployment_id == deployment_id
    ).all()
    if not links:
        return []
    return (
        session.query(ThreatScenario)
        .filter(ThreatScenario.id.in_([link.scenario_id for link in links]))
        .all()
    )


def _notify_risk_stakeholders(event: CascadeEvent, risk, event_type: str, title: str, body: str):
    for recipient in {risk.risk_analyst_id, risk.risk_owner_id}:
        AuditTrail.notify(
            event.session,
            recipient_id=recipient,
            entity_type="risk",
            entity_id=risk.id,
            event_type=event_type,
            title=title,
            body=body,
        )


# -- Control -> Risk -------------------------------------------------------


@cascades.on(
    "control.failed",
    "Control objective entered Failure: freeze residual on every linked risk (CINV-5)",
)
def control_failed(event: CascadeEvent) -> None:
    from app.modules.control.models import ControlObjective

    objective = event.session.get(ControlObjective, event.entity_id)
    if objective is None:
        return
    objective.failure_declared_at = objective.failure_declared_at or utcnow()

    for risk in _risks_linked_to_objective(event.session, objective.id):
        risk.residual_score_locked = True
        risk.control_change_flag = "Control_Failure"
        risk.control_change_detail = (
            "Control " + objective.reference + " (" + objective.title + ") entered Failure. "
            "Residual score is frozen until the control is remediated or the linkage is "
            "re-assessed."
        )
        risk.sla_status = "At_Risk"
        _notify_risk_stakeholders(
            event,
            risk,
            "control_failure",
            "Residual frozen on " + risk.reference,
            "Linked control " + objective.reference + " is in Failure.",
        )
        event.record(
            "risk",
            risk.id,
            "Residual score locked and re-evaluation flagged on " + risk.reference,
            invariant="CINV-5",
        )

    # The same failure propagates into threat management via the deployments.
    for activity in objective.activities:
        for deployment in activity.deployments:
            _reopen_scenarios_for_deployment(event, deployment.id, objective.reference)


@cascades.on("control.recovered", "Control returned to Operating: clear the failure flag")
def control_recovered(event: CascadeEvent) -> None:
    from app.modules.control.models import ControlObjective

    objective = event.session.get(ControlObjective, event.entity_id)
    if objective is None:
        return
    objective.failure_declared_at = None

    for risk in _risks_linked_to_objective(event.session, objective.id):
        if risk.control_change_flag == "Control_Failure":
            risk.control_change_flag = "Control_Improved"
            risk.control_change_detail = (
                "Control " + objective.reference + " returned to Operating. The residual "
                "score is eligible for update once the full validation gate passes again."
            )
            event.record(
                "risk",
                risk.id,
                "Re-evaluation eligibility flagged on " + risk.reference,
            )


@cascades.on(
    "control.deprecated", "Control retired: linked risks require re-assessment within 30 days"
)
def control_deprecated(event: CascadeEvent) -> None:
    from app.modules.control.models import ControlObjective

    objective = event.session.get(ControlObjective, event.entity_id)
    if objective is None:
        return
    for risk in _risks_linked_to_objective(event.session, objective.id):
        risk.control_change_flag = "Control_Retired"
        risk.control_change_detail = (
            "Control " + objective.reference + " was retired. Re-assess this risk within "
            + str(governance.control_retirement_reassessment_days)
            + " days if the control was contributing to the residual score."
        )
        reassess_by = date.today() + timedelta(
            days=governance.control_retirement_reassessment_days
        )
        risk.next_review_date = min(
            filter(None, [risk.next_review_date, reassess_by])
        )
        _notify_risk_stakeholders(
            event,
            risk,
            "control_retired",
            "Re-assessment required on " + risk.reference,
            "Linked control " + objective.reference + " has been retired.",
        )
        event.record(
            "risk",
            risk.id,
            "Re-assessment required within "
            + str(governance.control_retirement_reassessment_days)
            + " days",
        )


@cascades.on(
    "deployment.failed",
    "Deployment failed: propagate to the parent objective (DL-1) and re-open threat scenarios",
)
def deployment_failed(event: CascadeEvent) -> None:
    from app.modules.control.models import ControlDeployment

    deployment = event.session.get(ControlDeployment, event.entity_id)
    if deployment is None:
        return

    objective = deployment.activity.objective if deployment.activity else None
    if objective is not None and objective.lifecycle_state == "Operating":
        # DL-1: a failed deployment takes the objective with it.
        objective.lifecycle_state = "Failure"
        event.record(
            "control_objective",
            objective.id,
            "Objective " + objective.reference + " propagated to Failure (DL-1)",
            invariant="DL-1",
        )
        cascades.emit(
            "control.failed",
            event.session,
            "control_objective",
            objective.id,
            event.actor_id,
        )
    else:
        _reopen_scenarios_for_deployment(
            event, deployment.id, deployment.reference
        )


@cascades.on(
    "deployment.degraded",
    "CE degradation: flag linked risks for re-evaluation with a rating-based SLA",
)
def deployment_degraded(event: CascadeEvent) -> None:
    for risk in _risks_linked_to_deployment(event.session, event.entity_id):
        sla_days = CE_DEGRADATION_SLA_DAYS.get(risk.reported_rating or "Moderate", 20)
        risk.control_change_flag = "Control_Changed"
        risk.control_change_detail = (
            "A linked control deployment degraded. Re-evaluation is required within "
            + str(sla_days)
            + " business days."
        )
        risk.residual_score_locked = True
        _notify_risk_stakeholders(
            event,
            risk,
            "ce_degradation",
            "Control changed: re-evaluation required on " + risk.reference,
            "Re-evaluate within " + str(sla_days) + " business days.",
        )
        event.record(
            "risk",
            risk.id,
            "Re-evaluation flagged with a " + str(sla_days) + " business day SLA",
        )


@cascades.on(
    "deployment.restored",
    "CE improvement: linked risks become eligible for a residual update, gate still applies",
)
def deployment_restored(event: CascadeEvent) -> None:
    for risk in _risks_linked_to_deployment(event.session, event.entity_id):
        risk.control_change_flag = "Control_Improved"
        risk.control_change_detail = (
            "A linked control deployment was restored. The residual score is eligible for "
            "update, but the full validation gate must still pass before it changes."
        )
        event.record("risk", risk.id, "Residual update eligibility flagged")


@cascades.on(
    "deployment.decommissioned",
    "Decommission preserves risk-control linkages read-only and notifies (CINV-9)",
)
def deployment_decommissioned(event: CascadeEvent) -> None:
    for risk in _risks_linked_to_deployment(event.session, event.entity_id):
        risk.control_change_flag = "Deployment_Decommissioned"
        risk.control_change_detail = (
            "A control deployment this risk relies on was decommissioned. The linkage is "
            "preserved for audit; re-map or close it explicitly."
        )
        risk.residual_score_locked = True
        event.record("risk", risk.id, "Linkage preserved read-only; re-assessment required")
    _reopen_scenarios_for_deployment(event, event.entity_id, "decommissioned deployment")


@cascades.on("control.operating", "Control reached Operating")
def control_operating(event: CascadeEvent) -> None:
    for risk in _risks_linked_to_objective(event.session, str(event.entity_id)):
        risk.control_change_flag = "Control_Improved"
        risk.control_change_detail = (
            "A linked control reached Operating state and now contributes to scoring."
        )
        event.record("risk", risk.id, "Control now contributes to scoring")


# -- Control -> Threat -----------------------------------------------------


def _reopen_scenarios_for_deployment(event: CascadeEvent, deployment_id: str, source: str) -> None:
    """TINV-4: a scenario is only Mitigated while its control is live. When the
    control stops being live the scenario re-opens and the model loses sign-off."""
    from app.modules.threat.models import ThreatModel

    for scenario in _scenarios_mitigated_by_deployment(event.session, deployment_id):
        if scenario.status != "Mitigated":
            continue
        scenario.status = "Identified"
        scenario.reopened_reason = (
            "Mitigating control " + source + " is no longer operational (TINV-4)."
        )
        scenario.reopened_at = utcnow()
        event.record(
            "threat_scenario",
            scenario.id,
            "Scenario " + scenario.reference + " re-opened to Identified",
            invariant="TINV-4",
        )

        model = event.session.get(ThreatModel, scenario.threat_model_id)
        if model is not None and model.lifecycle_state == "Active":
            model.lifecycle_state = "Review"
            model.appsec_signoff_by = None
            model.appsec_signoff_at = None
            model.owner_signoff_by = None
            model.owner_signoff_at = None
            model.signoff_stripped_reason = (
                "Mitigating control " + source + " failed. Sign-off stripped pending rework."
            )
            AuditTrail.notify(
                event.session,
                recipient_id=model.system_owner_id,
                entity_type="threat_model",
                entity_id=model.id,
                event_type="threat_model_reopened",
                title="Threat model " + model.reference + " returned to Review",
                body="A control mitigating one of its scenarios is no longer operational.",
            )
            event.record(
                "threat_model",
                model.id,
                "Model " + model.reference + " returned to Review; sign-offs stripped",
                invariant="TINV-2",
            )


@cascades.on("threat_model.reopened", "Threat model returned to Review: strip both sign-offs")
def threat_model_reopened(event: CascadeEvent) -> None:
    from app.modules.threat.models import ThreatModel

    model = event.session.get(ThreatModel, event.entity_id)
    if model is None:
        return
    model.appsec_signoff_by = None
    model.appsec_signoff_at = None
    model.owner_signoff_by = None
    model.owner_signoff_at = None
    model.signoff_stripped_reason = event.payload.get("reason", "Model returned to review.")
    event.record("threat_model", model.id, "Sign-offs stripped", invariant="TINV-2")


@cascades.on("threat_model.activated", "Threat model signed off and active")
def threat_model_activated(event: CascadeEvent) -> None:
    event.record("threat_model", event.entity_id, "Threat model is now Active")


# -- Policy -> Control -----------------------------------------------------


@cascades.on(
    "policy.revision_opened",
    "Policy revision: linked controls flagged for re-alignment within 30 days (PINV-7)",
)
def policy_revision_opened(event: CascadeEvent) -> None:
    from app.modules.policy.models import Policy

    policy = event.session.get(Policy, event.entity_id)
    if policy is None:
        return
    due = date.today() + timedelta(days=governance.policy_realignment_days)
    policy.realignment_due = due
    policy.realignment_pending = len(policy.control_links)
    for link in policy.control_links:
        link.realignment_required = True
        link.realignment_due = due
        objective = link.objective
        if objective is not None:
            AuditTrail.notify(
                event.session,
                recipient_id=objective.control_owner_id,
                entity_type="control_objective",
                entity_id=objective.id,
                event_type="policy_revision",
                title="Alignment check required on " + objective.reference,
                body=(
                    "Policy " + policy.reference + " is under revision. Confirm alignment "
                    "by " + due.isoformat() + "."
                ),
            )
            event.record(
                "control_objective",
                objective.id,
                "Alignment confirmation required by " + due.isoformat(),
                invariant="PINV-7",
            )


@cascades.on(
    "policy.deprecated",
    "Policy deprecated: linked controls flagged for re-mapping within 60 days (PINV-3)",
)
def policy_deprecated(event: CascadeEvent) -> None:
    from app.modules.policy.models import Policy

    policy = event.session.get(Policy, event.entity_id)
    if policy is None:
        return
    due = date.today() + timedelta(days=governance.policy_remapping_days)
    policy.realignment_due = due
    policy.realignment_pending = len(policy.control_links)
    for link in policy.control_links:
        link.realignment_required = True
        link.realignment_due = due
        event.record(
            "control_objective",
            link.objective_id,
            "Re-mapping to a surviving policy required by " + due.isoformat(),
            invariant="PINV-3",
        )


@cascades.on("policy.activated", "Policy activated: set the next review date")
def policy_activated(event: CascadeEvent) -> None:
    from app.modules.policy.models import Policy

    policy = event.session.get(Policy, event.entity_id)
    if policy is None:
        return
    months = 12 if policy.review_cycle == "Annual" else 24
    policy.next_review_date = date.today() + timedelta(days=months * 30)
    policy.realignment_pending = 0
    for link in policy.control_links:
        link.realignment_required = False
    event.record(
        "policy", policy.id, "Next review scheduled for " + policy.next_review_date.isoformat()
    )


# -- Policy exception ------------------------------------------------------


@cascades.on(
    "exception.approved",
    "Exception without compensating controls escalates for risk promotion (PE-2)",
)
def exception_approved(event: CascadeEvent) -> None:
    from app.modules.policy.models import Policy, PolicyException

    exception = event.session.get(PolicyException, event.entity_id)
    if exception is None:
        return
    policy = event.session.get(Policy, exception.policy_id)
    if policy is not None:
        policy.exception_count = policy.active_exception_count
        # A policy carrying more than five exceptions is a revision trigger.
        if (
            policy.exception_count > governance.exception_review_trigger_count
            and policy.lifecycle_state == "Active"
        ):
            AuditTrail.notify(
                event.session,
                recipient_id=policy.policy_owner_id,
                entity_type="policy",
                entity_id=policy.id,
                event_type="policy_review_trigger",
                title="Review trigger on " + policy.reference,
                body=(
                    str(policy.exception_count)
                    + " active exceptions. Unscheduled review required."
                ),
            )
            event.record(
                "policy", policy.id, "Unscheduled review triggered by exception volume"
            )

    if not exception.compensating_controls:
        AuditTrail.notify(
            event.session,
            recipient_id=exception.requested_by,
            entity_type="policy_exception",
            entity_id=exception.id,
            event_type="exception_promotion_assessment",
            title="Risk promotion assessment required for " + exception.reference,
            body="This exception has no compensating controls recorded (PE-2).",
        )
        event.record(
            "policy_exception",
            exception.id,
            "No compensating controls: escalated for risk register promotion assessment",
            invariant="PE-2",
        )


@cascades.on("exception.expired", "Expired exception without renewal is a governance gap (PE-5)")
def exception_expired(event: CascadeEvent) -> None:
    from app.modules.policy.models import Policy, PolicyException

    exception = event.session.get(PolicyException, event.entity_id)
    if exception is None:
        return
    policy = event.session.get(Policy, exception.policy_id)
    if policy is not None:
        policy.exception_count = policy.active_exception_count
    event.record(
        "policy_exception",
        exception.id,
        "Exception expired; governance gap flagged and CISO notified",
        invariant="PE-5",
    )


# -- Treatment -> Risk -----------------------------------------------------


@cascades.on(
    "treatment.completed",
    "Treatment complete: re-evaluate residual gate condition 1 on every linked risk",
)
def treatment_completed(event: CascadeEvent) -> None:
    from app.modules.risk.models import Risk, RiskTreatmentLink
    from app.modules.treatment.models import Treatment

    treatment = event.session.get(Treatment, event.entity_id)
    if treatment is None:
        return
    treatment.completed_at = treatment.completed_at or utcnow()

    links = event.session.query(RiskTreatmentLink).filter(
        RiskTreatmentLink.treatment_id == treatment.id
    ).all()
    for link in links:
        risk = event.session.get(Risk, link.risk_id)
        if risk is None:
            continue
        all_complete = all(l.treatment.is_complete for l in risk.treatment_links)
        risk.gate_mitigations_implemented = all_complete
        if all_complete:
            _notify_risk_stakeholders(
                event,
                risk,
                "treatments_complete",
                "All treatments complete on " + risk.reference,
                "Residual gate condition 1 is now satisfied. Four conditions remain.",
            )
            event.record(
                "risk",
                risk.id,
                "Residual gate condition 1 satisfied on " + risk.reference,
            )
        else:
            event.record(
                "risk",
                risk.id,
                "Treatment complete; other treatments on " + risk.reference + " still open",
            )


@cascades.on("treatment.cancelled", "Treatment cancelled: linked risks lose gate condition 1")
def treatment_cancelled(event: CascadeEvent) -> None:
    from app.modules.risk.models import Risk, RiskTreatmentLink

    links = event.session.query(RiskTreatmentLink).filter(
        RiskTreatmentLink.treatment_id == event.entity_id
    ).all()
    for link in links:
        risk = event.session.get(Risk, link.risk_id)
        if risk is None:
            continue
        risk.gate_mitigations_implemented = False
        risk.residual_score_locked = True
        event.record(
            "risk", risk.id, "Residual re-locked on " + risk.reference + "; treatment cancelled"
        )


# -- Risk internal ---------------------------------------------------------


@cascades.on("risk.admitted", "Risk admitted to the register: start the owner assignment SLA")
def risk_admitted(event: CascadeEvent) -> None:
    event.record("risk", event.entity_id, "Risk admitted; owner assignment SLA started")


@cascades.on("risk.inherent_locked", "Inherent score frozen once the risk leaves Scoring (OUT-5)")
def risk_inherent_locked(event: CascadeEvent) -> None:
    from app.modules.risk.models import Risk

    risk = event.session.get(Risk, event.entity_id)
    if risk is None:
        return
    risk.inherent_locked = True
    event.record("risk", risk.id, "Inherent score locked for this assessment cycle")


@cascades.on("risk.readout_queued", "Risk queued for the next governance forum")
def risk_readout_queued(event: CascadeEvent) -> None:
    from app.modules.risk.models import Risk

    risk = event.session.get(Risk, event.entity_id)
    if risk is None:
        return
    AuditTrail.notify(
        event.session,
        recipient_id=risk.risk_owner_id,
        entity_type="risk",
        entity_id=risk.id,
        event_type="readout_queued",
        title=risk.reference + " is queued for governance readout",
        body="Confirm the treatment plan at the next forum.",
    )
    event.record("risk", risk.id, "Queued for governance readout; Risk Owner notified")


@cascades.on("risk.monitoring_started", "Risk entered monitoring: set the review cadence")
def risk_monitoring_started(event: CascadeEvent) -> None:
    from app.modules.risk.models import Risk

    risk = event.session.get(Risk, event.entity_id)
    if risk is None:
        return
    risk.next_review_date = ScoringEngine.next_review_date(risk.reported_rating)
    risk.control_change_flag = None
    risk.control_change_detail = None
    risk.sla_status = "On_Track"
    if risk.next_review_date:
        event.record(
            "risk",
            risk.id,
            "Review cadence set; next review " + risk.next_review_date.isoformat(),
        )


@cascades.on("risk.reassessment_started", "Risk returned for re-assessment: unlock a new cycle")
def risk_reassessment_started(event: CascadeEvent) -> None:
    from app.modules.risk.models import Risk

    risk = event.session.get(Risk, event.entity_id)
    if risk is None:
        return
    risk.reassessment_count += 1
    risk.inherent_locked = False
    risk.residual_score_locked = True
    # A new cycle re-opens the residual gate from scratch.
    risk.gate_mitigations_implemented = False
    risk.gate_evidence_provided = False
    risk.gate_effectiveness_confirmed = False
    risk.gate_governance_approved = False
    risk.gate_drift_tracked = False
    risk.readout_confirmed = False
    event.record(
        "risk",
        risk.id,
        "Assessment cycle " + str(risk.reassessment_count + 1) + " opened; residual re-locked",
    )


@cascades.on("risk.closed", "Risk closed")
def risk_closed(event: CascadeEvent) -> None:
    from app.modules.risk.models import Risk

    risk = event.session.get(Risk, event.entity_id)
    if risk is None:
        return
    risk.closed_at = risk.closed_at or utcnow()
    risk.closed_by = risk.closed_by or event.actor_id
    risk.escalation_flag = False
    event.record("risk", risk.id, "Risk closed")
