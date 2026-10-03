"""What a repair sets in motion (codified-rules 10.3).

Registered on the shared bus beside the handlers in modules/cascades.py, not
inside them, so the failure and recovery cascades there are left untouched.
"""

from __future__ import annotations

from sqlalchemy import select

from app.engine import AuditTrail, CascadeEvent, cascades


@cascades.on(
    "deployment.repaired",
    "Deployment repaired and back in service: open an effectiveness review (REV-1)",
)
def open_effectiveness_review(event: CascadeEvent) -> None:
    """REV-1: a control back in service is not yet a control that works.

    Fired by the two repair transitions only, Degraded to Active and Failed to
    Active. A rising CE rating emits deployment.restored too, and is not a
    repair, so it is not this event."""
    from app.modules.control.models import ControlDeployment
    from app.modules.review.service import ReviewService, control_editors

    dep = event.session.get(ControlDeployment, event.entity_id)
    if dep is None or dep.deployment_status != "Active":
        return
    svc = ReviewService(event.session, event.actor_id)
    review = svc.open_for(dep, trigger="Restored to Active")
    if review is None:
        return
    obj = dep.activity.objective if dep.activity else None
    asset = dep.surface.name if dep.surface else "its asset"
    recipients = list(dict.fromkeys(
        [*control_editors(event.session), getattr(obj, "control_owner_id", None)]
    ))
    for recipient in recipients:
        AuditTrail.notify(
            event.session,
            recipient_id=recipient,
            entity_type="control_review",
            entity_id=review.id,
            event_type="control_review_opened",
            title=review.reference + ": retest " + (obj.reference if obj else "the control")
            + " on " + asset,
            body=(
                "It is back in service. Show that it works by recording a passing test by "
                + review.due_date.isoformat()
                + ". Nothing that depends on it is told to re-assess until you do."
            ),
        )
    event.record(
        "control_review", review.id,
        "Effectiveness review " + review.reference + " opened; due " + review.due_date.isoformat(),
        invariant="REV-1",
    )


@cascades.on(
    "control_review.completed",
    "Repaired control proven by retest: prompt everything that depends on it to re-assess",
)
def review_completed(event: CascadeEvent) -> None:
    """REV-3: tell each dependant, in the terms of its own lifecycle.

    Nothing is changed on their behalf. A risk's residual is re-earned by
    re-assessing it, a threat scenario is re-mitigated by AppSec, a requirement
    is re-covered through its own gate. The engine's job is to make sure the
    people who own those decisions know the control is back.
    """
    from app.modules.compliance.models import ControlRequirementLink, RequirementAssessment
    from app.modules.review.models import ControlReview
    from app.modules.risk.models import Risk, RiskControlLink
    from app.modules.threat.models import ThreatMitigationLink, ThreatModel

    review = event.session.get(ControlReview, event.entity_id)
    if review is None:
        return
    dep = review.deployment
    obj = review.objective
    asset_id = dep.attack_surface_id if dep else None
    asset = dep.surface.name if dep and dep.surface else "its asset"
    label = (obj.reference if obj else "A control") + " on " + asset

    # Risks: linked to the control, and concerned with this asset or with no
    # declared asset at all (RINV-14).
    risks = event.session.execute(
        select(Risk).join(RiskControlLink, RiskControlLink.risk_id == Risk.id).where(
            RiskControlLink.objective_id == review.objective_id,
            Risk.lifecycle_state != "Closed",
        )
    ).scalars().unique().all()
    prompted = 0
    for risk in risks:
        scope = risk.scope_asset_ids
        if scope and asset_id not in scope:
            continue
        prompted += 1
        risk.control_change_flag = "Control_Recovered"
        risk.control_change_detail = (
            label + " passed its retest (" + review.reference + "). Re-assess to earn back "
            "the residual reduction it supports."
        )
        for recipient in dict.fromkeys([risk.risk_analyst_id, risk.risk_owner_id]):
            AuditTrail.notify(
                event.session,
                recipient_id=recipient,
                entity_type="risk",
                entity_id=risk.id,
                event_type="control_recovered",
                title="Re-assess " + risk.reference + ": " + label + " works again",
                body=risk.control_change_detail,
            )

    # Threat scenarios this deployment mitigates and that are still open.
    links = event.session.execute(
        select(ThreatMitigationLink).where(ThreatMitigationLink.deployment_id == review.deployment_id)
    ).scalars().all()
    scenarios = [l.scenario for l in links if l.scenario and l.scenario.status == "Identified"]
    for scenario in scenarios:
        model = event.session.get(ThreatModel, scenario.threat_model_id)
        for recipient in dict.fromkeys(
            [getattr(model, "appsec_partner_id", None), getattr(model, "system_owner_id", None)]
        ):
            AuditTrail.notify(
                event.session,
                recipient_id=recipient,
                entity_type="threat_scenario",
                entity_id=scenario.id,
                event_type="control_recovered",
                title="Re-confirm " + scenario.reference + ": " + label + " works again",
                body="The mitigation was reopened when the control failed. It passed its "
                "retest; confirm the mitigation and re-sign the model.",
            )

    # Requirements this control evidences that sit in Gap.
    gaps = event.session.execute(
        select(RequirementAssessment).join(
            ControlRequirementLink,
            ControlRequirementLink.requirement_id == RequirementAssessment.requirement_id,
        ).where(
            ControlRequirementLink.objective_id == review.objective_id,
            RequirementAssessment.lifecycle_state == "Gap",
        )
    ).scalars().unique().all()
    for assessment in gaps:
        AuditTrail.notify(
            event.session,
            recipient_id=assessment.owner_id,
            entity_type="requirement_assessment",
            entity_id=assessment.id,
            event_type="control_recovered",
            title="Re-assess coverage: " + label + " works again",
            body="A requirement this control evidences is in Gap. It passed its retest; "
            "re-assess whether the requirement is covered.",
        )

    event.record(
        "control_review", review.id,
        "Retest passed; prompted " + str(prompted) + " risk(s), " + str(len(scenarios))
        + " threat scenario(s) and " + str(len(gaps)) + " requirement(s) to re-assess",
        invariant="REV-3",
    )
