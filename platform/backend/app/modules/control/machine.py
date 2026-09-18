"""The three control lifecycles, declared.

Objective  Design -> Implementation -> Operating <-> Failure <-> Redesign -> Deprecated
Activity   Draft -> Active <-> Suspended -> Retired
Deployment Planned -> Active <-> Degraded <-> Failed -> Decommissioned

The blocking rules that matter are OL-3 (a control cannot retire while it is
still holding up an unmitigated above-appetite risk) and AL-1 (an activity cannot
retire while it still has live deployments).
"""

from __future__ import annotations

from app.engine import Precondition, StateMachine, Transition, TransitionContext
from app.modules.control.models import (
    ACTIVITY_STATES,
    DEPLOYMENT_STATES,
    OBJECTIVE_STATES,
    ControlActivity,
    ControlDeployment,
    ControlObjective,
)

# -- objective predicates --------------------------------------------------


def _has_activity(obj: ControlObjective, _ctx: TransitionContext) -> bool:
    return len(obj.activities) > 0


def _has_deployment_plan(obj: ControlObjective, _ctx: TransitionContext) -> bool:
    return any(a.deployments for a in obj.activities)


def _deployments_active(obj: ControlObjective, _ctx: TransitionContext) -> bool:
    """OL-4: at least one deployment actually live."""
    return any(d.deployment_status == "Active" for d in obj.deployments)


def _first_ce_assessed(obj: ControlObjective, _ctx: TransitionContext) -> bool:
    return any(
        d.deployment_status == "Active" and d.ce_rating != "CE-Unvalidated" and d.ce_evidence_ref
        for d in obj.deployments
    )


def _remediation_plan(obj: ControlObjective, _ctx: TransitionContext) -> bool:
    return bool(obj.remediation_plan)


def _ce_reassessed_upward(obj: ControlObjective, ctx: TransitionContext) -> bool:
    return any(
        d.deployment_status in ("Active", "Degraded")
        and d.ce_rating != "CE-Unvalidated"
        and d.ce_evidence_ref
        for d in obj.deployments
    )


def _no_blocking_risks(obj: ControlObjective, ctx: TransitionContext) -> bool:
    """OL-3 / CINV-8: retirement is blocked while a linked risk is above appetite
    and its treatment is unresolved."""
    from app.engine.scoring import ScoringEngine
    from app.modules.risk.models import Risk, RiskControlLink

    links = (
        ctx.session.query(RiskControlLink)
        .filter(RiskControlLink.objective_id == obj.id)
        .all()
    )
    if not links:
        return True
    risk_ids = [link.risk_id for link in links]
    risks = ctx.session.query(Risk).filter(Risk.id.in_(risk_ids)).all()
    for risk in risks:
        if risk.lifecycle_state == "Closed":
            continue
        if not ScoringEngine.is_above_appetite(risk.reported_rating):
            continue
        if risk.treatment_strategy not in ("Accept", "Transfer", "Avoid"):
            return False
    return True


def _deprecation_rationale(obj: ControlObjective, _ctx: TransitionContext) -> bool:
    return bool(obj.deprecation_rationale)


CONTROL_OBJECTIVE_MACHINE = StateMachine(
    entity="control_objective",
    state_field="lifecycle_state",
    initial="Design",
    states=OBJECTIVE_STATES,
    terminal=("Deprecated",),
    transitions=[
        Transition(
            source="Design",
            target="Implementation",
            gate="GATE_CONTROL_IMPLEMENTATION",
            description="At least one activity defined with a deployment plan.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "OL-1.1",
                    "At least one control activity defined",
                    _has_activity,
                    "Define how the objective will be implemented before moving to build.",
                ),
                Precondition(
                    "OL-1.2",
                    "Deployment plan exists",
                    _has_deployment_plan,
                    "At least one deployment must be planned against an asset.",
                ),
            ),
        ),
        Transition(
            source="Implementation",
            target="Operating",
            gate="GATE_CONTROL_OPERATING",
            description="Deployments live and first CE assessed. Enforces OL-4.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "OL-4",
                    "At least one deployment is Active",
                    _deployments_active,
                    "A control cannot be Operating with no live deployment.",
                ),
                Precondition(
                    "CINV-1",
                    "First control effectiveness assessed with evidence",
                    _first_ce_assessed,
                    "Assess CE on at least one active deployment and record the evidence "
                    "reference before the control counts as Operating.",
                ),
            ),
            cascades=("control.operating",),
        ),
        Transition(
            source="Operating",
            target="Failure",
            gate="GATE_CONTROL_FAILURE",
            description=(
                "Control has failed. Freezes residual scores on every linked risk (CINV-5)."
            ),
            roles=("Control_Owner", "Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(),
            cascades=("control.failed",),
        ),
        Transition(
            source="Failure",
            target="Operating",
            gate="GATE_CONTROL_RECOVERED",
            description="Remediated without architectural change and CE re-assessed upward.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "OL-2.1",
                    "Remediation plan recorded",
                    _remediation_plan,
                    "Document what was remediated before returning the control to Operating.",
                ),
                Precondition(
                    "OL-2.2",
                    "CE re-assessed with current evidence",
                    _ce_reassessed_upward,
                    "At least one live deployment must carry a CE rating above Unvalidated "
                    "with an evidence reference.",
                ),
                Precondition(
                    "OL-4",
                    "At least one deployment is Active",
                    _deployments_active,
                    "Restore at least one deployment to Active first.",
                ),
            ),
            cascades=("control.recovered",),
        ),
        Transition(
            source="Failure",
            target="Redesign",
            gate="GATE_CONTROL_REDESIGN",
            description="Remediation requires architectural change to the control design.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "OL-2.3",
                    "Redesign rationale recorded",
                    _remediation_plan,
                    "Document why the control needs redesigning rather than repair.",
                ),
            ),
        ),
        Transition(
            source="Redesign",
            target="Implementation",
            gate="GATE_CONTROL_REBUILD",
            description="Redesigned and ready for re-deployment.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "OL-1.1",
                    "At least one control activity defined",
                    _has_activity,
                    "Define the redesigned implementation before rebuilding.",
                ),
            ),
        ),
        Transition(
            source="*",
            target="Deprecated",
            gate="GATE_CONTROL_RETIREMENT",
            description="Governance-approved retirement. Enforces OL-3 / CINV-8.",
            roles=("Control_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "CINV-8",
                    "No linked risk is above appetite and unmitigated",
                    _no_blocking_risks,
                    "This control is still holding up at least one above-appetite risk whose "
                    "treatment is not Accepted, Transferred or Avoided. Resolve those risks "
                    "before retiring the control.",
                ),
                Precondition(
                    "OL-3.2",
                    "Retirement rationale documented",
                    _deprecation_rationale,
                    "Record why the control is being retired.",
                ),
            ),
            cascades=("control.deprecated",),
        ),
    ],
)


# -- activity --------------------------------------------------------------


def _activity_approved(act: ControlActivity, ctx: TransitionContext) -> bool:
    return bool(act.objective_id) and ctx.has_role(
        "Control_Owner", "GRC_Engineer", "CISO", "Admin"
    )


def _no_live_deployments(act: ControlActivity, _ctx: TransitionContext) -> bool:
    """AL-1: every deployment must be decommissioned before the activity retires."""
    return all(d.deployment_status == "Decommissioned" for d in act.deployments)


CONTROL_ACTIVITY_MACHINE = StateMachine(
    entity="control_activity",
    state_field="lifecycle_state",
    initial="Draft",
    states=ACTIVITY_STATES,
    terminal=("Retired",),
    transitions=[
        Transition(
            source="Draft",
            target="Active",
            gate="GATE_ACTIVITY_ACTIVE",
            description="Approved by the Control Owner and linked to a parent objective.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "AL-2",
                    "Linked to a parent objective and approved",
                    _activity_approved,
                    "Draft activities cannot be linked to risk records; activate first.",
                ),
            ),
        ),
        Transition(
            source="Active",
            target="Suspended",
            gate="GATE_ACTIVITY_SUSPEND",
            description="Suspension with documented rationale and impact assessment.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "AL-3",
                    "Suspension rationale documented",
                    lambda a, c: bool(a.suspension_rationale),
                    "Record why the activity is being suspended and what the impact is.",
                ),
            ),
        ),
        Transition(
            source="Suspended",
            target="Active",
            gate="GATE_ACTIVITY_RESUME",
            description="Suspension condition resolved.",
            roles=("Control_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(),
        ),
        Transition(
            source="Active",
            target="Retired",
            gate="GATE_ACTIVITY_RETIRE",
            description="Governance-approved retirement. Enforces AL-1.",
            roles=("Control_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "AL-1",
                    "All deployments decommissioned",
                    _no_live_deployments,
                    "Decommission every deployment of this activity before retiring it.",
                ),
            ),
        ),
        Transition(
            source="Suspended",
            target="Retired",
            gate="GATE_ACTIVITY_RETIRE",
            description="Governance-approved retirement from suspension.",
            roles=("Control_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "AL-1",
                    "All deployments decommissioned",
                    _no_live_deployments,
                    "Decommission every deployment of this activity before retiring it.",
                ),
            ),
        ),
    ],
)


# -- deployment ------------------------------------------------------------


def _deployment_ce_assessed(dep: ControlDeployment, _ctx: TransitionContext) -> bool:
    return dep.ce_rating != "CE-Unvalidated" and bool(dep.ce_evidence_ref)


def _remediation_evidence(dep: ControlDeployment, _ctx: TransitionContext) -> bool:
    return bool(dep.ce_evidence_ref) and dep.ce_rating != "CE-Unvalidated"


CONTROL_DEPLOYMENT_MACHINE = StateMachine(
    entity="control_deployment",
    state_field="deployment_status",
    initial="Planned",
    states=DEPLOYMENT_STATES,
    terminal=("Decommissioned",),
    transitions=[
        Transition(
            source="Planned",
            target="Active",
            gate="GATE_DEPLOYMENT_ACTIVE",
            description="Deployment confirmed on the asset.",
            roles=("Control_Owner", "Control_Operator", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(),
        ),
        Transition(
            source="Active",
            target="Degraded",
            gate="GATE_DEPLOYMENT_DEGRADED",
            description="Partial test result or CE drop to CE-Low.",
            roles=("Control_Owner", "Control_Operator", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(),
            cascades=("deployment.degraded",),
        ),
        Transition(
            source="Active",
            target="Failed",
            gate="GATE_DEPLOYMENT_FAILED",
            description="Test result Fail. Triggers DL-1 failure propagation to the objective.",
            roles=("Control_Owner", "Control_Operator", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(),
            cascades=("deployment.failed",),
        ),
        Transition(
            source="Degraded",
            target="Active",
            gate="GATE_DEPLOYMENT_RESTORED",
            description="Remediated and CE re-assessed upward.",
            roles=("Control_Owner", "Control_Operator", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "DL-2",
                    "CE re-assessed with evidence",
                    _deployment_ce_assessed,
                    "Re-assess CE on this deployment and record the evidence reference.",
                ),
            ),
            cascades=("deployment.restored",),
        ),
        Transition(
            source="Degraded",
            target="Failed",
            gate="GATE_DEPLOYMENT_FAILED",
            description="Further degradation confirmed. Triggers DL-1 propagation.",
            roles=("Control_Owner", "Control_Operator", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(),
            cascades=("deployment.failed",),
        ),
        Transition(
            source="Failed",
            target="Active",
            gate="GATE_DEPLOYMENT_REMEDIATED",
            description="Fully remediated, evidence provided and CE re-assessed.",
            roles=("Control_Owner", "Control_Operator", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "DL-4",
                    "Remediation evidence and CE re-assessment recorded",
                    _remediation_evidence,
                    "A failed deployment returns to Active only with fresh evidence and a "
                    "CE rating above Unvalidated.",
                ),
            ),
            cascades=("deployment.restored",),
        ),
        Transition(
            source="*",
            target="Decommissioned",
            gate="GATE_DEPLOYMENT_DECOMMISSION",
            description="Governance-approved. Record becomes read-only (DL-3).",
            roles=("Control_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "DL-3",
                    "Decommission rationale documented",
                    lambda d, c: bool(d.decommission_rationale),
                    "Record why the control is being removed from this asset. "
                    "The deployment becomes read-only afterwards.",
                ),
            ),
            cascades=("deployment.decommissioned",),
        ),
    ],
)
