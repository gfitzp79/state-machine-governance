"""Risk management invariants (RINV-1 .. RINV-13).

These are hard rules. They are evaluated on every write to a risk record, before
commit, regardless of which API path reached the record or what role the caller
holds. Several are additionally backed by CHECK constraints in the schema so a
direct SQL write cannot bypass them either.
"""

from __future__ import annotations

from datetime import date

from app.engine import BOTH, SCHEMA, SERVICE, Invariant, invariants
from app.engine.scoring import ACCEPTANCE_RULES, ScoringEngine
from app.modules.risk.models import Risk

ENTITY = "risk"


def _linked_objectives(risk: Risk):
    return [link.objective for link in risk.control_links if link.objective is not None]


# RINV-1 ------------------------------------------------------------------
def _residual_only_with_validation(risk: Risk, _ctx) -> bool:
    if not risk.residual_score_locked:
        return True
    # While locked, residual scores must be absent or identical to inherent.
    if risk.residual_risk_score is None:
        return True
    return risk.residual_risk_score == risk.inherent_risk_score


# RINV-3 ------------------------------------------------------------------
def _owner_not_control_owner(risk: Risk, _ctx) -> bool:
    """SEP-3: the person who owns a control feeding this risk's score cannot also
    be the person who owns the risk decision."""
    if not risk.risk_owner_id:
        return True
    return all(obj.control_owner_id != risk.risk_owner_id for obj in _linked_objectives(risk))


# RINV-4 ------------------------------------------------------------------
def _acceptance_time_bound(risk: Risk, _ctx) -> bool:
    if risk.treatment_strategy != "Accept":
        return True
    if risk.acceptance_expiry_date is None:
        return False
    rating = risk.inherent_rating or risk.reported_rating
    rule = ACCEPTANCE_RULES.get(rating or "", {})
    max_days = int(rule.get("max_days", 365))
    return (risk.acceptance_expiry_date - date.today()).days <= max_days


# RINV-5 ------------------------------------------------------------------
def _critical_never_accepted(risk: Risk, _ctx) -> bool:
    if risk.treatment_strategy != "Accept":
        return True
    return "Critical" not in (risk.inherent_rating, risk.residual_rating)


# RINV-6 ------------------------------------------------------------------
def _readout_not_skipped(risk: Risk, _ctx) -> bool:
    """Only meaningful once the risk is past readout."""
    if risk.phase_number < 6:
        return True
    if risk.inherent_rating in ("Moderate", "High", "Critical"):
        return risk.readout_confirmed
    return True


# RINV-9 ------------------------------------------------------------------
def _only_operating_controls_reduce(risk: Risk, _ctx) -> bool:
    """A residual likelihood below inherent has to be justified by controls that
    actually qualify. If nothing qualifies, no reduction is permitted."""
    if risk.residual_likelihood is None or risk.likelihood is None:
        return True
    if risk.residual_likelihood >= risk.likelihood:
        return True
    resolution = ScoringEngine.resolve_ce(_linked_objectives(risk))
    ok, _ = ScoringEngine.validate_residual_likelihood(
        risk.likelihood, risk.residual_likelihood, resolution
    )
    return ok


# RINV-10 -----------------------------------------------------------------
def _ownership_present(risk: Risk, _ctx) -> bool:
    """Enforced from Scoring onward; an Intake record has not yet been assigned."""
    if risk.phase_number < 3:
        return True
    return bool(risk.risk_owner_id) and bool(risk.risk_stakeholder_id)


def _sep1(risk: Risk, _ctx) -> bool:
    if not risk.risk_owner_id or not risk.risk_stakeholder_id:
        return True
    return risk.risk_owner_id != risk.risk_stakeholder_id


# RINV-12 -----------------------------------------------------------------
def _treatments_validated_before_readout(risk: Risk, _ctx) -> bool:
    if risk.phase_number < 5 or risk.treatment_strategy != "Mitigate":
        return True
    links = risk.treatment_links
    if not links:
        return False
    return all(link.treatment.grc_eng_validated and link.treatment.owner_committed for link in links)


# RINV-13 -----------------------------------------------------------------
def _partial_treatment_documented(risk: Risk, ctx) -> bool:
    """If fewer treatments were selected than were proposed against this risk, the
    reason has to be on the record."""
    if risk.treatment_strategy != "Mitigate":
        return True
    selected = len(risk.treatment_links)
    proposed = int(getattr(ctx, "payload", {}).get("treatments_proposed", selected) or selected)
    if proposed <= selected:
        return True
    return bool(risk.partial_treatment_rationale)


# RINV-2 ------------------------------------------------------------------
def _appetite_not_downgraded(risk: Risk, ctx) -> bool:
    """Appetite thresholds are a governance artefact, not per-record data. No API
    path writes them, so the invariant holds structurally; it is registered here
    so the catalogue stays complete and the rule stays visible."""
    return True


# RINV-7 ------------------------------------------------------------------
def _promotion_criteria_met(risk: Risk, _ctx) -> bool:
    """An item that arrived by promotion must carry the triage confirmation that
    justified promoting it."""
    if risk.intake_source != "Issue_Promotion":
        return True
    if risk.phase_number < 2:
        return True
    return risk.pre_true_risk_confirmed


# RINV-8 ------------------------------------------------------------------
def _no_scoring_before_preconditions(risk: Risk, _ctx) -> bool:
    if risk.phase_number >= 3:
        return True
    return risk.impact is None and risk.likelihood is None


# RINV-11 -----------------------------------------------------------------
def _no_silent_expiry(risk: Risk, _ctx) -> bool:
    """An acceptance past its expiry must be flagged. The scheduled job sets the
    flag; this invariant makes an unflagged expired acceptance a hard error."""
    if risk.treatment_strategy != "Accept" or risk.acceptance_expiry_date is None:
        return True
    if risk.acceptance_expiry_date >= date.today():
        return True
    return risk.escalation_flag


invariants.register(
    Invariant(
        id="RINV-1",
        entity=ENTITY,
        rule="Residual risk is never updated without validated evidence",
        layer=BOTH,
        mechanism=(
            "residual_score_locked flag released only by GATE_RESIDUAL_VALIDATED; while "
            "locked, residual may not diverge from inherent"
        ),
        violation="Write rejected; residual remains at the inherent score",
        spec_ref="scoring-model section 7",
        holds=_residual_only_with_validation,
    ),
    Invariant(
        id="RINV-2",
        entity=ENTITY,
        rule="Risk appetite is never downgraded without formal governance",
        layer=SERVICE,
        mechanism="No API endpoint writes appetite thresholds; they are engine constants",
        violation="Change request rejected; logged as an unauthorised modification attempt",
        spec_ref="codified-rules section 1.2",
        holds=_appetite_not_downgraded,
    ),
    Invariant(
        id="RINV-3",
        entity=ENTITY,
        rule="Control owners are never assigned as risk owners for linked risks",
        layer=BOTH,
        mechanism="Risk owner checked against control_owner_id on every linked objective",
        violation="Assignment rejected; validation error returned",
        spec_ref="codified-rules section 2.2 (SEP-3)",
        holds=_owner_not_control_owner,
    ),
    Invariant(
        id="RINV-4",
        entity=ENTITY,
        rule="Acceptance is never permanent; it is always time-bound and within the rating limit",
        layer=BOTH,
        mechanism="CHECK constraint requires an expiry date; service caps the window per rating",
        violation="Write rejected; constraint violation",
        spec_ref="codified-rules section 5.5",
        holds=_acceptance_time_bound,
    ),
    Invariant(
        id="RINV-5",
        entity=ENTITY,
        rule="Critical risks are never accepted",
        layer=BOTH,
        mechanism="CHECK constraint plus service-layer rejection of Accept on a Critical rating",
        violation="Decision rejected; must select Mitigate, Transfer or Avoid",
        spec_ref="codified-rules section 5.5",
        holds=_critical_never_accepted,
    ),
    Invariant(
        id="RINV-6",
        entity=ENTITY,
        rule="Risk readout is never skipped for risks rated Moderate or above",
        layer=SERVICE,
        mechanism="Phase 5 gate requires readout_confirmed for Moderate, High and Critical",
        violation="Phase transition blocked",
        spec_ref="codified-rules section 7.4",
        holds=_readout_not_skipped,
    ),
    Invariant(
        id="RINV-7",
        entity=ENTITY,
        rule="Issues are never scored as risks without promotion criteria met",
        layer=SERVICE,
        mechanism="Promoted items must carry triage confirmation before leaving Preconditions",
        violation="Risk record creation blocked; item remains in issue management",
        spec_ref="codified-rules section 3.6",
        holds=_promotion_criteria_met,
    ),
    Invariant(
        id="RINV-8",
        entity=ENTITY,
        rule="Scoring never begins without preconditions satisfied",
        layer=SERVICE,
        mechanism="Scoring fields remain unwritable until the 4-item Phase 2 checklist passes",
        violation="Phase transition blocked; scoring fields stay read-only",
        spec_ref="codified-rules section 4.1",
        holds=_no_scoring_before_preconditions,
    ),
    Invariant(
        id="RINV-9",
        entity=ENTITY,
        rule="Planned, partial or unvalidated controls never reduce residual risk",
        layer=SERVICE,
        mechanism=(
            "Scoring engine filters to Operating objectives with live deployments and "
            "non-expired evidence, then caps the likelihood reduction at the resolved CE"
        ),
        violation="Residual likelihood reduction beyond the CE ceiling is rejected",
        spec_ref="codified-rules section 4.6",
        holds=_only_operating_controls_reduce,
    ),
    Invariant(
        id="RINV-10",
        entity=ENTITY,
        rule="Every risk has both a Risk Owner and a Risk Stakeholder",
        layer=BOTH,
        mechanism="Service enforcement from Phase 3 onward; CHECK constraint enforces SEP-1",
        violation="Write rejected; constraint violation",
        spec_ref="codified-rules section 2.1",
        holds=_ownership_present,
    ),
    Invariant(
        id="SEP-1",
        entity=ENTITY,
        rule="The Risk Owner is never also the Risk Stakeholder",
        layer=BOTH,
        mechanism="CHECK constraint on the risks table plus service validation",
        violation="Assignment rejected",
        spec_ref="codified-rules section 2.2",
        holds=_sep1,
    ),
    Invariant(
        id="RINV-11",
        entity=ENTITY,
        rule="Expired acceptances are always escalated; no silent expiry",
        layer=SERVICE,
        mechanism="Daily scheduled job flags expired acceptances; an unflagged one is invalid",
        violation="Auto-escalation to Risk Owner, then Risk Stakeholder, then CISO",
        spec_ref="codified-rules sections 5.5 and 6.1",
        holds=_no_silent_expiry,
    ),
    Invariant(
        id="RINV-12",
        entity=ENTITY,
        rule=(
            "Treatments are never presented at readout without GRC Engineer validation and "
            "treatment owner commitment"
        ),
        layer=SERVICE,
        mechanism="Phase 4 gate checks both flags on every linked treatment record",
        violation="Phase transition blocked; treatment records flagged incomplete",
        spec_ref="codified-rules section 5.2",
        holds=_treatments_validated_before_readout,
    ),
    Invariant(
        id="RINV-13",
        entity=ENTITY,
        rule="Partial treatment selection is always documented with a rationale",
        layer=SERVICE,
        mechanism="Rationale required when fewer treatments are selected than proposed",
        violation="Save rejected; rationale field required",
        spec_ref="codified-rules section 5.2",
        holds=_partial_treatment_documented,
    ),
)
