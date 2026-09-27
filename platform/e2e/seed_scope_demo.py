"""Scope-aware testing demo: one control, two frameworks, three risks.

Layered on the standard demo seed, for the recorded user journeys in this
directory. Run it inside the API container against a freshly seeded database:

    docker compose cp e2e/seed_scope_demo.py api:/tmp/seed_scope_demo.py
    docker compose exec -e PYTHONPATH=/srv api python /tmp/seed_scope_demo.py

The shape is the scenario codified-rules section 25 exists for. CTL-006, a
multi-factor authentication control, runs on five assets. PCI DSS scopes three
of them and is configured all_in_scope; ISO 27001 scopes all five and is
any_in_scope. Checkout Web sits inside both. So one operating failure on
Checkout Web costs PCI its requirements and ISO nothing, and of the three risks
the control reduces, only the one whose scope includes Checkout Web moves.

Licensing. ISO 27001 and PCI DSS text is not redistributable (AINV-6). The
requirement identifiers below are references; every title is this demo's own
paraphrase, prefixed "Demo label", and none of it is the standards' wording.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from sqlalchemy import select

# Every model, so the mapper can resolve relationships declared by name.
import app.modules.compliance.models  # noqa: F401
import app.modules.control.models  # noqa: F401
import app.modules.identity.models  # noqa: F401
import app.modules.policy.models  # noqa: F401
import app.modules.risk.models  # noqa: F401
import app.modules.threat.models  # noqa: F401
import app.modules.treatment.models  # noqa: F401
from app.core.db import SessionLocal
from app.core.model_base import utcnow
from app.modules.compliance.models import (
    ComplianceFramework,
    ComplianceRequirement,
    ControlRequirementLink,
    RequirementAssessment,
)
from app.modules.control.models import (
    AttackSurface,
    ControlActivity,
    ControlDeployment,
    ControlObjective,
)
from app.modules.identity.models import User
from app.modules.risk.models import Risk, RiskAssetLink, RiskControlLink, RiskPhaseHistory

TODAY = date.today()


def next_reference(session, model, prefix: str, taken: set[str] = frozenset()) -> str:
    """The next free PREFIX-NNN, read from what the standard seed left."""
    used = {r for (r,) in session.execute(select(model.reference))} | set(taken)
    n = 1
    while prefix + "-" + str(n).zfill(3) in used:
        n += 1
    return prefix + "-" + str(n).zfill(3)
ISO, PCI = "ISO-27001-2022", "PCI-DSS-4.0"


def main() -> int:
    s = SessionLocal()
    if s.execute(select(ControlObjective).where(ControlObjective.reference == "CTL-006")).first():
        print("already seeded; reset first: docker compose down -v && docker compose up -d")
        return 2

    users = {u.email: u for u in s.execute(select(User)).scalars()}
    control_owner = users["control@example.com"]
    grc = users["grc@example.com"]
    analyst = users["analyst@example.com"]
    risk_owner = users["owner@example.com"]
    sys_owner = users["sysowner@example.com"]
    ciso = users["ciso@example.com"]

    # -- frameworks: adopt, and import identifiers with demo labels ----------
    frameworks = {
        f.framework_id: f
        for f in s.execute(select(ComplianceFramework)).scalars()
        if f.framework_id in (ISO, PCI)
    }
    for f in frameworks.values():
        f.adopted = True
        f.adopted_at = utcnow()

    def requirement(framework_id, ref, title, order):
        r = ComplianceRequirement(
            framework_id=frameworks[framework_id].id,
            ref=ref,
            title=title,
            category="Demo requirements",
            sort_order=order,
        )
        s.add(r)
        s.flush()
        return r

    iso_a517 = requirement(ISO, "A.5.17", "Demo label: authentication secrets are issued and protected", 1)
    iso_a85 = requirement(ISO, "A.8.5", "Demo label: access to systems requires strong authentication", 2)
    iso_a815 = requirement(ISO, "A.8.15", "Demo label: activity is logged and the logs are reviewed", 3)
    iso_a519 = requirement(ISO, "A.5.19", "Demo label: supplier relationships carry security terms", 4)
    pci_842 = requirement(PCI, "8.4.2", "Demo label: multi-factor authentication for all access into the card environment", 1)
    pci_843 = requirement(PCI, "8.4.3", "Demo label: multi-factor authentication for remote access to the card environment", 2)
    pci_1021 = requirement(PCI, "10.2.1", "Demo label: audit logs capture user activity in the card environment", 3)

    # -- assets and their compliance scope ---------------------------------
    assets = {a.name: a for a in s.execute(select(AttackSurface)).scalars()}
    payments = assets["Payments API"]
    corp_idp = assets["Corporate Identity Provider"]

    def asset(name, tier, description, owner):
        a = AttackSurface(name=name, tier=tier, description=description, system_owner_id=owner)
        s.add(a)
        s.flush()
        return a

    vault = asset("Card Vault", "Tier_1", "Tokenisation service holding primary account numbers.", sys_owner.id)
    checkout = asset("Checkout Web", "Tier_1", "Customer checkout front end that captures card details.", sys_owner.id)
    hr = asset("HR Portal", "Tier_3", "Workforce self-service for leave, payroll and expenses.", None)

    def scope(a, *framework_ids):
        a.compliance_scopes = sorted(set(a.compliance_scopes or []) | set(framework_ids))

    for a in (payments, vault, checkout):
        scope(a, PCI, ISO)
    for a in (corp_idp, hr):
        scope(a, ISO)

    # -- CTL-006 on five assets ------------------------------------------
    ctl = ControlObjective(
        reference="CTL-006",
        title="Multi-factor authentication for all interactive access",
        description="Every interactive login to a production or workforce system presents a second factor.",
        family="Identity_Management",
        control_type="Preventive",
        lifecycle_state="Operating",
        control_owner_id=control_owner.id,
        automation_level="Automated",
        implementation_type="Technical",
        operating_frequency="Continuous",
        assurance_method="Re_Performance",
        objective_statement=(
            "No interactive session is established on an in-scope system without a "
            "second authentication factor."
        ),
    )
    s.add(ctl)
    s.flush()
    act = ControlActivity(
        reference=next_reference(s, ControlActivity, "ACT"),
        objective_id=ctl.id,
        title="Enforce a second factor through the identity provider",
        description="Conditional access requires a second factor for every interactive sign-in.",
        lifecycle_state="Active",
        control_operator_id=control_owner.id,
        automation_level="Automated",
        operating_frequency="Continuous",
        procedure_ref="RUN-IAM-021 Multi-factor enrolment and enforcement",
        tooling="Identity provider conditional access",
        evidence_type="Configuration_Export",
    )
    s.add(act)
    s.flush()
    allocated: set[str] = set()
    for a in (payments, vault, checkout, corp_idp, hr):
        reference = next_reference(s, ControlDeployment, "DEP", allocated)
        allocated.add(reference)
        s.add(
            ControlDeployment(
                reference=reference,
                activity_id=act.id,
                attack_surface_id=a.id,
                deployment_status="Active",
                ce_rating="CE-High",
                ce_evidence_ref="Conditional access export and sign-in log sample, " + a.name + ".",
                ce_assessed_by=control_owner.id,
                ce_assessed_at=TODAY - timedelta(days=20),
                test_frequency="Quarterly",
                last_test_result="Pass",
                last_tested_date=TODAY - timedelta(days=20),
                next_test_due=TODAY + timedelta(days=70),
            )
        )
    s.flush()

    # -- coverage assertions and positions --------------------------------
    ctl4 = s.execute(select(ControlObjective).where(ControlObjective.reference == "CTL-004")).scalar_one()

    def cover(req, objective, rationale):
        s.add(
            ControlRequirementLink(
                requirement_id=req.id,
                objective_id=objective.id,
                coverage_level="Full",
                rationale=rationale,
                asserted_by=grc.id,
            )
        )
        s.add(
            RequirementAssessment(
                requirement_id=req.id,
                lifecycle_state="Covered",
                owner_id=grc.id,
                assessed_by=grc.id,
                assessed_at=utcnow(),
            )
        )

    def gap(req, reason):
        s.add(
            RequirementAssessment(
                requirement_id=req.id,
                lifecycle_state="Gap",
                gap_reason=reason,
                owner_id=grc.id,
                assessed_by=grc.id,
                assessed_at=utcnow(),
            )
        )

    cover(iso_a517, ctl, "Second factor enforced at the identity provider for every workforce login.")
    cover(iso_a85, ctl, "Conditional access requires a second factor on every in-scope system.")
    cover(iso_a815, ctl4, "Privileged session capture with a documented review.")
    gap(iso_a519, "No control mapped yet. Supplier terms are held by procurement, not evidenced here.")
    cover(pci_842, ctl, "Second factor enforced on every system inside the card environment.")
    cover(pci_843, ctl, "Remote access to the card environment goes through the same conditional access.")
    gap(pci_1021, "Log capture on Checkout Web is not yet evidenced.")

    # -- risks with different scopes --------------------------------------
    def risk(reference, title, tier, impact, likelihood, rating, res_likelihood, res_rating, owner, scope_assets, **text):
        r = Risk(
            reference=reference,
            title=title,
            lifecycle_state="Monitoring",
            phase=7,
            intake_source="Assessment",
            identified_by="Annual risk assessment",
            tier=tier,
            pre_true_risk_confirmed=True,
            impact=impact,
            likelihood=likelihood,
            inherent_risk_score=impact * likelihood,
            inherent_rating=rating,
            inherent_locked=True,
            treatment_strategy="Mitigate",
            readout_confirmed=True,
            readout_conducted_at=utcnow(),
            gate_mitigations_implemented=True,
            gate_evidence_provided=True,
            gate_effectiveness_confirmed=True,
            gate_governance_approved=True,
            gate_drift_tracked=True,
            evidence_ref="Conditional access export and quarterly sign-in log review.",
            residual_score_locked=False,
            residual_impact=impact,
            residual_likelihood=res_likelihood,
            residual_risk_score=impact * res_likelihood,
            residual_rating=res_rating,
            residual_impact_rationale="Impact is unchanged. Controls reduce likelihood, not consequence (IMP-4).",
            residual_likelihood_rationale=(
                "CTL-006 holds CE-High on every asset in scope, which permits a reduction of "
                "two levels."
            ),
            next_review_date=TODAY + timedelta(days=60),
            sla_status="On_Track",
            risk_owner_id=owner.id,
            risk_stakeholder_id=ciso.id,
            risk_analyst_id=analyst.id,
            created_by=analyst.id,
            **text,
        )
        s.add(r)
        s.flush()
        for a in scope_assets:
            s.add(RiskAssetLink(risk_id=r.id, attack_surface_id=a.id, linked_by=analyst.id))
        s.add(RiskControlLink(risk_id=r.id, objective_id=ctl.id, ce_at_assessment="CE-High", linked_by=analyst.id))
        for src, dst, phase in (
            (None, "Intake", 1), ("Intake", "Preconditions", 2), ("Preconditions", "Scoring", 3),
            ("Scoring", "Treatment", 4), ("Treatment", "Readout", 5),
            ("Readout", "Evidence_Residual", 6), ("Evidence_Residual", "Monitoring", 7),
        ):
            s.add(
                RiskPhaseHistory(
                    risk_id=r.id, from_state=src, to_state=dst,
                    from_phase=phase - 1 if src else None, to_phase=phase,
                    gate="SEEDED", gate_evaluation={"seeded": True}, changed_by=analyst.id,
                )
            )
        return r

    risk(
        "RISK-006",
        "Card data exposed through a hijacked checkout session",
        "Tier_1", 4, 4, "High", 2, "Moderate-Low", risk_owner, (checkout, vault),
        tier_rationale="Card data exposure is an enterprise-level regulatory and financial event.",
        cause="checkout and vault sessions can be established with a stolen password",
        threat_event="an attacker replays phished credentials against checkout administration",
        vulnerability="a password alone would grant a session if the second factor lapsed",
        impact_statement="exposure of primary account numbers and a reportable card data breach",
        impact_justification="Tier 1 scope. A card data breach carries fines, reissue costs and brand damage.",
        likelihood_justification="Credential phishing against retail checkout staff is routine across the sector.",
    )
    risk(
        "RISK-007",
        "Workforce account takeover through phished credentials",
        "Tier_2", 4, 3, "Moderate", 1, "Low", sys_owner, (corp_idp, hr),
        tier_rationale="Workforce identity underpins every internal system but not the card environment.",
        cause="workforce sign-in is exposed to the internet",
        threat_event="a phished employee password is used to sign in",
        vulnerability="a password alone would grant access if the second factor lapsed",
        impact_statement="unauthorised access to payroll data and internal systems",
        impact_justification="Tier 2 scope. Material internal exposure, contained away from card data.",
        likelihood_justification="Workforce phishing succeeds against some fraction of staff every year.",
    )
    risk1 = s.execute(select(Risk).where(Risk.reference == "RISK-001")).scalar_one()
    s.add(RiskControlLink(risk_id=risk1.id, objective_id=ctl.id, ce_at_assessment="CE-High", linked_by=analyst.id))

    s.commit()
    print(
        "scope demo seeded: CTL-006 on 5 assets; PCI (all_in_scope) scopes Payments API, "
        "Card Vault, Checkout Web; ISO (any_in_scope) scopes those plus Corporate Identity "
        "Provider and HR Portal; RISK-006, RISK-007 and RISK-001 rely on CTL-006."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
