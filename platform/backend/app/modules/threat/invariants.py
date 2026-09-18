"""Threat management invariants (TINV-1 .. TINV-5)."""

from __future__ import annotations

from datetime import date, timedelta

from app.core.governance import governance
from app.engine import BOTH, SCHEMA, SERVICE, Invariant, invariants
from app.modules.threat.models import SEVERITY_ORDER, ThreatModel, ThreatScenario

MODEL = "threat_model"
SCENARIO = "threat_scenario"


def _scenario_resolves(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-1: a scenario may rest at Mitigated, Accepted (Low only) or
    Promoted_To_Risk. Identified is a working state, not a resting one, so it is
    only invalid once the parent model has been signed off."""
    if scenario.status != "Identified":
        return True
    model = scenario.model
    return model is None or model.lifecycle_state != "Active"


def _dual_signoff(model: ThreatModel, _ctx) -> bool:
    if model.lifecycle_state != "Active":
        return True
    return (
        bool(model.appsec_signoff_by)
        and bool(model.owner_signoff_by)
        and model.appsec_signoff_by != model.owner_signoff_by
    )


def _no_local_acceptance_above_low(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-3."""
    if scenario.status != "Accepted":
        return True
    return (
        SEVERITY_ORDER[scenario.inherent_severity]
        < governance.minimum_promotable_severity_rank
    )


def _mitigation_requires_live_control(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-4."""
    if scenario.status != "Mitigated":
        return True
    if not scenario.mitigations:
        return False
    return any(
        link.deployment is not None
        and link.deployment.deployment_status in ("Active", "Degraded")
        for link in scenario.mitigations
    )


def _acceptance_expiry_within_12_months(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-5."""
    if scenario.status != "Accepted":
        return True
    if scenario.acceptance_expiry is None:
        return False
    limit = date.today() + timedelta(days=governance.threat_local_acceptance_max_days)
    return date.today() <= scenario.acceptance_expiry <= limit


def _promotion_linked(scenario: ThreatScenario, _ctx) -> bool:
    if scenario.status != "Promoted_To_Risk":
        return True
    return bool(scenario.promoted_risk_id)


invariants.register(
    Invariant(
        id="TINV-1",
        entity=SCENARIO,
        rule=(
            "Every threat scenario resolves to mitigation, local acceptance (Low only), or "
            "promotion to the risk register"
        ),
        layer=SERVICE,
        mechanism="Review to Active gate blocks while any scenario is still Identified",
        violation="Phase transition from Review to Active blocked",
        spec_ref="codified-rules section 19.3",
        holds=_scenario_resolves,
    ),
    Invariant(
        id="TINV-2",
        entity=MODEL,
        rule=(
            "A threat model cannot be Active without independent AppSec and System Owner "
            "sign-off"
        ),
        layer=BOTH,
        mechanism=(
            "CHECK constraint blocks AppSec sign-off by the system owner; the Review gate "
            "requires both signatures present"
        ),
        violation="Phase transition blocked until both signatures are present",
        spec_ref="codified-rules section 19.3",
        holds=_dual_signoff,
    ),
    Invariant(
        id="TINV-3",
        entity=SCENARIO,
        rule="Medium, High and Critical threat scenarios are never locally accepted",
        layer=BOTH,
        mechanism="CHECK constraint plus service rejection; promotion is the only other path",
        violation="Rejected; promotion to the risk register required",
        spec_ref="codified-rules section 19.3",
        holds=_no_local_acceptance_above_low,
    ),
    Invariant(
        id="TINV-4",
        entity=SCENARIO,
        rule="Full mitigation of a threat scenario requires an active, linked control deployment",
        layer=BOTH,
        mechanism=(
            "FK to control_deployments plus a service check that the deployment is Active or "
            "Degraded; a control failure re-opens the scenario"
        ),
        violation="Cannot flag the scenario as Mitigated",
        spec_ref="codified-rules section 19.3",
        holds=_mitigation_requires_live_control,
    ),
    Invariant(
        id="TINV-5",
        entity=SCENARIO,
        rule=(
            "A locally accepted Low severity scenario carries an acceptance expiry no more "
            "than 12 months out"
        ),
        layer=BOTH,
        mechanism="CHECK constraint requires an expiry; service caps the window at 12 months",
        violation="Rejected; expiry required and capped",
        spec_ref="codified-rules section 19.3",
        holds=_acceptance_expiry_within_12_months,
    ),
    Invariant(
        id="TINV-6",
        entity=SCENARIO,
        rule="A promoted scenario always names the risk record it produced",
        layer=BOTH,
        mechanism="CHECK constraint requires promoted_risk_id when status is Promoted_To_Risk",
        violation="Write rejected; promotion must create and link a risk record",
        spec_ref="data-model section 8",
        holds=_promotion_linked,
    ),
)
