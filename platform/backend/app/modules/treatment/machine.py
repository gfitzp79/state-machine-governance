"""Treatment lifecycle, declared.

Proposed -> Validated -> Approved -> In_Progress -> Complete, with Cancelled
reachable from anything short of Complete.

Validated is a distinct state rather than a flag on Approved because RINV-12
separates two different confirmations: a GRC Engineer saying the treatment is
technically feasible, and the treatment owner saying they will actually deliver it.
"""

from __future__ import annotations

from app.engine import Precondition, StateMachine, Transition, TransitionContext
from app.modules.treatment.models import TREATMENT_STATES, Treatment


def _has_owner(t: Treatment, _ctx: TransitionContext) -> bool:
    return bool(t.treatment_owner_id)


def _has_target_date(t: Treatment, _ctx: TransitionContext) -> bool:
    return t.target_date is not None


def _grc_validated(t: Treatment, _ctx: TransitionContext) -> bool:
    return t.grc_eng_validated and bool(t.grc_eng_validated_by)


def _owner_committed(t: Treatment, _ctx: TransitionContext) -> bool:
    return t.owner_committed


def _validator_is_not_owner(t: Treatment, _ctx: TransitionContext) -> bool:
    """SEP-5: the GRC Engineer validating feasibility is not the person on the
    hook for delivering it."""
    return t.grc_eng_validated_by != t.treatment_owner_id


def _has_evidence(t: Treatment, _ctx: TransitionContext) -> bool:
    return bool(t.evidence_ref)


def _has_checkin(t: Treatment, _ctx: TransitionContext) -> bool:
    return len(t.checkins) > 0


def _approved(t: Treatment, _ctx: TransitionContext) -> bool:
    return any(a.decision == "Approved" for a in t.approvals)


TREATMENT_MACHINE = StateMachine(
    entity="treatment",
    state_field="lifecycle_state",
    initial="Proposed",
    states=TREATMENT_STATES,
    terminal=("Complete", "Cancelled"),
    transitions=[
        Transition(
            source="Proposed",
            target="Validated",
            gate="GATE_TREATMENT_VALIDATED",
            description="GRC Engineer confirms technical feasibility. Enforces RINV-12.",
            roles=("GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "RINV-12.1",
                    "GRC Engineer feasibility validation recorded",
                    _grc_validated,
                    "A named GRC Engineer must confirm the treatment is technically "
                    "deliverable before it can be approved.",
                ),
                Precondition(
                    "SEP-5",
                    "Validator is not the treatment owner",
                    _validator_is_not_owner,
                    "The person validating feasibility cannot be the person delivering it.",
                ),
                Precondition(
                    "GATE_TREATMENT_VALIDATED.3",
                    "Treatment owner assigned",
                    _has_owner,
                    "Name the owner accountable for delivery.",
                ),
            ),
        ),
        Transition(
            source="Validated",
            target="Approved",
            gate="GATE_TREATMENT_APPROVED",
            description="Owner commits and governance approves. Enforces RINV-12.",
            roles=("Risk_Owner", "CISO", "Admin", "GRC_Engineer"),
            preconditions=(
                Precondition(
                    "RINV-12.2",
                    "Treatment owner commitment confirmed",
                    _owner_committed,
                    "The treatment owner must explicitly commit before approval.",
                ),
                Precondition(
                    "GATE_TREATMENT_APPROVED.2",
                    "Target date set",
                    _has_target_date,
                    "Set a delivery target date so the SLA clock can run.",
                ),
                Precondition(
                    "GATE_TREATMENT_APPROVED.3",
                    "Approval decision recorded",
                    _approved,
                    "Record an approval decision against this treatment.",
                ),
            ),
        ),
        Transition(
            source="Approved",
            target="In_Progress",
            gate="GATE_TREATMENT_STARTED",
            description="Delivery underway.",
            roles=("Risk_Treatment_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(),
        ),
        Transition(
            source="In_Progress",
            target="Complete",
            gate="GATE_TREATMENT_COMPLETE",
            description=(
                "Delivered with evidence. Feeds residual gate condition 1 on every linked risk."
            ),
            roles=("Risk_Treatment_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "RESIDUAL.2",
                    "Implementation evidence recorded",
                    _has_evidence,
                    "Record the evidence reference. A treatment marked complete without "
                    "evidence cannot release the residual gate on its linked risks.",
                ),
                Precondition(
                    "RESIDUAL.5",
                    "At least one progress check-in recorded",
                    _has_checkin,
                    "The drift trail needs at least one check-in across the treatment period.",
                ),
            ),
            cascades=("treatment.completed",),
        ),
        Transition(
            source="*",
            target="Cancelled",
            gate="GATE_TREATMENT_CANCELLED",
            description="Treatment abandoned. Linked risks return to treatment design.",
            roles=("Risk_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "GATE_TREATMENT_CANCELLED.1",
                    "Cancellation reason recorded",
                    lambda t, c: bool(c.payload.get("reason")),
                    "Record why the treatment is being cancelled.",
                ),
                Precondition(
                    "GATE_TREATMENT_CANCELLED.2",
                    "Treatment is not already complete",
                    lambda t, c: t.lifecycle_state != "Complete",
                    "A completed treatment cannot be cancelled. Its evidence is already "
                    "load-bearing for the residual scores it released.",
                ),
            ),
            cascades=("treatment.cancelled",),
        ),
    ],
)
