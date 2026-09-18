"""Threat model lifecycle, declared.

Scope -> Decomposition -> Threat_Analysis -> Mitigation_Design -> Review <-> Active
                                                                    -> Deprecated
Anything short of Active can be Abandoned.

The Review -> Active gate is where TINV-1 and TINV-2 land together: every scenario
must have resolved to a legal end state, and two independent signatures must be
present. The reverse edge exists because a control failure strips those signatures.
"""

from __future__ import annotations

from app.core.governance import governance
from app.engine import Precondition, StateMachine, Transition, TransitionContext
from app.modules.threat.models import THREAT_MODEL_STATES, ThreatModel


def _has_attack_surface(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    return bool(tm.attack_surface_id)


def _has_component(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    return len(tm.components) > 0


def _has_trust_boundary(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    return tm.has_trust_boundary or len(tm.components) > 0


def _has_scenario(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    return len(tm.scenarios) > 0


def _high_severity_handled(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    """Every Critical and High scenario must be mitigated or flagged for promotion
    before the model can go to review."""
    return len(tm.unhandled_high_severity) == 0


def _all_scenarios_resolved(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    """TINV-1: mitigation, a valid local Low acceptance, or promotion. Nothing
    may be left simply Identified."""
    return len(tm.unresolved_scenarios) == 0


def _appsec_signoff(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    return bool(tm.appsec_signoff_by) and tm.appsec_signoff_at is not None


def _owner_signoff(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    return bool(tm.owner_signoff_by) and tm.owner_signoff_at is not None


def _signoffs_independent(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    """TINV-2: AppSec sign-off must come from someone other than the system owner."""
    if not tm.appsec_signoff_by or not tm.owner_signoff_by:
        return True  # the presence checks above report the real failure
    return tm.appsec_signoff_by != tm.owner_signoff_by


def _sensitive_components_zoned(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    """TINV-9. Data at or above the sensitive threshold needs a declared zone.

    Where a component sits is half of what a compromise costs, so a crown-jewel
    datastore with no trust zone is an incomplete decomposition rather than a
    complete one with a blank field.
    """
    return all(
        bool(c.trust_zone) for c in tm.components if c.is_sensitive
    )


def _sensitive_components_analysed(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    """TINV-11. Every sensitive component carries at least one scenario.

    The failure mode this catches is silence: a component decomposed, labelled
    Restricted, and then never thought about. A scenario list cannot surface its
    own omissions, so the gate walks the decomposition instead.
    """
    analysed = {s.component_id for s in tm.scenarios}
    return all(c.id in analysed for c in tm.components if c.is_sensitive)


def _scenarios_have_rationale(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    """TINV-10. Every resolved scenario carries a reason for its resolution."""
    for s in tm.scenarios:
        if s.status == "Accepted" and not s.acceptance_rationale:
            return False
        if s.status == "Mitigated" and not (s.mitigations or s.status_rationale):
            return False
    return True


def _mitigations_backed_by_live_controls(tm: ThreatModel, _ctx: TransitionContext) -> bool:
    """TINV-4: a scenario is only Mitigated while the deployment mitigating it is
    actually running."""
    for scenario in tm.scenarios:
        if scenario.status != "Mitigated":
            continue
        if not scenario.mitigations:
            return False
        if not any(
            link.deployment is not None
            and link.deployment.deployment_status in ("Active", "Degraded")
            for link in scenario.mitigations
        ):
            return False
    return True


THREAT_MODEL_MACHINE = StateMachine(
    entity="threat_model",
    state_field="lifecycle_state",
    initial="Scope",
    states=THREAT_MODEL_STATES,
    terminal=("Deprecated", "Abandoned"),
    transitions=[
        Transition(
            source="Scope",
            target="Decomposition",
            gate="GATE_TM_DECOMPOSITION",
            description="Model scoped to at least one attack surface.",
            roles=("AppSec_Lead", "AppSec_Engineer", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(
                Precondition(
                    "TM-1",
                    "At least one attack surface linked",
                    _has_attack_surface,
                    "Scope the model to an asset in the register.",
                ),
            ),
        ),
        Transition(
            source="Decomposition",
            target="Threat_Analysis",
            gate="GATE_TM_ANALYSIS",
            description="At least one trust boundary or component defined.",
            roles=("AppSec_Lead", "AppSec_Engineer", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(
                Precondition(
                    "TM-2",
                    "At least one component or trust boundary defined",
                    _has_trust_boundary,
                    "Decompose the system into processes, datastores, flows and boundaries.",
                ),
                Precondition(
                    "TM-2.1",
                    "Components declare what data they handle",
                    lambda tm, c: all(
                        bool(comp.data_classification)
                        for comp in tm.components
                        if comp.component_type in ("Process", "Datastore", "Data_Flow")
                    ),
                    "Classify the data each process, datastore and flow handles. What a "
                    "component handles determines what its compromise costs, so threat "
                    "analysis cannot be scoped without it.",
                ),
            ),
        ),
        Transition(
            source="Threat_Analysis",
            target="Mitigation_Design",
            gate="GATE_TM_MITIGATION",
            description="At least one threat scenario identified.",
            roles=("AppSec_Lead", "AppSec_Engineer", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(
                Precondition(
                    "TM-3",
                    "At least one threat scenario identified",
                    _has_scenario,
                    "Identify threats against the decomposed components.",
                ),
            ),
        ),
        Transition(
            source="Mitigation_Design",
            target="Review",
            gate="GATE_TM_REVIEW",
            description="All Critical and High scenarios assigned a mitigation or promotion.",
            roles=("AppSec_Lead", "AppSec_Engineer", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(
                Precondition(
                    "TM-4",
                    "All Critical and High scenarios handled",
                    _high_severity_handled,
                    "Every Critical and High scenario must carry a mitigation or be flagged "
                    "for promotion to the risk register before review.",
                ),
            ),
        ),
        Transition(
            source="Review",
            target="Mitigation_Design",
            gate="GATE_TM_REWORK",
            description="Reviewer returns the model for further mitigation work.",
            roles=("AppSec_Lead", "AppSec_Engineer", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(),
        ),
        Transition(
            source="Review",
            target="Active",
            gate="GATE_TM_SIGNOFF",
            description="Dual sign-off and all scenarios resolved. Enforces TINV-1 and TINV-2.",
            roles=("AppSec_Lead", "AppSec_Engineer", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(
                Precondition(
                    "TINV-1",
                    "Every scenario resolved to a permitted end state",
                    _all_scenarios_resolved,
                    "Each scenario must be Mitigated, locally Accepted (Low severity only), "
                    "or Promoted to the risk register. None may remain Identified.",
                ),
                Precondition(
                    "TINV-4",
                    "Every mitigation is backed by a live control deployment",
                    _mitigations_backed_by_live_controls,
                    "A scenario marked Mitigated must link to a control deployment that is "
                    "Active or Degraded. A planned or failed control does not mitigate.",
                ),
                Precondition(
                    "TINV-9",
                    "Sensitive components declare a trust zone",
                    _sensitive_components_zoned,
                    "A component handling data at or above the configured sensitivity "
                    "threshold must declare where it sits. Where it sits is half of "
                    "what a compromise costs.",
                ),
                Precondition(
                    "TINV-11",
                    "Every sensitive component has been analysed",
                    _sensitive_components_analysed,
                    "A component was decomposed and labelled sensitive but carries no "
                    "threat scenario. Silence on a crown-jewel component is the one "
                    "omission a scenario list cannot surface by itself.",
                ),
                Precondition(
                    "TINV-10",
                    "Every resolved scenario carries a rationale",
                    _scenarios_have_rationale,
                    "Accepting or mitigating a scenario is a decision. Record why.",
                ),
                Precondition(
                    "TINV-2.1",
                    "AppSec sign-off recorded",
                    _appsec_signoff,
                    "An AppSec Lead or Engineer must sign off.",
                ),
                Precondition(
                    "TINV-2.2",
                    "System Owner sign-off recorded",
                    _owner_signoff,
                    "The System Owner must sign off.",
                ),
                Precondition(
                    "TINV-2.3",
                    "Sign-offs are independent",
                    _signoffs_independent,
                    "The AppSec signature and the System Owner signature cannot be the "
                    "same person.",
                ),
            ),
            cascades=("threat_model.activated",),
        ),
        Transition(
            source="Active",
            target="Review",
            gate="GATE_TM_REOPENED",
            description=(
                "A mitigating control failed or the architecture changed. Sign-offs are "
                "stripped and the model returns to review."
            ),
            roles=("AppSec_Lead", "AppSec_Engineer", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(),
            cascades=("threat_model.reopened",),
        ),
        Transition(
            source="Active",
            target="Deprecated",
            gate="GATE_TM_DEPRECATED",
            description="Feature or system decommissioned. Drops mapping to enterprise controls.",
            roles=("AppSec_Lead", "System_Owner", "CISO", "Admin"),
            preconditions=(
                Precondition(
                    "TM-5",
                    "Deprecation reason recorded",
                    lambda tm, c: bool(c.payload.get("reason")),
                    "Record why the threat model is being retired.",
                ),
            ),
        ),
        Transition(
            source="*",
            target="Abandoned",
            gate="GATE_TM_ABANDONED",
            description="Model abandoned before reaching Active.",
            roles=("AppSec_Lead", "System_Owner", "GRC_Engineer", "Admin"),
            preconditions=(
                Precondition(
                    "TM-6",
                    "Model has not been signed off",
                    lambda tm, c: tm.lifecycle_state != "Active",
                    "An Active threat model is deprecated, not abandoned.",
                ),
                Precondition(
                    "TM-7",
                    "Abandonment reason recorded",
                    lambda tm, c: bool(c.payload.get("reason")),
                    "Record why the model is being abandoned.",
                ),
            ),
        ),
    ],
)
