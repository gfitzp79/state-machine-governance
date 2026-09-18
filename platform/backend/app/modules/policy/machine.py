"""Policy and policy exception lifecycles, declared.

Policy    Draft -> Under_Review -> Approved -> Active <-> Under_Revision -> Deprecated
Exception Requested -> Approved -> Expired, or Requested -> Rejected

PINV-1 is the rule with teeth on activation: a policy with no linked control is a
statement of intent with nothing enforcing it, so it cannot go Active.
"""

from __future__ import annotations

from datetime import date

from app.core.governance import governance
from app.engine import Precondition, StateMachine, Transition, TransitionContext
from app.modules.policy.models import (
    EXCEPTION_STATES,
    POLICY_STATES,
    Policy,
    PolicyException,
)


def _has_linked_control(policy: Policy, _ctx: TransitionContext) -> bool:
    """PINV-1."""
    return len(policy.control_links) > 0


def _approved_by_senior(policy: Policy, ctx: TransitionContext) -> bool:
    """PINV-5: CISO or above, and never the policy owner."""
    from app.modules.identity.models import ROLE_LEVELS, User

    if not policy.approved_by:
        return False
    if policy.approved_by == policy.policy_owner_id:
        return False
    approver = ctx.session.get(User, policy.approved_by)
    if approver is None:
        return False
    return max(
        (ROLE_LEVELS.get(r, 0) for r in approver.role_names), default=0
    ) >= ROLE_LEVELS["CISO"]


def _effective_date_reached(policy: Policy, _ctx: TransitionContext) -> bool:
    return policy.effective_date is not None and policy.effective_date <= date.today()


def _review_cycle_valid(policy: Policy, _ctx: TransitionContext) -> bool:
    """PINV-4 / CF-4."""
    if not policy.requires_annual_review:
        return True
    return policy.review_cycle == "Annual"


def _version_incremented(policy: Policy, ctx: TransitionContext) -> bool:
    """PL-4: a revision produces a new version with a change summary."""
    if not policy.change_summary:
        return False
    captured = {v.version for v in policy.versions}
    return policy.version not in captured or bool(ctx.payload.get("version"))


def _no_blocking_risks(policy: Policy, ctx: TransitionContext) -> bool:
    """PINV-8 / PL-2: deprecation is blocked while a linked risk is Critical or
    High and its treatment is unresolved."""
    from app.modules.risk.models import Risk, RiskPolicyLink

    links = (
        ctx.session.query(RiskPolicyLink).filter(RiskPolicyLink.policy_id == policy.id).all()
    )
    if not links:
        return True
    risks = (
        ctx.session.query(Risk).filter(Risk.id.in_([link.risk_id for link in links])).all()
    )
    for risk in risks:
        if risk.lifecycle_state == "Closed":
            continue
        if risk.reported_rating in ("Critical", "High") and risk.treatment_strategy not in (
            "Accept",
            "Transfer",
            "Avoid",
        ):
            return False
    return True


def _remapping_planned(policy: Policy, _ctx: TransitionContext) -> bool:
    return bool(policy.change_summary)


POLICY_MACHINE = StateMachine(
    entity="policy",
    state_field="lifecycle_state",
    initial="Draft",
    states=POLICY_STATES,
    terminal=("Deprecated",),
    transitions=[
        Transition(
            source="Draft",
            target="Under_Review",
            gate="GATE_POLICY_REVIEW",
            description="Policy owner submits the draft for review.",
            roles=("Policy_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PL-0",
                    "Policy body and scope populated",
                    lambda p, c: bool(p.body) and bool(p.scope),
                    "A policy needs a scope and a body before anyone can review it.",
                ),
            ),
        ),
        Transition(
            source="Under_Review",
            target="Draft",
            gate="GATE_POLICY_RETURN",
            description="Reviewer returns the policy for revision.",
            roles=("Policy_Owner", "CISO", "Admin"),
            preconditions=(),
        ),
        Transition(
            source="Under_Review",
            target="Approved",
            gate="GATE_POLICY_APPROVED",
            description="Approved by CISO or above. Enforces PINV-5.",
            roles=("CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PINV-5",
                    "Approved by CISO or above, and not by the policy owner",
                    _approved_by_senior,
                    "Policy approval requires CISO or above. Self-approval by the policy "
                    "owner is never permitted.",
                ),
                Precondition(
                    "PINV-4",
                    "Review cycle valid for the mapped compliance frameworks",
                    _review_cycle_valid,
                    "Policies mapped to annual-audit frameworks must carry an Annual review "
                    "cycle. Change the cycle or remove the mapping.",
                ),
            ),
        ),
        Transition(
            source="Approved",
            target="Active",
            gate="GATE_POLICY_ACTIVE",
            description="Effective date reached and at least one control linked. Enforces PINV-1.",
            roles=("Policy_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PINV-1",
                    "At least one control objective linked",
                    _has_linked_control,
                    "A policy with no linked control has nothing enforcing it. Link at least "
                    "one control objective before activation.",
                ),
                Precondition(
                    "PL-1",
                    "Effective date set and reached",
                    _effective_date_reached,
                    "Set an effective date on or before today.",
                ),
                Precondition(
                    "PL-1.2",
                    "Approver sign-off recorded",
                    lambda p, c: bool(p.approved_by) and p.approved_at is not None,
                    "The approval record must carry an approver identity and timestamp.",
                ),
            ),
            cascades=("policy.activated",),
        ),
        Transition(
            source="Active",
            target="Under_Revision",
            gate="GATE_POLICY_REVISION",
            description=(
                "Revision opened. The Active version stays enforceable throughout (PL-3)."
            ),
            roles=("Policy_Owner", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PL-3",
                    "Revision trigger recorded",
                    lambda p, c: bool(c.payload.get("reason") or p.change_summary),
                    "Record what triggered the revision: schedule, audit finding, "
                    "regulatory change, risk event, or exception volume.",
                ),
            ),
            cascades=("policy.revision_opened",),
        ),
        Transition(
            source="Under_Revision",
            target="Approved",
            gate="GATE_POLICY_REVISION_APPROVED",
            description="New version approved. Enforces PL-4 and PINV-5.",
            roles=("CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PL-4",
                    "Version incremented with a change summary",
                    _version_incremented,
                    "Increment the version and record what changed.",
                ),
                Precondition(
                    "PINV-5",
                    "Approved by CISO or above, and not by the policy owner",
                    _approved_by_senior,
                    "Policy approval requires CISO or above. Self-approval is never permitted.",
                ),
            ),
        ),
        Transition(
            source="Active",
            target="Deprecated",
            gate="GATE_POLICY_DEPRECATION",
            description="Superseded or no longer applicable. Enforces PINV-8 / PL-2.",
            roles=("CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PINV-8",
                    "No linked risk is Critical or High and unmitigated",
                    _no_blocking_risks,
                    "A Critical or High risk linked to this policy has an unresolved "
                    "treatment. Resolve it before deprecating the policy.",
                ),
                Precondition(
                    "PC-2",
                    "Re-mapping plan recorded",
                    _remapping_planned,
                    "Linked controls must be re-mapped to a surviving policy within 60 days. "
                    "Record the plan in the change summary.",
                ),
            ),
            cascades=("policy.deprecated",),
        ),
        Transition(
            source="Deprecated",
            target="Under_Review",
            gate="GATE_POLICY_REINSTATE",
            description="Reinstatement requires the full approval workflow.",
            roles=("CISO", "Admin"),
            preconditions=(),
        ),
    ],
)


# -- policy exception ------------------------------------------------------


def _expiry_within_limit(exc: PolicyException, ctx: TransitionContext) -> bool:
    """PE-1. Both windows come from policy.exceptions in governance.yml."""
    days = (exc.expiry_date - date.today()).days
    if days <= 0:
        return False
    if days <= governance.exception_max_days:
        return True
    if days <= governance.exception_extended_max_days:
        return ctx.has_role("CISO", "Admin")
    return False


POLICY_EXCEPTION_MACHINE = StateMachine(
    entity="policy_exception",
    state_field="lifecycle_state",
    initial="Requested",
    states=EXCEPTION_STATES,
    terminal=("Expired", "Rejected"),
    transitions=[
        Transition(
            source="Requested",
            target="Approved",
            gate="GATE_EXCEPTION_APPROVED",
            description="Approved by Policy Owner or above. Enforces PE-1 and PINV-2.",
            roles=("Policy_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PE-1",
                    "Expiry within the permitted window",
                    _expiry_within_limit,
                    "Exceptions run for a maximum of "
                    + str(governance.exception_max_days)
                    + " days, extendable to "
                    + str(governance.exception_extended_max_days)
                    + " with CISO approval. An expiry in the past is never valid.",
                ),
                Precondition(
                    "PE-0",
                    "Business justification and risk statement documented",
                    lambda e, c: bool(e.business_justification) and bool(e.risk_statement),
                    "Record the business justification and the risk being carried.",
                ),
            ),
            cascades=("exception.approved",),
        ),
        Transition(
            source="Requested",
            target="Rejected",
            gate="GATE_EXCEPTION_REJECTED",
            description="Rejected with documented rationale.",
            roles=("Policy_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "PE-6",
                    "Rejection rationale documented",
                    lambda e, c: bool(e.rejection_rationale),
                    "Record why the exception was refused.",
                ),
            ),
        ),
        Transition(
            source="Approved",
            target="Expired",
            gate="GATE_EXCEPTION_EXPIRED",
            description="Expiry reached or renewal not approved. Enforces PE-5.",
            roles=(),
            preconditions=(),
            cascades=("exception.expired",),
        ),
    ],
)
