"""Control management invariants (CINV-1 .. CINV-10)."""

from __future__ import annotations

from app.engine import BOTH, SCHEMA, SERVICE, Invariant, invariants
from app.engine.scoring import ScoringEngine
from app.modules.control.models import ControlDeployment, ControlObjective

OBJECTIVE = "control_objective"
DEPLOYMENT = "control_deployment"


# CINV-1 ------------------------------------------------------------------
def _ce_requires_evidence(dep: ControlDeployment, _ctx) -> bool:
    if dep.ce_rating == "CE-Unvalidated":
        return True
    return bool(dep.ce_evidence_ref and dep.ce_evidence_ref.strip())


# CINV-2 ------------------------------------------------------------------
def _non_operating_excluded(obj: ControlObjective, _ctx) -> bool:
    """Structural: the scoring engine filters on lifecycle_state, so a Design or
    Implementation control cannot contribute. Registered so the exclusion is
    visible in the catalogue and testable."""
    if obj.contributes_to_scoring:
        return True
    resolution = ScoringEngine.resolve_ce([obj])
    return resolution.effective_ce == "CE-Unvalidated"


# CINV-4 ------------------------------------------------------------------
def _no_ce_on_decommissioned(dep: ControlDeployment, _ctx) -> bool:
    if dep.deployment_status != "Decommissioned":
        return True
    return dep.ce_rating == "CE-Unvalidated" or dep.ce_assessed_at is None or dep.is_read_only


# CINV-6 ------------------------------------------------------------------
def _worst_case_ce(obj: ControlObjective, _ctx) -> bool:
    """The resolved CE never exceeds the weakest qualifying deployment."""
    from app.engine.scoring import CE_STRENGTH

    resolution = ScoringEngine.resolve_ce([obj])
    if not resolution.contributing:
        return resolution.effective_ce == "CE-Unvalidated"
    weakest = min(
        (c["ce_rating"] for c in resolution.contributing),
        key=lambda r: CE_STRENGTH.get(r, 0),
    )
    return resolution.effective_ce == weakest


# CINV-8 ------------------------------------------------------------------
def _retirement_blocked_by_risks(obj: ControlObjective, ctx) -> bool:
    if obj.lifecycle_state != "Deprecated":
        return True
    from app.modules.risk.models import Risk, RiskControlLink

    session = getattr(ctx, "session", None)
    if session is None:
        return True
    links = session.query(RiskControlLink).filter(RiskControlLink.objective_id == obj.id).all()
    if not links:
        return True
    risks = session.query(Risk).filter(Risk.id.in_([link.risk_id for link in links])).all()
    for risk in risks:
        if risk.lifecycle_state == "Closed":
            continue
        if ScoringEngine.is_above_appetite(risk.reported_rating) and risk.treatment_strategy not in (
            "Accept",
            "Transfer",
            "Avoid",
        ):
            return False
    return True


# CINV-10 -----------------------------------------------------------------
def _expired_ce_downgraded(dep: ControlDeployment, _ctx) -> bool:
    """Expired evidence never continues to count. The scheduled job performs the
    downgrade; this invariant makes a stale non-Unvalidated rating a hard error."""
    if dep.ce_rating == "CE-Unvalidated":
        return True
    return not ScoringEngine.ce_expired(dep.ce_assessed_at, dep.test_frequency)


# CINV-3 ------------------------------------------------------------------
def _owner_not_risk_owner(obj: ControlObjective, ctx) -> bool:
    """SEP-3, from the control side.

    RINV-3 stops a risk being assigned to someone who owns a control feeding its
    score. This is the other direction: assigning control ownership to someone
    who already owns a linked risk. Without it the rule is trivially defeated by
    doing the two assignments in the opposite order.
    """
    if not obj.control_owner_id:
        return True
    from app.modules.risk.models import Risk, RiskControlLink

    session = getattr(ctx, "session", None)
    if session is None:
        return True
    links = session.query(RiskControlLink).filter(
        RiskControlLink.objective_id == obj.id
    ).all()
    if not links:
        return True
    owners = {
        r.risk_owner_id
        for r in session.query(Risk).filter(Risk.id.in_([l.risk_id for l in links])).all()
    }
    return obj.control_owner_id not in owners


# CINV-5 / CINV-7 / CINV-9 ------------------------------------------------
def _always(entity, _ctx) -> bool:
    return True


invariants.register(
    Invariant(
        id="CINV-1",
        entity=DEPLOYMENT,
        rule="Control effectiveness evidence is required for any rating other than CE-Unvalidated",
        layer=BOTH,
        mechanism="CHECK constraint on control_deployments plus service validation",
        violation="CE rating save rejected; evidence reference required",
        spec_ref="codified-rules section 4.5",
        holds=_ce_requires_evidence,
    ),
    Invariant(
        id="CINV-2",
        entity=OBJECTIVE,
        rule="Design and Implementation controls are never used as CE evidence in risk scoring",
        layer=SERVICE,
        mechanism="Scoring engine filters to Operating objectives; others resolve to CE-Unvalidated",
        violation="Controls silently excluded from scoring, with the exclusion reason surfaced",
        spec_ref="codified-rules section 9.1 (OL rules)",
        holds=_non_operating_excluded,
    ),
    Invariant(
        id="CINV-3",
        entity=OBJECTIVE,
        rule="A Control Owner is never assigned as Risk Owner for a linked risk",
        layer=SERVICE,
        mechanism=(
            "Control owner checked against the risk owner of every linked risk. "
            "The risk-side half is RINV-3; both directions are needed or the rule "
            "is defeated by ordering the two assignments the other way round."
        ),
        violation="Assignment rejected",
        spec_ref="codified-rules section 2.2 (SEP-3)",
        holds=_owner_not_risk_owner,
    ),
    Invariant(
        id="CINV-4",
        entity=DEPLOYMENT,
        rule="Control effectiveness is never assessed on a decommissioned deployment",
        layer=SERVICE,
        mechanism="Decommissioned deployments are read-only; CE writes are rejected",
        violation="Write rejected; the deployment is frozen",
        spec_ref="codified-rules section 9.3 (DL-3)",
        holds=_no_ce_on_decommissioned,
    ),
    Invariant(
        id="CINV-5",
        entity=OBJECTIVE,
        rule="A Failure state always propagates a warning to every linked risk record",
        layer=SERVICE,
        mechanism="control.failed cascade flags linked risks and sets residual_score_locked",
        violation="Automatic cascade; no manual action required",
        spec_ref="codified-rules section 9.1 (OL-5)",
        holds=_always,
    ),
    Invariant(
        id="CINV-6",
        entity=OBJECTIVE,
        rule="Worst-case control effectiveness across deployments is always used in scoring",
        layer=SERVICE,
        mechanism="Scoring engine takes the minimum CE across qualifying deployments",
        violation="Automatic; the engine never averages and never takes best case",
        spec_ref="codified-rules section 4.6",
        holds=_worst_case_ce,
    ),
    Invariant(
        id="CINV-7",
        entity=DEPLOYMENT,
        rule="Test history records are immutable",
        layer=SCHEMA,
        mechanism="Database trigger rejects UPDATE and DELETE on control_tests",
        violation="UPDATE and DELETE rejected at the database layer; corrections supersede",
        spec_ref="codified-rules section 10.1 (TST-1)",
        holds=_always,
    ),
    Invariant(
        id="CINV-8",
        entity=OBJECTIVE,
        rule="Control retirement is blocked if linked risks are above appetite and unmitigated",
        layer=SERVICE,
        mechanism="Deprecation gate walks every linked risk before permitting the transition",
        violation="Lifecycle transition rejected",
        spec_ref="codified-rules section 9.1 (OL-3)",
        holds=_retirement_blocked_by_risks,
    ),
    Invariant(
        id="CINV-9",
        entity=DEPLOYMENT,
        rule="Asset decommission never silently removes risk-control linkages",
        layer=SERVICE,
        mechanism="Decommission preserves linkages read-only and notifies the Risk Analyst",
        violation="Decommission proceeds; linkages remain visible and re-assessment is required",
        spec_ref="codified-rules section 8.1 (CH-6)",
        holds=_always,
    ),
    Invariant(
        id="CINV-10",
        entity=DEPLOYMENT,
        rule="Expired control effectiveness auto-downgrades to CE-Unvalidated with no override",
        layer=SERVICE,
        mechanism="Scheduled job downgrades on expiry; no endpoint permits a manual override",
        violation="Automatic downgrade; Risk Analyst notified",
        spec_ref="codified-rules section 10.2",
        holds=_expired_ce_downgraded,
    ),
)
