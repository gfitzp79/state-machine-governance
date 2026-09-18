"""Compliance and assurance invariants (AINV).

Two of these are unusual and worth naming.

AINV-3 says partial coverage is a gap. It is the direct analogue of TM-PARTIAL,
and it exists for the same reason: a requirement half-satisfied is a requirement
not satisfied, and giving partial coverage a status of its own would let it
close out a Statement of Applicability.

AINV-6 makes a licence obligation enforceable. A framework whose text this
repository may not redistribute is refused at load time if it carries text.
That turns "do not commit ISO content" from a note in a README, which is the
kind of control this project exists to argue against, into a boot-time refusal.
"""

from __future__ import annotations

from datetime import date

from app.core.governance import governance
from app.engine import BOTH, SCHEMA, SERVICE, Invariant, invariants
from app.modules.compliance.models import (
    ComplianceFramework,
    ComplianceRequirement,
    ControlRequirementLink,
    RequirementAssessment,
)

ASSESSMENT = "requirement_assessment"
FRAMEWORK = "compliance_framework"
LINK = "control_requirement_link"


def _exclusion_justified(a: RequirementAssessment, _ctx) -> bool:
    """AINV-1."""
    if a.lifecycle_state != "Not_Applicable":
        return True
    return bool(a.rationale and a.rationale.strip())


def _coverage_backed_by_live_control(a: RequirementAssessment, ctx) -> bool:
    """AINV-2, checked on every write rather than only at the gate.

    The gate decides whether a requirement may become Covered. This decides
    whether it may REMAIN Covered, which is the half that matters: controls
    decay, deployments fail, and a register that only checks on the way in
    reports a posture that was true once.
    """
    if a.lifecycle_state != "Covered":
        return True

    # Deliberately the same predicate the gate uses. A rule enforced one way on
    # entry and another way thereafter is two rules wearing one name.
    from app.modules.compliance.machine import _coverage_is_live

    return _coverage_is_live(a, ctx)


def _partial_does_not_satisfy(a: RequirementAssessment, _ctx) -> bool:
    """AINV-3.

    A requirement resting only on Partial links is not covered. Note this is
    derived from the whole link set, not from the link being added, so
    downgrading the last Full link to Partial re-opens the requirement rather
    than leaving a stale Covered behind.
    """
    if a.lifecycle_state != "Covered":
        return True
    return bool(a.requirement.satisfying_links)


def _compensating_time_bound(a: RequirementAssessment, _ctx) -> bool:
    """AINV-4."""
    if a.lifecycle_state != "Compensating":
        return True
    if a.compensating_expiry is None:
        return False
    return a.compensating_expiry >= date.today()


def _framework_licence_respected(f: ComplianceFramework, _ctx) -> bool:
    """AINV-6.

    A framework the repository may not redistribute must not carry requirement
    prose. Identifiers and the organisation's own imported text are fine: the
    rule is about what ships in this tree, and an operator's licensed import
    lives in their database, never in the catalogue file.
    """
    if f.redistributable:
        return True
    return not f.carries_text


def _version_immutable(f: ComplianceFramework, ctx) -> bool:
    """AINV-7.

    ISO 27001:2013 to :2022 renumbered and merged controls. Editing the version
    in place would silently re-point every coverage assertion at a clause that
    may no longer mean the same thing, and the Statement of Applicability would
    still look complete. A new version is a new record.
    """
    proposed = ctx.payload.get("version") if hasattr(ctx, "payload") else None
    if proposed is None or proposed == f.version:
        return True
    return f.requirement_count == 0


def _assessment_on_adopted_framework(a: RequirementAssessment, _ctx) -> bool:
    """AINV-8: only an adopted framework carries a position.

    Un-adopting a framework does not delete the work; it means the assessments
    are no longer claims the organisation is making, so they must not be
    counted in a posture figure.
    """
    if a.lifecycle_state == "Not_Assessed":
        return True
    return bool(a.requirement.framework.adopted)


def _scoped_assets_exist_for_covered(a: RequirementAssessment, ctx) -> bool:
    """AINV-9.

    With no asset in scope, AINV-2 falls back to accepting a live deployment
    anywhere, so a framework nobody has scoped would report coverage off an
    estate it was never assessed against. A confident percentage over an
    undeclared scope is the most dangerous number a compliance tool can print,
    so an adopted framework must have at least one asset in scope before any of
    its requirements may be Covered.
    """
    from app.modules.control.models import AttackSurface

    if a.lifecycle_state != "Covered":
        return True
    framework_id = a.requirement.framework.framework_id
    assets = ctx.session.query(AttackSurface).all()
    return any(framework_id in (asset.compliance_scopes or []) for asset in assets)


def _link_level_is_configured(link: ControlRequirementLink, _ctx) -> bool:
    """AINV-10: a coverage level outside the configured set is meaningless.

    The invariants read `satisfies` off the configuration. A level absent from
    it would be neither satisfying nor non-satisfying, and would silently fail
    to count.
    """
    return link.coverage_level in governance.coverage_levels


def _key_control_assurance(link: ControlRequirementLink, _ctx) -> bool:
    """CINV-12 applied at the point it bites.

    A key control assessed only by asking somebody whether it works is not
    assured. The floor is configurable; that there is a floor is not.
    """
    objective = link.objective
    if objective is None or not objective.is_key_control:
        return True
    rank = governance.assurance_rank
    floor = rank.get(governance.key_control_minimum_assurance, 0)
    return rank.get(objective.assurance_method, -1) >= floor


invariants.register(
    Invariant(
        id="AINV-1",
        entity=ASSESSMENT,
        rule="An excluded requirement always carries a documented justification",
        layer=BOTH,
        mechanism=(
            "CHECK constraint requires a rationale when the state is "
            "Not_Applicable, plus a gate precondition on the exclusion transition"
        ),
        violation="Exclusion rejected; a Statement of Applicability must justify every omission",
        spec_ref="codified-rules section 22.2",
        holds=_exclusion_justified,
    ),
    Invariant(
        id="AINV-2",
        entity=ASSESSMENT,
        rule=(
            "A requirement is Covered only while a satisfying control is Operating "
            "and live where the requirement applies"
        ),
        layer=SERVICE,
        mechanism=(
            "Gate and invariant share one predicate: a satisfying link, an "
            "Operating objective, and a live deployment inside the framework's "
            "scope. Re-checked on every write, so coverage cannot outlive the "
            "control that carried it. Analogue of TINV-4 for compliance."
        ),
        violation="Covered rejected or revoked; the requirement returns to Gap",
        spec_ref="codified-rules section 23.1",
        holds=_coverage_backed_by_live_control,
    ),
    Invariant(
        id="AINV-3",
        entity=ASSESSMENT,
        rule="Partial coverage is a gap, never coverage",
        layer=SERVICE,
        mechanism=(
            "Satisfying levels are read from configuration, and status is derived "
            "from the whole link set. Downgrading the last Full link to Partial "
            "re-opens the requirement. Analogue of TM-PARTIAL."
        ),
        violation="Covered rejected; a requirement half-satisfied is not satisfied",
        spec_ref="codified-rules section 23.2",
        holds=_partial_does_not_satisfy,
    ),
    Invariant(
        id="AINV-4",
        entity=ASSESSMENT,
        rule="A compensating position is never permanent; it is always time-bound",
        layer=BOTH,
        mechanism=(
            "CHECK constraint requires an expiry; the gate caps the window and a "
            "scheduled job expires it. Same principle as RINV-4 and TINV-5."
        ),
        violation="Rejected; set an expiry within the configured window",
        spec_ref="codified-rules section 23.3",
        holds=_compensating_time_bound,
    ),
    Invariant(
        id="AINV-6",
        entity=FRAMEWORK,
        rule=(
            "A framework whose content may not be redistributed never carries "
            "requirement text in this repository"
        ),
        layer=SERVICE,
        mechanism=(
            "The catalogue loader refuses at boot. Licensed content is imported "
            "into the database by the operator, never into the tree."
        ),
        violation="Boot refused; the licence is enforced rather than documented",
        spec_ref="codified-rules section 21.2",
        holds=_framework_licence_respected,
    ),
    Invariant(
        id="AINV-7",
        entity=FRAMEWORK,
        rule="A framework version is immutable once its requirements are loaded",
        layer=SERVICE,
        mechanism=(
            "Version changes are rejected while requirements exist. A new version "
            "is a new record, because renumbering between versions would silently "
            "re-point existing coverage assertions."
        ),
        violation="Version change rejected; create the new version as its own framework",
        spec_ref="codified-rules section 21.3",
        holds=_version_immutable,
    ),
    Invariant(
        id="AINV-8",
        entity=ASSESSMENT,
        rule="Only an adopted framework carries an assessed position",
        layer=SERVICE,
        mechanism="Gate blocks assessment on an unadopted framework",
        violation="Assessment rejected; adopt the framework first",
        spec_ref="codified-rules section 21.4",
        holds=_assessment_on_adopted_framework,
    ),
    Invariant(
        id="AINV-9",
        entity=ASSESSMENT,
        rule=(
            "No requirement of an adopted framework is Covered while no asset "
            "declares itself in that framework's scope"
        ),
        layer=SERVICE,
        mechanism=(
            "With no scope declared, AINV-2 accepts a live deployment anywhere. "
            "This refuses the undeclared case explicitly, so a percentage is "
            "never reported against an estate nobody assessed."
        ),
        violation="Covered rejected; declare the assets the framework applies to",
        spec_ref="codified-rules section 23.1",
        holds=_scoped_assets_exist_for_covered,
    ),
    Invariant(
        id="AINV-10",
        entity=LINK,
        rule="A coverage assertion always uses a configured coverage level",
        layer=SERVICE,
        mechanism="Level validated against compliance.coverage_levels on write",
        violation="Link rejected; an unconfigured level would silently fail to count",
        spec_ref="codified-rules section 23.2",
        holds=_link_level_is_configured,
    ),
    Invariant(
        id="CINV-12",
        entity=LINK,
        rule=(
            "A key control never evidences a requirement on assurance weaker than "
            "the configured floor"
        ),
        layer=SERVICE,
        mechanism=(
            "Assurance methods are ordered weakest first; a key control must sit at "
            "or above controls.key_control_minimum_assurance"
        ),
        violation="Link rejected; strengthen the assurance method or unmark the key control",
        spec_ref="codified-rules section 24.2",
        holds=_key_control_assurance,
    ),
)
