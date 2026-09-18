"""Threat management invariants (TINV-1 .. TINV-11).

TINV-1..6 govern the scenario lifecycle. TINV-7..11 govern the connective
tissue between threat modelling and the rest of GRC: what the environment is
allowed to do to a model, and what a decomposition must account for.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.governance import governance
from app.engine import BOTH, SCHEMA, SERVICE, Invariant, invariants
from app.modules.threat.models import (
    SEVERITY_ORDER,
    ThreatComponent,
    ThreatModel,
    ThreatScenario,
)

MODEL = "threat_model"
SCENARIO = "threat_scenario"
COMPONENT = "threat_component"


def _scenario_resolves(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-1: a scenario may rest at Mitigated, locally Accepted below the
    promotion threshold, or carried by the risk register (whether promoted into
    a new record or referencing an existing one).

    Identified is a working state, not a resting one, so it is only invalid once
    the parent model has been signed off.
    """
    if scenario.is_resolved:
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


def _no_partial_link_while_mitigated(scenario: ThreatScenario, _ctx) -> bool:
    """TM-PARTIAL. Partial coverage is an open threat, not a mitigated one.

    A distinct "Partially Mitigated" state may be derived for display from the
    link table, but it is not a status value: allowing it would let a scenario
    pass the sign-off gate on coverage nobody claimed was complete.
    """
    if scenario.status != "Mitigated":
        return True
    return not scenario.has_partial_mitigation


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


def _mitigation_is_deliberate(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-7. A scenario is never Mitigated by the mere presence of a control on
    the asset. Mitigation is an explicit link asserted by a person.

    This is the threat-modelling analogue of LKH-3. Environmental context is
    informative; identification and resolution happen against the architecture as
    designed. A scenario marked Mitigated with no link is a scenario that was
    resolved by ambient control posture, which is exactly what this forbids.
    """
    if scenario.status != "Mitigated":
        return True
    return len(scenario.mitigations) > 0


def _no_duplicate_register_entry(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-8. A scenario either promotes into a new risk or references existing
    ones. Doing both mints a duplicate of an exposure the register already holds.
    """
    creating = [
        link
        for link in scenario.risk_links
        if link.link_type
        in {t["id"] for t in governance.risk_link_type_detail if t.get("creates_risk")}
    ]
    if len(creating) > 1:
        return False
    if scenario.promoted_risk_id and creating:
        # The promotion link is the one creating entry; a second is a duplicate.
        return creating[0].risk_id == scenario.promoted_risk_id
    return True


def _sensitive_component_is_zoned(component: ThreatComponent, _ctx) -> bool:
    """TINV-9. Data at or above the sensitive threshold cannot float outside a
    declared trust zone. Where it sits is half of what a compromise costs.
    """
    if not component.is_sensitive:
        return True
    return bool(component.trust_zone)


def _evidence_supports_status(scenario: ThreatScenario, _ctx) -> bool:
    """TINV-10. A status change is a decision, and a decision carries a reason.

    Accepted and Mitigated are assertions about the world; Identified is not, so
    only the assertions require rationale.
    """
    if scenario.status in ("Identified",):
        return True
    if scenario.status == "Accepted":
        return bool(scenario.acceptance_rationale)
    return bool(scenario.status_rationale) or len(scenario.mitigations) > 0 or bool(
        scenario.promoted_risk_id
    )


def _sensitive_components_analysed(model: ThreatModel, _ctx) -> bool:
    """TINV-11. A signed-off model has no unanalysed sensitive component.

    If you decomposed it and said it handles Restricted data, the model has to
    show you thought about it. Silence on a crown-jewel component is the failure
    mode a scenario list cannot surface on its own.
    """
    if model.lifecycle_state != "Active":
        return True
    analysed = {s.component_id for s in model.scenarios}
    for component in model.components:
        if component.is_sensitive and component.id not in analysed:
            return False
    return True


invariants.register(
    Invariant(
        id="TINV-1",
        entity=SCENARIO,
        rule=(
            "Every threat scenario reaches a permitted end state: mitigated, locally "
            "accepted below the promotion threshold, or carried by the risk register"
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
    Invariant(
        id="TM-PARTIAL",
        entity=SCENARIO,
        rule=(
            "A scenario is never Mitigated while any of its mitigation links asserts "
            "only partial coverage"
        ),
        layer=SERVICE,
        mechanism=(
            "Status is derived from the whole link set, not the link being added. "
            "A partial link added to a mitigated scenario returns it to Identified."
        ),
        violation="Status reverts to Identified; partial coverage is an open threat",
        spec_ref="codified-rules section 19.3 (TM-PARTIAL)",
        holds=_no_partial_link_while_mitigated,
    ),
    Invariant(
        id="TINV-7",
        entity=SCENARIO,
        rule=(
            "Environmental control posture is informative, never determinative: a "
            "scenario is never resolved by the ambient presence of a control"
        ),
        layer=SERVICE,
        mechanism=(
            "The context engine is read-only and cannot write to a scenario. "
            "Mitigated requires an explicit threat_mitigation_links row asserted by "
            "a person. Analogue of LKH-3 for threat identification."
        ),
        violation="Mitigated status rejected when no mitigation link exists",
        spec_ref="codified-rules section 19.4",
        holds=_mitigation_is_deliberate,
    ),
    Invariant(
        id="TINV-8",
        entity=SCENARIO,
        rule=(
            "A scenario either promotes into a new risk or references existing ones, "
            "never both; the register never gains a duplicate exposure"
        ),
        layer=SERVICE,
        mechanism=(
            "Exactly one configured risk link type may create a risk record. "
            "Linking to an existing risk is a reference, not a promotion."
        ),
        violation="Link rejected; reference the existing risk instead of promoting again",
        spec_ref="codified-rules section 19.5",
        holds=_no_duplicate_register_entry,
    ),
    Invariant(
        id="TINV-9",
        entity=COMPONENT,
        rule=(
            "A component handling data at or above the sensitive threshold must "
            "declare the trust zone it sits in"
        ),
        layer=SERVICE,
        mechanism="Component save validates trust_zone against the configured zones",
        violation="Save rejected; declare where the component sits",
        spec_ref="codified-rules section 19.1",
        holds=_sensitive_component_is_zoned,
    ),
    Invariant(
        id="TINV-10",
        entity=SCENARIO,
        rule="A scenario status change always carries a rationale or a linked artefact",
        layer=SERVICE,
        mechanism=(
            "Accepted requires acceptance rationale; Mitigated requires a link or "
            "rationale. Evidence records are append-only at the database layer."
        ),
        violation="Status change rejected without a reason",
        spec_ref="codified-rules section 19.5",
        holds=_evidence_supports_status,
    ),
    Invariant(
        id="TINV-11",
        entity=MODEL,
        rule=(
            "An Active threat model has no sensitive component without at least one "
            "threat scenario"
        ),
        layer=SERVICE,
        mechanism="Review to Active gate walks every component above the classification threshold",
        violation="Sign-off blocked; the component was decomposed but never analysed",
        spec_ref="codified-rules section 19.4",
        holds=_sensitive_components_analysed,
    ),
)
