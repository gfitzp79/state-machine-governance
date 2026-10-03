"""Control effectiveness review lifecycle (codified-rules 10.3, REV-1 to REV-5).

    Open --GATE_REVIEW_COMPLETED--> Completed
    Open --GATE_REVIEW_CANCELLED--> Cancelled

Opened by the engine, never by a person: a deployment returning to Active opens
one (REV-1). Completed by someone who may edit controls, and only on a retest
recorded after the repair (REV-2). Completion is what tells the risks, threat
scenarios and compliance requirements that depend on the control to look again
(REV-3). An open review past its due date is escalated (REV-4).
"""

from __future__ import annotations

from app.core.governance import governance
from app.engine import Precondition, StateMachine, Transition, TransitionContext
from app.modules.review.models import REVIEW_STATES, ControlReview


def _retested_since_repair(review: ControlReview, _ctx: TransitionContext) -> bool:
    return _passing_test(review) is not None


def _passing_test(review: ControlReview):
    """The latest Pass recorded on the deployment after the review opened."""
    dep = review.deployment
    if dep is None:
        return None
    passes = [
        t for t in dep.tests
        if t.result == "Pass" and t.tested_at is not None and t.tested_at > review.opened_at
    ]
    return max(passes, key=lambda t: t.tested_at) if passes else None


def _deployment_live(review: ControlReview, _ctx: TransitionContext) -> bool:
    dep = review.deployment
    return dep is not None and dep.deployment_status in ("Active", "Degraded")


def _ce_current(review: ControlReview, _ctx: TransitionContext) -> bool:
    dep = review.deployment
    return (
        dep is not None
        and dep.ce_rating not in (None, "CE-Unvalidated")
        and bool(dep.ce_evidence_ref)
    )


def _reason(_review: ControlReview, ctx: TransitionContext) -> bool:
    return bool(str(ctx.payload.get("reason") or "").strip())


# Completing a review is assurance work, so it belongs to whoever may edit
# controls. Cancelling one can also be done by the CISO, who receives the
# escalation when it runs late.
_ASSURANCE = tuple(governance.edit_permissions.get("control", ()))

CONTROL_REVIEW_MACHINE = StateMachine(
    entity="control_review",
    state_field="lifecycle_state",
    initial="Open",
    states=REVIEW_STATES,
    terminal=("Completed", "Cancelled"),
    transitions=[
        Transition(
            source="Open",
            target="Completed",
            gate="GATE_REVIEW_COMPLETED",
            description=(
                "The repaired control is shown to work by a retest, and everything that "
                "depends on it is told to re-assess. Enforces REV-2 and REV-3."
            ),
            roles=_ASSURANCE,
            preconditions=(
                Precondition(
                    "REV-2",
                    "Retested since the repair, and passed",
                    _retested_since_repair,
                    "Record a passing test on this deployment. A test from before the "
                    "repair does not count, and the remediation assessment is not a test.",
                ),
                Precondition(
                    "REV-2.1",
                    "The deployment is live",
                    _deployment_live,
                    "The deployment is no longer Active or Degraded. Cancel the review "
                    "instead; a new one opens when it is repaired again.",
                ),
                Precondition(
                    "REV-2.2",
                    "Control effectiveness is rated with evidence",
                    _ce_current,
                    "The deployment carries no CE rating above Unvalidated with an "
                    "evidence reference.",
                ),
            ),
            cascades=("control_review.completed",),
        ),
        Transition(
            source="Open",
            target="Cancelled",
            gate="GATE_REVIEW_CANCELLED",
            description="The review no longer applies, for instance because the control failed again.",
            roles=(*_ASSURANCE, "CISO"),
            preconditions=(
                Precondition(
                    "REV-5",
                    "Cancellation reason recorded",
                    _reason,
                    "Record why the review is being cancelled.",
                    requires_input="reason",
                ),
            ),
        ),
    ],
)
