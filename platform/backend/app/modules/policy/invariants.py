"""Policy management invariants (PINV-1 .. PINV-10)."""

from __future__ import annotations

from datetime import date

from app.core import ownership
from app.engine import BOTH, SCHEMA, SERVICE, Invariant, invariants
from app.modules.policy.models import Policy, PolicyException

POLICY = "policy"
EXCEPTION = "policy_exception"


def _active_policy_has_control(policy: Policy, _ctx) -> bool:
    if policy.lifecycle_state not in ("Active", "Under_Revision"):
        return True
    return len(policy.control_links) > 0


def _exception_time_bound(exc: PolicyException, _ctx) -> bool:
    return exc.expiry_date is not None


def _no_self_approval(policy: Policy, ctx) -> bool:
    if not policy.approved_by:
        return True
    if policy.approved_by == policy.policy_owner_id:
        return False
    from app.modules.identity.models import ROLE_LEVELS, User

    session = getattr(ctx, "session", None)
    if session is None:
        return True
    approver = session.get(User, policy.approved_by)
    if approver is None:
        return False
    return approver.max_role_level >= ROLE_LEVELS["CISO"]


def _annual_cycle_for_compliance(policy: Policy, _ctx) -> bool:
    if not policy.requires_annual_review:
        return True
    return policy.review_cycle == "Annual"


def _retirement_blocked(policy: Policy, ctx) -> bool:
    if policy.lifecycle_state != "Deprecated":
        return True
    from app.modules.risk.models import Risk, RiskPolicyLink

    session = getattr(ctx, "session", None)
    if session is None:
        return True
    links = session.query(RiskPolicyLink).filter(RiskPolicyLink.policy_id == policy.id).all()
    if not links:
        return True
    risks = session.query(Risk).filter(Risk.id.in_([link.risk_id for link in links])).all()
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


def _approved_exception_not_past_expiry(exc: PolicyException, _ctx) -> bool:
    """PE-5: an approved exception past its expiry is a governance gap, not a
    valid state. It must be transitioned to Expired."""
    if exc.lifecycle_state != "Approved":
        return True
    return exc.expiry_date >= date.today()


def _always(entity, _ctx) -> bool:
    return True


# PINV-10 ------------------------------------------------------------------
POLICY_OWNER_ROLES = {
    "policy_owner_id": "Policy_Owner",
}

invariants.register(
    Invariant(
        id="PINV-10",
        entity=POLICY,
        rule="A person named as policy owner holds the Policy_Owner role",
        layer=SERVICE,
        mechanism=ownership.describe(POLICY_OWNER_ROLES),
        violation="Named owner does not hold the required role",
        spec_ref="codified-rules section 2.4",
        holds=ownership.holder_of(fields=POLICY_OWNER_ROLES),
    ),
    Invariant(
        id="PINV-1",
        entity=POLICY,
        rule="Every Active policy has at least one linked control objective",
        layer=SERVICE,
        mechanism="Activation gate counts linked controls; zero blocks the transition",
        violation="Lifecycle transition blocked; governance gap flagged",
        spec_ref="codified-rules section 12.1 (PH-1)",
        holds=_active_policy_has_control,
    ),
    Invariant(
        id="PINV-2",
        entity=EXCEPTION,
        rule="Policy exceptions are never permanent; they are always time-bound",
        layer=SCHEMA,
        mechanism="NOT NULL constraint on policy_exceptions.expiry_date",
        violation="Write rejected; constraint violation",
        spec_ref="codified-rules section 12.3 (PE-1)",
        holds=_exception_time_bound,
    ),
    Invariant(
        id="PINV-3",
        entity=POLICY,
        rule="Policy deprecation never silently removes risk-policy linkages",
        layer=SERVICE,
        mechanism="Deprecation cascade preserves linkages and starts a 60-day re-mapping SLA",
        violation="Deprecation proceeds; linkages remain and the re-mapping clock starts",
        spec_ref="codified-rules section 14.1 (PC-2)",
        holds=_always,
    ),
    Invariant(
        id="PINV-4",
        entity=POLICY,
        rule="Compliance-mapped policies carry an Annual review cycle",
        # Service only: the rule depends on the contents of a jsonb column, which
        # a CHECK constraint cannot evaluate meaningfully.
        layer=SERVICE,
        mechanism="Service validates the cycle against the mapped frameworks on save",
        violation="Save rejected if Biennial is selected for a compliance-mapped policy",
        spec_ref="codified-rules section 15 (CF-4)",
        holds=_annual_cycle_for_compliance,
    ),
    Invariant(
        id="PINV-5",
        entity=POLICY,
        rule="Policy approval requires CISO or above, and never self-approval",
        layer=BOTH,
        mechanism="CHECK constraint blocks owner == approver; service checks the role level",
        violation="Approval rejected; must be approved by CISO or a delegate",
        spec_ref="codified-rules section 13.1 (PL-1)",
        holds=_no_self_approval,
    ),
    Invariant(
        id="PINV-6",
        entity=POLICY,
        rule="Policies Under Revision remain enforceable",
        layer=SERVICE,
        mechanism=(
            "A revision captures an immutable version and drafts forward; the Active version "
            "stays system of record until the new one reaches Active"
        ),
        violation="No violation possible; the architecture prevents an enforcement gap",
        spec_ref="codified-rules section 13.1 (PL-3)",
        holds=_always,
    ),
    Invariant(
        id="PINV-7",
        entity=POLICY,
        rule="Standard revision always triggers a control alignment check",
        layer=SERVICE,
        mechanism="Revision cascade notifies linked control owners with a 30-day SLA",
        violation="Automatic notification; SLA tracking begins",
        spec_ref="codified-rules section 14.1 (PC-1)",
        holds=_always,
    ),
    Invariant(
        id="PINV-8",
        entity=POLICY,
        rule="Policy retirement is blocked if linked risks are Critical or High and unmitigated",
        layer=SERVICE,
        mechanism="Deprecation gate walks every linked risk before permitting the transition",
        violation="Lifecycle transition rejected",
        spec_ref="codified-rules section 13.1 (PL-2)",
        holds=_retirement_blocked,
    ),
    Invariant(
        id="PINV-9",
        entity=POLICY,
        rule="Version history is immutable and always retained for audit",
        layer=SCHEMA,
        mechanism="Database trigger rejects UPDATE and DELETE on policy_versions",
        violation="UPDATE and DELETE rejected at the database layer",
        spec_ref="codified-rules section 12.2",
        holds=_always,
    ),
    Invariant(
        id="PE-5",
        entity=EXCEPTION,
        rule="An approved exception past its expiry date is a governance gap, not a valid state",
        layer=SERVICE,
        mechanism="Scheduled job expires overdue exceptions and notifies the CISO",
        violation="Governance gap flagged; CISO notified",
        spec_ref="state-transitions section 6",
        holds=_approved_exception_not_past_expiry,
    ),
)
