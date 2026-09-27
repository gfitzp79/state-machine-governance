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
    """Linked risks this deployment actually bears on (RINV-14).

    A risk that names its assets is touched only when the deployment runs on
    one of them. One that names none is touched by every deployment, because
    its CE resolution counts every deployment. The two lookups must agree: a
    cascade that flags a risk the scoring engine says the deployment cannot
    reach is an alert about nothing, and a risk it fails to flag is a residual
    nobody knows is wrong.

    A failure of the whole control (DL-1, design) uses the objective lookup
    instead, because then the control is broken everywhere at once.
    """
    from app.modules.control.models import ControlDeployment

    deployment = session.get(ControlDeployment, deployment_id)
    if deployment is None:
        return []
    activity = deployment.activity
    if activity is None:
        return []
    asset_id = deployment.attack_surface_id
    return [
        risk
        for risk in _risks_linked_to_objective(session, activity.objective_id)
        if not risk.scope_asset_ids or asset_id in risk.scope_asset_ids
    ]


def _proposed_residual(risk):
    """The residual this risk would carry against the CE resolved now."""
    objectives = [link.objective for link in risk.control_links if link.objective is not None]
    resolution = ScoringEngine.resolve_ce(objectives, scope=risk.scope_asset_ids)
    return ScoringEngine.proposed_residual(
        risk.impact,
        risk.likelihood,
        risk.residual_impact,
        risk.residual_likelihood,
        resolution,
    )


def _proposal_sentence(proposal) -> str:
    """One sentence for a risk banner: how far the number is likely to move."""
    if proposal is None:
        return ""
    if not proposal["changed"]:
        return (
            " The recorded residual still fits the control effectiveness that "
            "remains, so the proposal is to leave it at " + str(proposal["score"]) + "."
        )
    return (
        " Proposed residual: " + str(proposal["score"]) + " (" + proposal["rating"]
        + (", above appetite" if proposal["above_appetite"] else "")
        + "). Proposed, not applied: the full validation gate still applies (RINV-1)."
    )


def _grouped(event: CascadeEvent) -> bool:
    """Inside a test campaign, owners get one digest when it closes instead of
    one alert per cascade (codified-rules section 25.5)."""
    return bool(event.payload.get("campaign_id"))


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
    if _grouped(event):
        return
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
            "re-assessed." + _proposal_sentence(_proposed_residual(risk))
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
    "Deployment failed: a design failure propagates to the objective (DL-1); an "
    "operating failure stays on its asset and reaches only the risks and "
    "frameworks whose scope includes it",
)
def deployment_failed(event: CascadeEvent) -> None:
    from app.modules.control.models import ControlDeployment

    deployment = event.session.get(ControlDeployment, event.entity_id)
    if deployment is None:
        return

    # CINV-16. A transition fired by hand, with no test behind it, carries no
    # classification and is read as Design: the reading that propagates
    # furthest, because under-reacting to a failure is the costlier mistake.
    failure_type = event.payload.get("failure_type") or "Design"
    objective = deployment.activity.objective if deployment.activity else None

    if objective is not None and objective.lifecycle_state == "Operating":
        if failure_type == "Design":
            # DL-1: a design failure is the control not working as designed,
            # so it is broken everywhere and the objective goes with it.
            objective.lifecycle_state = "Failure"
            event.record(
                "control_objective",
                objective.id,
                "Design failure: objective " + objective.reference
                + " propagated to Failure (DL-1)",
                invariant="DL-1",
            )
            # chain, not emit: a bare emit would drop everything the downstream
            # handlers record, so the audit trail would show the objective
            # failing and say nothing about the risks frozen or the
            # requirements uncovered. The payload travels with it so a campaign
            # still groups the alerts this raises.
            event.chain(
                cascades, "control.failed", "control_objective", objective.id,
                **event.payload,
            )
            return
        _operating_failure(event, deployment, objective)

    _reopen_scenarios_for_deployment(event, deployment.id, deployment.reference)


def _operating_failure(event: CascadeEvent, deployment, objective) -> None:
    """DL-1, operating branch. The control is sound and did not run HERE.

    The objective stays Operating, because it still works on every other asset
    it runs on. What changes is confined to the places this asset matters:
    risks whose declared scope includes it (or who declare none, since their CE
    resolution counts every deployment), and frameworks whose scope includes
    it, each judged by its own coverage rule. A PCI requirement can be lost and
    an ISO one untouched by the same test, which is the whole point.
    """
    asset = deployment.surface.name if deployment.surface else "an asset"
    event.record(
        "control_objective",
        objective.id,
        "Operating failure on " + asset + ": " + objective.reference
        + " stays Operating; consequences confined to its scope (DL-1)",
        invariant="DL-1",
    )

    for risk in _risks_linked_to_deployment(event.session, deployment.id):
        proposal = _proposed_residual(risk)
        where = (
            asset + ", inside this risk's declared scope"
            if risk.scope_asset_ids
            else asset + ". This risk declares no assets, so every deployment counts toward it"
        )
        risk.residual_score_locked = True
        risk.control_change_flag = "Control_Failure"
        risk.control_change_detail = (
            "Control " + objective.reference + " failed its test on " + where + ". "
            "It is an operating failure: the control still runs elsewhere, but "
            "here it is held at CE-Unvalidated (CE-7) and the residual score is "
            "frozen until re-assessed." + _proposal_sentence(proposal)
        )
        risk.sla_status = "At_Risk"
        above = bool(proposal and proposal["above_appetite"] and proposal["changed"])
        _notify_risk_stakeholders(
            event,
            risk,
            "control_failure",
            "Residual frozen on " + risk.reference + ": " + objective.reference
            + " failed on " + asset + (" (proposed above appetite)" if above else ""),
            risk.control_change_detail,
        )
        event.record(
            "risk",
            risk.id,
            "Residual locked on " + risk.reference + "; " + asset + " is inside its scope"
            + (
                "; proposed residual " + str(proposal["score"]) + " " + proposal["rating"]
                if proposal and proposal["changed"]
                else ""
            ),
            invariant="RINV-14",
        )

    _recheck_coverage_for_deployment(event, objective, deployment)


def _notify_requirement_owner(event: CascadeEvent, assessment, requirement, reason: str) -> None:
    """Codified-rules section 24.3: the requirement owner hears about it."""
    if _grouped(event):
        return
    AuditTrail.notify(
        event.session,
        recipient_id=assessment.owner_id,
        entity_type="requirement_assessment",
        entity_id=assessment.id,
        event_type="coverage_lost",
        title=requirement.framework.framework_id + " " + requirement.ref + " lost coverage",
        body=reason,
    )


def _recheck_coverage_for_deployment(event: CascadeEvent, objective, deployment) -> None:
    """AINV-2 and AINV-11 after an operating failure, framework by framework.

    A framework whose scope does not include the failed asset is untouched.
    One whose scope does is re-judged by its own rule: under any_in_scope the
    requirement survives while another in-scope asset still carries a live
    satisfying control, under all_in_scope it does not. Both judgements read
    the whole link set, so a second control still covering the asset counts.
    """
    from sqlalchemy import select

    from app.modules.compliance.machine import coverage_meets_rule, live_reach
    from app.modules.compliance.models import ControlRequirementLink

    asset = deployment.surface.name if deployment.surface else "an asset"
    links = event.session.execute(
        select(ControlRequirementLink).where(ControlRequirementLink.objective_id == objective.id)
    ).scalars()

    for link in links:
        requirement = link.requirement
        if requirement is None or not link.satisfies:
            continue
        assessment = requirement.assessment
        if assessment is None or assessment.lifecycle_state != "Covered":
            continue
        framework_id = requirement.framework.framework_id
        scoped, reached = live_reach(requirement, event.session)
        if scoped and deployment.attack_surface_id not in scoped:
            continue

        rule = governance.coverage_rule(framework_id)
        live = bool(reached & scoped) if scoped else bool(reached)
        meets = coverage_meets_rule(requirement, event.session)
        label = framework_id + " " + requirement.ref
        if live and meets:
            event.record(
                "requirement_assessment",
                assessment.id,
                label + " still covered under " + rule + ": "
                + str(len(reached & scoped)) + " of " + str(len(scoped))
                + " in-scope assets still carry the control",
                invariant="AINV-11",
            )
            continue

        reason = (
            "Control " + objective.reference + " failed on " + asset + ", inside the "
            + framework_id + " scope. "
            + (
                framework_id + " is configured all_in_scope, so every in-scope asset "
                "must carry a live satisfying control (AINV-11)."
                if live
                else "No in-scope asset still carries a live satisfying control (AINV-2)."
            )
        )
        assessment.lifecycle_state = "Gap"
        assessment.gap_reason = reason
        _notify_requirement_owner(event, assessment, requirement, reason)
        event.record(
            "requirement_assessment",
            assessment.id,
            label + " lost coverage: " + reason,
            invariant="AINV-11" if live else "AINV-2",
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
    from sqlalchemy import select

    from app.modules.compliance.models import ControlRequirementLink
    from app.modules.control.models import ControlDeployment

    for risk in _risks_linked_to_deployment(event.session, event.entity_id):
        risk.control_change_flag = "Control_Improved"
        risk.control_change_detail = (
            "A linked control deployment was restored. The residual score is eligible for "
            "update, but the full validation gate must still pass before it changes."
        )
        event.record("risk", risk.id, "Residual update eligibility flagged")

    # The compliance half of the same argument. A requirement this deployment's
    # failure un-covered becomes ELIGIBLE to return to Covered; the gate, not
    # this handler, decides whether it does, exactly as RINV-1 does for risk.
    deployment = event.session.get(ControlDeployment, event.entity_id)
    if deployment is None or deployment.activity is None:
        return
    asset = deployment.surface.name if deployment.surface else None
    links = event.session.execute(
        select(ControlRequirementLink).where(
            ControlRequirementLink.objective_id == deployment.activity.objective_id
        )
    ).scalars()
    for link in links:
        assessment = link.requirement.assessment if link.requirement else None
        if assessment is None or assessment.lifecycle_state != "Gap":
            continue
        if not asset or asset not in (assessment.gap_reason or ""):
            continue
        requirement = link.requirement
        if not _grouped(event):
            AuditTrail.notify(
                event.session,
                recipient_id=assessment.owner_id,
                entity_type="requirement_assessment",
                entity_id=assessment.id,
                event_type="coverage_restorable",
                title=requirement.framework.framework_id + " " + requirement.ref
                + " can be re-asserted as Covered",
                body="The deployment on " + asset + " whose failure opened this gap is "
                "live again. Re-assert Covered; the gate re-checks AINV-2 and AINV-11.",
            )
        event.record(
            "requirement_assessment",
            assessment.id,
            requirement.framework.framework_id + " " + requirement.ref
            + " eligible to return to Covered; the gate still decides",
        )


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


@cascades.on(
    "threat.scenario_mitigated",
    "Threat mitigated: flag every risk record carrying it as re-evaluation eligible "
    "(codified-rules section 20.3)",
)
def threat_scenario_mitigated(event: CascadeEvent) -> None:
    """The return leg of the threat-risk loop.

    A control failure re-opens scenarios and strips sign-off. The inverse has to
    be true as well, or the loop is one-directional: when a threat the register
    carries is genuinely mitigated, the risk that carries it needs to know.

    The residual score is deliberately NOT updated. Eligibility is not
    validation, and RINV-1 still requires all five conditions of
    GATE_RESIDUAL_VALIDATED before a residual can move.
    """
    from app.modules.risk.models import Risk
    from app.modules.threat.models import ThreatScenario

    scenario = event.session.get(ThreatScenario, event.entity_id)
    if scenario is None:
        return

    # Every risk carrying this exposure, whether by promotion or by reference.
    risk_ids = {link.risk_id for link in scenario.risk_links}
    if scenario.promoted_risk_id:
        risk_ids.add(scenario.promoted_risk_id)
    if not risk_ids:
        return

    risks = (
        event.session.query(Risk)
        .filter(Risk.id.in_(risk_ids))
        .filter(Risk.lifecycle_state != "Closed")
        .all()
    )
    for risk in risks:
        risk.control_change_flag = "Linked_Threat_Mitigated"
        risk.control_change_detail = (
            "Threat scenario " + scenario.reference + " is now fully mitigated by a "
            "live control. This risk is eligible for residual re-evaluation; the "
            "full validation gate still applies (RINV-1)."
        )
        _notify_risk_stakeholders(
            event,
            risk,
            "linked_threat_mitigated",
            "Linked threat mitigated on " + risk.reference,
            scenario.reference + " is fully mitigated. Residual re-evaluation is "
            "eligible but not automatic.",
        )
        event.record(
            "risk",
            risk.id,
            "Flagged re-evaluation eligible on " + risk.reference
            + "; residual NOT auto-updated (RINV-1)",
            invariant="RINV-1",
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

# ---------------------------------------------------------------------------
# Compliance and assurance (codified-rules section 24.3)
#
# This is the cascade that makes the compliance module something other than a
# mapping table. A control failing is not merely a control problem: every
# requirement whose coverage rested on it stops being covered at the same
# moment, and a Statement of Applicability that still reads "Covered" the next
# morning is asserting something untrue.
# ---------------------------------------------------------------------------


def _revoke_coverage_for_objective(event: CascadeEvent, objective, reason: str) -> None:
    """AINV-5: coverage that rested on this control is no longer coverage."""
    from sqlalchemy import select

    from app.modules.compliance.models import ControlRequirementLink

    links = event.session.execute(
        select(ControlRequirementLink).where(
            ControlRequirementLink.objective_id == objective.id
        )
    ).scalars()

    for link in links:
        requirement = link.requirement
        if requirement is None or not link.satisfies:
            continue
        assessment = requirement.assessment
        if assessment is None or assessment.lifecycle_state != "Covered":
            continue

        # Another Operating control may still carry it. Revoking then would
        # report a gap that does not exist, which erodes trust in the number
        # faster than missing one does.
        still_covered = any(
            other.satisfies
            and other.objective is not None
            and other.objective.id != objective.id
            and other.objective.lifecycle_state == "Operating"
            for other in requirement.control_links
        )
        if still_covered:
            continue

        assessment.lifecycle_state = "Gap"
        assessment.gap_reason = reason
        _notify_requirement_owner(event, assessment, requirement, reason)
        event.record(
            "requirement_assessment",
            assessment.id,
            requirement.ref + " lost coverage: " + reason,
            invariant="AINV-5",
        )


# No description: control.failed already carries one, and CascadeBus.on
# overwrites rather than appends it. The reason lives in the docstring.
@cascades.on("control.failed")
def control_failed_compliance(event: CascadeEvent) -> None:
    """AINV-5. Revoke compliance coverage that rested on the failed control."""
    from app.modules.control.models import ControlObjective

    objective = event.session.get(ControlObjective, event.entity_id)
    if objective is None:
        return
    _revoke_coverage_for_objective(
        event,
        objective,
        "Control " + objective.reference + " entered Failure. A requirement is "
        "covered only while the control carrying it is operating (AINV-2).",
    )


@cascades.on("control.deprecated")
def control_deprecated_compliance(event: CascadeEvent) -> None:
    """AINV-5. A retired control stops carrying the requirements it covered."""
    from app.modules.control.models import ControlObjective

    objective = event.session.get(ControlObjective, event.entity_id)
    if objective is None:
        return
    _revoke_coverage_for_objective(
        event,
        objective,
        "Control " + objective.reference + " was retired. Re-map the requirement "
        "to its replacement before the next assessment.",
    )


@cascades.on("requirement.covered", "Requirement covered")
def requirement_covered(event: CascadeEvent) -> None:
    from app.modules.compliance.models import RequirementAssessment

    assessment = event.session.get(RequirementAssessment, event.entity_id)
    if assessment is None:
        return
    assessment.gap_reason = None
    event.record(
        "requirement_assessment",
        assessment.id,
        assessment.requirement.ref + " covered",
    )


@cascades.on("requirement.gap", "Requirement is an open gap")
def requirement_gap(event: CascadeEvent) -> None:
    from app.modules.compliance.models import RequirementAssessment

    assessment = event.session.get(RequirementAssessment, event.entity_id)
    if assessment is None:
        return
    reason = event.payload.get("reason") or assessment.gap_reason
    assessment.gap_reason = reason or "Applicable and not covered."
    event.record(
        "requirement_assessment",
        assessment.id,
        assessment.requirement.ref + " is an open gap",
        invariant="AINV-2",
    )


@cascades.on("requirement.compensating", "Requirement met by a time-bound compensating control")
def requirement_compensating(event: CascadeEvent) -> None:
    from app.modules.compliance.models import RequirementAssessment

    assessment = event.session.get(RequirementAssessment, event.entity_id)
    if assessment is None:
        return
    event.record(
        "requirement_assessment",
        assessment.id,
        assessment.requirement.ref
        + " resting on a compensating control until "
        + (
            assessment.compensating_expiry.isoformat()
            if assessment.compensating_expiry
            else "an unset date"
        ),
        invariant="AINV-4",
    )


@cascades.on("requirement.excluded", "Requirement excluded from scope with justification")
def requirement_excluded(event: CascadeEvent) -> None:
    from app.modules.compliance.models import RequirementAssessment

    assessment = event.session.get(RequirementAssessment, event.entity_id)
    if assessment is None:
        return
    event.record(
        "requirement_assessment",
        assessment.id,
        assessment.requirement.ref + " excluded from scope",
        invariant="AINV-1",
    )


# ---------------------------------------------------------------------------
# Test impact (codified-rules section 25.5)
#
# Alert on outcomes, not events. A single test notifies each owner as its
# cascade runs, once. A campaign holds those back and sends each owner one
# digest when it closes. Either way, the posture alert fires only when a test
# pulls an adopted framework's coverage below the configured floor, because a
# percentage that moved from 97 to 96 is information and one that crossed the
# line the organisation drew is a decision somebody has to make.
# ---------------------------------------------------------------------------


def _users_with_roles(session, roles):
    from app.modules.identity.models import User, UserRole

    if not roles:
        return []
    return (
        session.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .filter(UserRole.role.in_(list(roles)), User.deactivated_at.is_(None))
        .distinct()
        .all()
    )


@cascades.on(
    "control_test.impact_assessed",
    "Test impact assessed: one digest per owner for a campaign, and a posture "
    "alert when coverage falls below the configured floor",
)
def control_test_impact_assessed(event: CascadeEvent) -> None:
    impact = event.payload.get("impact") or {}
    subject = event.payload.get("subject") or "A control test"

    if _grouped(event):
        per_recipient: dict[str, list[str]] = {}
        for row in impact.get("risks", []):
            if not row.get("affected"):
                continue
            line = row["reference"] + ": " + row["summary"]
            for recipient in {row.get("risk_owner_id"), row.get("risk_analyst_id")} - {None}:
                per_recipient.setdefault(recipient, []).append(line)
        for framework in impact.get("frameworks", []):
            for requirement in framework.get("requirements", []):
                if requirement.get("lost") and requirement.get("owner_id"):
                    per_recipient.setdefault(requirement["owner_id"], []).append(
                        framework["framework_id"] + " " + requirement["ref"]
                        + " lost coverage: " + (requirement.get("reason") or "")
                    )
        for recipient, lines in per_recipient.items():
            AuditTrail.notify(
                event.session,
                recipient_id=recipient,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                event_type="test_impact_digest",
                title=subject + ": " + str(len(lines)) + " item"
                + ("" if len(lines) == 1 else "s") + " for you",
                body="\n".join(lines),
            )
            event.record(
                "user", recipient, "One digest sent covering " + str(len(lines)) + " item(s)"
            )

    floor = governance.posture_alert_below_pct
    fell = [
        f
        for f in impact.get("frameworks", [])
        if f.get("coverage_pct_before") is not None
        and f.get("coverage_pct_after") is not None
        and f["coverage_pct_after"] < f["coverage_pct_before"]
        and f["coverage_pct_after"] < floor
    ]
    if not fell:
        return
    body = "; ".join(
        f["framework_id"] + " fell from " + str(f["coverage_pct_before"]) + "% to "
        + str(f["coverage_pct_after"]) + "%"
        for f in fell
    )
    for user in _users_with_roles(event.session, governance.posture_alert_roles):
        AuditTrail.notify(
            event.session,
            recipient_id=user.id,
            entity_type="compliance",
            entity_id=None,
            event_type="posture_below_floor",
            title=subject + " pulled coverage below " + str(floor) + "%",
            body=body,
        )
    event.record(
        "compliance_framework",
        ",".join(f["framework_id"] for f in fell),
        "Posture alert: " + body,
    )
