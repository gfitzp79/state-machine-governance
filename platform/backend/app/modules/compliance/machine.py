"""Requirement assessment lifecycle.

A requirement is not a control, and its position is not derived from one. The
organisation decides whether a requirement applies, and then whether it is
covered, and both decisions are gated and attributed. That is what makes a
Statement of Applicability defensible rather than a spreadsheet of assertions.

The two interesting gates:

  * Applicable to Covered requires a satisfying link whose control is Operating
    AND deployed live on an asset inside the framework's scope (AINV-2). A
    control that runs everywhere except where the requirement bites covers
    nothing.
  * Not_Assessed to Not_Applicable requires a rationale (AINV-1), because an
    unexplained exclusion is the most common finding against an SoA.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.governance import governance
from app.engine import Precondition, StateMachine, Transition, TransitionContext
from app.modules.compliance.models import ASSESSMENT_STATES, RequirementAssessment


def _has_rationale(a: RequirementAssessment, ctx: TransitionContext) -> bool:
    return bool(ctx.payload.get("rationale") or a.rationale)


def _in_scope_assets(ctx: TransitionContext, framework_id: str) -> list:
    """Assets declaring themselves inside this framework's scope."""
    from app.modules.control.models import AttackSurface

    assets = ctx.session.query(AttackSurface).all()
    return [a for a in assets if framework_id in (a.compliance_scopes or [])]


def _coverage_is_live(a: RequirementAssessment, ctx: TransitionContext) -> bool:
    """AINV-2. The core rule of the module.

    A requirement is covered when a person has asserted a satisfying link, the
    linked control objective is Operating, and that control is deployed live on
    an asset inside the framework's scope.

    The last clause is what separates this from a mapping table. An objective
    marked Operating proves the control exists somewhere. It does not prove it
    exists on the estate the requirement applies to, and an assessor samples the
    estate rather than the register.

    An earlier draft required a deployment on EVERY in-scope asset. That is the
    more flattering rule to write and an unusable one to live with: requirements
    apply to different parts of an estate, so a single global scope would leave
    almost everything permanently uncovered, and the first thing anybody would
    do is stop declaring scope at all. Partial asset coverage is reported by
    `ComplianceService.asset_coverage` instead, where it informs rather than
    blocks - the same choice made for threat context in TINV-7.
    """
    links = a.requirement.satisfying_links
    if not links:
        return False

    live = governance.live_deployment_statuses
    framework_id = a.requirement.framework.framework_id
    scoped = {asset.id for asset in _in_scope_assets(ctx, framework_id)}

    for link in links:
        objective = link.objective
        if objective is None or objective.lifecycle_state != "Operating":
            continue
        for activity in objective.activities:
            for deployment in activity.deployments:
                if deployment.deployment_status not in live:
                    continue
                # With no scope declared, any live deployment counts and AINV-9
                # refuses the position separately. Declaring scope makes this
                # stricter, which is the right way round.
                if not scoped or deployment.attack_surface_id in scoped:
                    return True
    return False


def _compensating_is_bounded(a: RequirementAssessment, ctx: TransitionContext) -> bool:
    """AINV-4: compensating coverage always expires, and within the window."""
    expiry = ctx.payload.get("compensating_expiry") or a.compensating_expiry
    if not expiry:
        return False
    if isinstance(expiry, str):
        expiry = date.fromisoformat(expiry)
    limit = date.today() + timedelta(days=governance.compensating_max_days)
    return date.today() <= expiry <= limit


def _has_compensating_link(a: RequirementAssessment, _ctx: TransitionContext) -> bool:
    return any(
        link.coverage_level in governance.time_bound_coverage_levels
        for link in a.requirement.control_links
    )


def _framework_adopted(a: RequirementAssessment, _ctx: TransitionContext) -> bool:
    """A requirement of a framework nobody has adopted is reference material.

    Assessing it is not wrong, but it should be a deliberate act rather than a
    side effect of browsing a catalogue.
    """
    return bool(a.requirement.framework.adopted)


ASSESSOR = ("Risk_Analyst", "GRC_Engineer", "Control_Owner", "CISO", "Admin")
APPROVER = ("GRC_Engineer", "CISO", "Admin")


REQUIREMENT_ASSESSMENT_MACHINE = StateMachine(
    entity="requirement_assessment",
    state_field="lifecycle_state",
    initial="Not_Assessed",
    states=ASSESSMENT_STATES,
    transitions=[
        Transition(
            source="Not_Assessed",
            target="Applicable",
            gate="GATE_REQUIREMENT_IN_SCOPE",
            description="The requirement applies to this organisation.",
            roles=ASSESSOR,
            preconditions=(
                Precondition(
                    "AINV-8",
                    "The framework has been adopted",
                    _framework_adopted,
                    "Adopt the framework before assessing its requirements. A "
                    "catalogue that is merely loaded is reference material.",
                ),
            ),
        ),
        Transition(
            source="Not_Assessed",
            target="Not_Applicable",
            gate="GATE_REQUIREMENT_EXCLUDED",
            description="Excluded from scope, with justification. Enforces AINV-1.",
            roles=APPROVER,
            preconditions=(
                Precondition(
                    "AINV-1",
                    "Exclusion carries a documented justification",
                    _has_rationale,
                    "ISO 27001 requires a justification for every excluded "
                    "control. An unexplained exclusion is the most common "
                    "finding raised against a Statement of Applicability.",
                ),
            ),
            cascades=("requirement.excluded",),
        ),
        Transition(
            source="Not_Applicable",
            target="Applicable",
            gate="GATE_REQUIREMENT_IN_SCOPE",
            description="Re-scoped: the exclusion no longer holds.",
            roles=APPROVER,
            preconditions=(
                Precondition(
                    "AINV-1.2",
                    "Reason for re-scoping recorded",
                    _has_rationale,
                    "Reversing an exclusion changes the SoA. Say why.",
                ),
            ),
        ),
        Transition(
            source="Applicable",
            target="Covered",
            gate="GATE_REQUIREMENT_COVERED",
            description="Covered by a live control. Enforces AINV-2 and AINV-3.",
            roles=ASSESSOR,
            preconditions=(
                Precondition(
                    "AINV-2",
                    "A satisfying control is Operating and live inside the framework scope",
                    _coverage_is_live,
                    "Link a control whose objective is Operating and which is "
                    "deployed Active or Degraded on an asset inside this "
                    "framework's scope. A Partial link does not satisfy "
                    "(AINV-3), and a control that runs everywhere except where "
                    "the requirement applies covers nothing.",
                ),
            ),
            cascades=("requirement.covered",),
        ),
        Transition(
            source="Applicable",
            target="Compensating",
            gate="GATE_REQUIREMENT_COMPENSATING",
            description="Met by a compensating control. Time-bound (AINV-4).",
            roles=APPROVER,
            preconditions=(
                Precondition(
                    "AINV-4.1",
                    "A compensating link exists",
                    _has_compensating_link,
                    "Record the compensating control against this requirement "
                    "before asserting the position rests on it.",
                ),
                Precondition(
                    "AINV-4.2",
                    "The compensating position carries an expiry within the window",
                    _compensating_is_bounded,
                    "A compensating control is a temporary answer. Set an "
                    "expiry no further out than the configured maximum.",
                ),
                Precondition(
                    "AINV-4.3",
                    "Rationale recorded",
                    _has_rationale,
                    "Say what is being compensated for, and why the "
                    "compensation is adequate.",
                ),
            ),
            cascades=("requirement.compensating",),
        ),
        Transition(
            source="Applicable",
            target="Gap",
            gate="GATE_REQUIREMENT_GAP",
            description="Applicable and not covered. An honest gap.",
            roles=ASSESSOR,
            preconditions=(),
            cascades=("requirement.gap",),
        ),
        Transition(
            source="Covered",
            target="Gap",
            gate="GATE_REQUIREMENT_GAP",
            description=(
                "Coverage lost. Fired by the AINV-5 cascade when a deployment "
                "the requirement depended on fails, or by re-assessment."
            ),
            roles=ASSESSOR,
            preconditions=(),
            cascades=("requirement.gap",),
        ),
        Transition(
            source="Compensating",
            target="Gap",
            gate="GATE_REQUIREMENT_GAP",
            description="Compensating position expired or withdrawn.",
            roles=ASSESSOR,
            preconditions=(),
            cascades=("requirement.gap",),
        ),
        Transition(
            source="Compensating",
            target="Covered",
            gate="GATE_REQUIREMENT_COVERED",
            description="A permanent control replaced the compensating one.",
            roles=ASSESSOR,
            preconditions=(
                Precondition(
                    "AINV-2",
                    "A satisfying control is Operating and live inside the framework scope",
                    _coverage_is_live,
                    "The compensating control is not enough on its own. Link "
                    "the permanent control that replaced it.",
                ),
            ),
            cascades=("requirement.covered",),
        ),
        Transition(
            source="Gap",
            target="Covered",
            gate="GATE_REQUIREMENT_COVERED",
            description="Gap closed. Enforces AINV-2 and AINV-3.",
            roles=ASSESSOR,
            preconditions=(
                Precondition(
                    "AINV-2",
                    "A satisfying control is Operating and live inside the framework scope",
                    _coverage_is_live,
                    "Closing a gap means the control is running where the "
                    "requirement applies, not that it is planned.",
                ),
            ),
            cascades=("requirement.covered",),
        ),
        Transition(
            source="Gap",
            target="Compensating",
            gate="GATE_REQUIREMENT_COMPENSATING",
            description="Interim compensating position while the gap is closed.",
            roles=APPROVER,
            preconditions=(
                Precondition(
                    "AINV-4.1",
                    "A compensating link exists",
                    _has_compensating_link,
                    "Record the compensating control first.",
                ),
                Precondition(
                    "AINV-4.2",
                    "The compensating position carries an expiry within the window",
                    _compensating_is_bounded,
                    "Set an expiry no further out than the configured maximum.",
                ),
                Precondition(
                    "AINV-4.3",
                    "Rationale recorded",
                    _has_rationale,
                    "Say what is being compensated for.",
                ),
            ),
            cascades=("requirement.compensating",),
        ),
        Transition(
            source="Covered",
            target="Applicable",
            gate="GATE_REQUIREMENT_REASSESS",
            description="Re-opened for re-assessment, for instance on a framework change.",
            roles=ASSESSOR,
            preconditions=(),
        ),
    ],
)
