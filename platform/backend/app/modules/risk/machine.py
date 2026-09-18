"""The 7-phase risk lifecycle, declared.

Each gate below is a direct transcription of the corresponding gate in the state
transitions specification. The `id` on every precondition is its specification
reference, so a blocked transition in the UI points back at the rule that blocked
it rather than at a generic validation message.
"""

from __future__ import annotations

from typing import Any

from app.engine import Precondition, StateMachine, Transition, TransitionContext
from app.modules.risk.models import RISK_STATES, Risk

# -- reusable predicates ---------------------------------------------------


def _statement_complete(risk: Risk, _ctx: TransitionContext) -> bool:
    return all(
        bool(v and str(v).strip())
        for v in (risk.cause, risk.threat_event, risk.vulnerability, risk.impact_statement)
    )


def _all_preconditions(risk: Risk, _ctx: TransitionContext) -> bool:
    return all(risk.preconditions.values())


def _inherent_scored(risk: Risk, _ctx: TransitionContext) -> bool:
    return (
        risk.impact is not None
        and risk.likelihood is not None
        and risk.inherent_risk_score is not None
        and bool(risk.inherent_rating)
    )


def _ownership_assigned(risk: Risk, _ctx: TransitionContext) -> bool:
    return bool(risk.risk_owner_id) and bool(risk.risk_stakeholder_id)


def _has_treatment(risk: Risk, _ctx: TransitionContext) -> bool:
    if risk.treatment_strategy in ("Accept", "Transfer", "Avoid"):
        return True
    return len(risk.treatment_links) > 0


def _treatments_validated(risk: Risk, _ctx: TransitionContext) -> bool:
    """RINV-12. A non-Mitigate strategy has no treatments to validate."""
    if risk.treatment_strategy != "Mitigate":
        return True
    links = risk.treatment_links
    return bool(links) and all(link.treatment.grc_eng_validated for link in links)


def _owners_committed(risk: Risk, _ctx: TransitionContext) -> bool:
    if risk.treatment_strategy != "Mitigate":
        return True
    links = risk.treatment_links
    return bool(links) and all(link.treatment.owner_committed for link in links)


def _control_mapping_documented(risk: Risk, _ctx: TransitionContext) -> bool:
    if risk.treatment_strategy != "Mitigate":
        return True
    return bool(risk.control_framework_mapping) or bool(risk.control_links)


def _strategy_selected(risk: Risk, _ctx: TransitionContext) -> bool:
    return bool(risk.treatment_strategy)


def _readout_done(risk: Risk, _ctx: TransitionContext) -> bool:
    """RINV-6. Readout is mandatory at Moderate and above and cannot be waived;
    below Moderate the confirmation flag is still the record of the decision."""
    return risk.readout_confirmed and risk.readout_conducted_at is not None


def _residual_gate(condition: str):
    def check(risk: Risk, _ctx: TransitionContext) -> bool:
        return bool(risk.residual_gate_conditions.get(condition))

    return check


def _treatments_complete(risk: Risk, _ctx: TransitionContext) -> bool:
    """Residual gate condition 1 read from the treatment records themselves
    rather than from a flag someone ticked."""
    if risk.treatment_strategy != "Mitigate":
        return True
    links = risk.treatment_links
    return bool(links) and all(link.treatment.is_complete for link in links)


def _residual_scored(risk: Risk, _ctx: TransitionContext) -> bool:
    return (
        risk.residual_impact is not None
        and risk.residual_likelihood is not None
        and not risk.residual_score_locked
    )


def _no_open_control_failure(risk: Risk, _ctx: TransitionContext) -> bool:
    """A risk cannot enter monitoring while a control it relies on is in Failure."""
    return not any(
        link.objective.lifecycle_state == "Failure" for link in risk.control_links
    )


def _closable(risk: Risk, _ctx: TransitionContext) -> bool:
    return bool(risk.closure_rationale)


def _treatment_resolved_for_closure(risk: Risk, _ctx: TransitionContext) -> bool:
    return risk.treatment_strategy in ("Accept", "Mitigate", "Transfer", "Avoid")


# -- the machine -----------------------------------------------------------

RISK_MACHINE = StateMachine(
    entity="risk",
    state_field="lifecycle_state",
    initial="Intake",
    states=RISK_STATES,
    terminal=("Closed",),
    transitions=[
        Transition(
            source="Intake",
            target="Preconditions",
            gate="GATE_INTAKE_COMPLETE",
            description="Structured risk statement complete and admitted to the register.",
            roles=("Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "GATE_INTAKE_COMPLETE.1",
                    "Structured risk statement complete",
                    _statement_complete,
                    "Cause, threat event, vulnerability and impact must all be populated. "
                    "Impact must reference business consequence, not technical failure alone.",
                ),
            ),
            cascades=("risk.admitted",),
        ),
        Transition(
            source="Preconditions",
            target="Scoring",
            gate="GATE_PRECONDITIONS_MET",
            description="All four scoring preconditions satisfied. Enforces RINV-8.",
            roles=("Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "RINV-8.1",
                    "True risk confirmed",
                    lambda r, c: r.pre_true_risk_confirmed,
                    "Triage must confirm this is a risk and not an issue or out-of-scope item.",
                ),
                Precondition(
                    "RINV-8.2",
                    "Risk tier assigned",
                    lambda r, c: r.pre_tier_assigned and bool(r.tier),
                    "Assign a NIST RMF tier (1-4) with documented rationale before scoring.",
                ),
                Precondition(
                    "RINV-8.3",
                    "All stakeholders identified",
                    lambda r, c: r.pre_stakeholders_identified,
                    "Risk Owner, Risk Analyst, Treatment Owner, Control Owner(s) and "
                    "Control Operator(s) must all be named.",
                ),
                Precondition(
                    "RINV-8.4",
                    "Control effectiveness assessed with evidence",
                    lambda r, c: r.pre_ce_assessed,
                    "At least one linked control must carry a CE rating above Unvalidated "
                    "with an evidence reference.",
                ),
            ),
        ),
        Transition(
            source="Scoring",
            target="Treatment",
            gate="GATE_SCORING_COMPLETE",
            description="Inherent score computed and ownership assigned. Enforces RINV-10.",
            roles=("Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "GATE_SCORING_COMPLETE.1",
                    "Inherent impact and likelihood scored",
                    _inherent_scored,
                    "Both axes must be scored 1-5 and the inherent rating derived.",
                ),
                Precondition(
                    "RINV-10",
                    "Risk Owner and Risk Stakeholder assigned",
                    _ownership_assigned,
                    "Every risk carries both a Risk Owner and a Risk Stakeholder. "
                    "They must be different people (SEP-1).",
                ),
                Precondition(
                    "IMP-2",
                    "Impact justification recorded",
                    lambda r, c: bool(r.impact_justification),
                    "Impact scores require a documented rationale within the tier scope.",
                ),
            ),
            cascades=("risk.inherent_locked",),
        ),
        Transition(
            source="Treatment",
            target="Readout",
            gate="GATE_TREATMENT_ALIGNED",
            description="Treatment designed, validated and committed. Enforces RINV-12.",
            roles=("Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "GATE_TREATMENT_ALIGNED.1",
                    "Treatment decision selected",
                    _strategy_selected,
                    "Select Accept, Mitigate, Transfer or Avoid.",
                ),
                Precondition(
                    "GATE_TREATMENT_ALIGNED.2",
                    "At least one treatment linked",
                    _has_treatment,
                    "A Mitigate decision requires at least one linked treatment record.",
                ),
                Precondition(
                    "RINV-12.1",
                    "GRC Engineer feasibility validation complete",
                    _treatments_validated,
                    "Every linked treatment must be validated as technically feasible by a "
                    "GRC Engineer before it can be presented at readout.",
                ),
                Precondition(
                    "RINV-12.2",
                    "Treatment owner commitment confirmed",
                    _owners_committed,
                    "Every linked treatment must carry an explicit commitment from its owner.",
                ),
                Precondition(
                    "GATE_TREATMENT_ALIGNED.5",
                    "Control framework mapping documented",
                    _control_mapping_documented,
                    "A Mitigate decision must map to the control framework, either by "
                    "linking controls or by documenting the mapping.",
                ),
            ),
            cascades=("risk.readout_queued",),
        ),
        Transition(
            source="Readout",
            target="Evidence_Residual",
            gate="GATE_READOUT_COMPLETE",
            description="Governance readout conducted. Enforces RINV-6.",
            roles=("Risk_Analyst", "Risk_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "RINV-6",
                    "Readout conducted and confirmed by the Risk Owner",
                    _readout_done,
                    "Risks rated Moderate or above cannot bypass governance readout. "
                    "Record the readout date and the Risk Owner's confirmation.",
                ),
            ),
        ),
        Transition(
            source="Evidence_Residual",
            target="Monitoring",
            gate="GATE_RESIDUAL_VALIDATED",
            description=(
                "All five residual conditions satisfied and residual score recorded. "
                "Enforces RINV-1."
            ),
            roles=("Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "RESIDUAL.1",
                    "Mitigations fully implemented",
                    _treatments_complete,
                    "Every linked treatment must be Complete. Planned mitigations do not "
                    "reduce residual risk (RINV-9).",
                ),
                Precondition(
                    "RESIDUAL.2",
                    "Evidence provided",
                    _residual_gate("evidence_provided"),
                    "Attach configs, logs, dashboards or audit artefacts and record the "
                    "evidence reference. Verbal attestation is not evidence (CE-2).",
                ),
                Precondition(
                    "RESIDUAL.3",
                    "Treatment effectiveness confirmed by Risk Analyst",
                    _residual_gate("effectiveness_confirmed"),
                    "Independent confirmation by the Risk Analyst. Self-assessment by the "
                    "treatment owner does not satisfy this condition.",
                ),
                Precondition(
                    "RESIDUAL.4",
                    "Governance approval documented",
                    _residual_gate("governance_approved"),
                    "Record the approver identity and timestamp.",
                ),
                Precondition(
                    "RESIDUAL.5",
                    "Risk drift tracked over the treatment period",
                    _residual_gate("drift_tracked"),
                    "The drift log must show the inherent-versus-residual delta across the "
                    "treatment period so degradation during treatment is visible.",
                ),
                Precondition(
                    "RINV-1",
                    "Residual score recorded",
                    _residual_scored,
                    "Residual impact and likelihood must be scored once the gate releases "
                    "the lock.",
                ),
                Precondition(
                    "CINV-5",
                    "No linked control is in Failure",
                    _no_open_control_failure,
                    "A control this risk depends on is in Failure state. Residual scoring is "
                    "frozen until it is remediated or the linkage is re-assessed.",
                ),
            ),
            cascades=("risk.monitoring_started",),
        ),
        # Re-assessment. Monitoring returns to Preconditions for a full traversal
        # with updated data; the inherent score is unlocked for a new cycle rather
        # than edited in place (OUT-5).
        Transition(
            source="Monitoring",
            target="Preconditions",
            gate="GATE_REASSESSMENT",
            description=(
                "Re-assessment triggered by control change, acceptance expiry, SLA breach "
                "or external event. Starts a new scoring cycle."
            ),
            roles=("Risk_Analyst", "GRC_Engineer", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "GATE_REASSESSMENT.1",
                    "Re-assessment reason recorded",
                    lambda r, c: bool(
                        r.control_change_flag
                        or r.escalation_flag
                        or c.payload.get("reason")
                    ),
                    "Record why the risk is being re-assessed.",
                ),
            ),
            cascades=("risk.reassessment_started",),
        ),
        Transition(
            source="Monitoring",
            target="Closed",
            gate="GATE_CLOSURE",
            description="Risk closed with documented rationale.",
            roles=("Risk_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "GATE_CLOSURE.1",
                    "Closure rationale documented",
                    _closable,
                    "Record why the risk is being closed.",
                ),
                Precondition(
                    "GATE_CLOSURE.2",
                    "Treatment decision resolved",
                    _treatment_resolved_for_closure,
                    "A risk cannot close without a recorded treatment decision.",
                ),
            ),
            cascades=("risk.closed",),
        ),
        Transition(
            source="Closed",
            target="Preconditions",
            gate="GATE_REOPEN",
            description="Reopen a closed risk. Starts a fresh assessment cycle.",
            roles=("CISO", "Admin"),
            preconditions=(
                Precondition(
                    "GATE_REOPEN.1",
                    "Reopen reason recorded",
                    lambda r, c: bool(c.payload.get("reason")),
                    "Record why the risk is being reopened.",
                ),
            ),
            cascades=("risk.reassessment_started",),
        ),
    ],
)


def allowed_next(risk: Risk) -> tuple[str, ...]:
    return RISK_MACHINE.targets_from(risk.lifecycle_state)


def machine_definition() -> dict[str, Any]:
    return RISK_MACHINE.describe()
