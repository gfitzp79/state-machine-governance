"""Demo dataset.

Seeded on first boot when SEED_DEMO_DATA is enabled. The data is arranged so the
interesting behaviour is reachable immediately:

  RISK-001  sits in Monitoring with a validated residual, reduced by CTL-001.
            CTL-001 also mitigates THR-001 in threat model TM-001, which is Active
            with both sign-offs. Fail a test on CTL-001's deployment and watch the
            residual re-lock, the scenario re-open and the threat model lose its
            sign-off in one transaction.

  RISK-002  sits at the residual gate with three of five conditions met, so the
            gate panel shows exactly what is missing.

  RISK-003  is Critical and in Treatment, so attempting to accept it is refused.

  POL-002   is Active with one linked control, so removing that link is refused.

Every password is 'changeme123'.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.model_base import utcnow
from app.core.security import hash_password
from app.modules.control.models import (
    AttackSurface,
    ControlActivity,
    ControlDeployment,
    ControlObjective,
    ControlTest,
)
from app.modules.identity.models import User, UserRole
from app.modules.policy.models import Policy, PolicyControlLink, PolicyException, PolicyVersion
from app.modules.risk.models import (
    Risk,
    RiskControlLink,
    RiskPhaseHistory,
    RiskTreatmentLink,
)
from app.modules.threat.models import (
    ThreatComponent,
    ThreatMitigationLink,
    ThreatModel,
    ThreatScenario,
    ThreatScenarioComment,
    ThreatScenarioEvidence,
    ThreatScenarioRiskLink,
)
from app.modules.treatment.models import Treatment, TreatmentApproval, TreatmentCheckin

PASSWORD = "changeme123"
TODAY = date.today()


def _user(session, email, name, title, seniority, roles):
    user = User(
        email=email,
        full_name=name,
        job_title=title,
        seniority=seniority,
        password_hash=hash_password(PASSWORD),
    )
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRole(user_id=user.id, role=role))
    return user


def _history(session, risk, pairs):
    """Backfill the phase trail so a seeded risk looks like it was walked here."""
    phases = {
        "Intake": 1,
        "Preconditions": 2,
        "Scoring": 3,
        "Treatment": 4,
        "Readout": 5,
        "Evidence_Residual": 6,
        "Monitoring": 7,
    }
    for src, dst, gate in pairs:
        session.add(
            RiskPhaseHistory(
                risk_id=risk.id,
                from_state=src,
                to_state=dst,
                from_phase=phases.get(src) if src else None,
                to_phase=phases.get(dst, 1),
                gate=gate,
                gate_evaluation={"seeded": True},
                changed_by=risk.risk_analyst_id,
            )
        )


def seed(session: Session) -> None:
    # -- people ------------------------------------------------------------
    admin = _user(
        session, "admin@example.com", "Ada Okafor", "Platform Administrator", "Director",
        ["Admin", "GRC_Engineer"],
    )
    ciso = _user(
        session, "ciso@example.com", "Marcus Bell", "Chief Information Security Officer",
        "C-level", ["CISO", "Risk_Stakeholder"],
    )
    analyst = _user(
        session, "analyst@example.com", "Priya Raman", "Senior Risk Analyst", "Manager",
        ["Risk_Analyst"],
    )
    engineer = _user(
        session, "grc@example.com", "Tomas Lindqvist", "GRC Engineer", "Manager",
        ["GRC_Engineer"],
    )
    risk_owner = _user(
        session, "owner@example.com", "Elena Vasquez", "VP Engineering", "VP",
        ["Risk_Owner"],
    )
    control_owner = _user(
        session, "control@example.com", "Jonah Weiss", "Head of Platform Security", "Director",
        ["Control_Owner", "Control_Operator"],
    )
    delivery = _user(
        session, "delivery@example.com", "Sam Okonkwo", "Engineering Manager", "Manager",
        ["Risk_Treatment_Owner"],
    )
    appsec = _user(
        session, "appsec@example.com", "Ines Ferreira", "Application Security Lead", "Manager",
        ["AppSec_Lead", "Security_SME"],
    )
    system_owner = _user(
        session, "sysowner@example.com", "Dmitri Sokolov", "Director of Payments Engineering",
        "Director", ["System_Owner", "Risk_Owner"],
    )
    policy_owner = _user(
        session, "policy@example.com", "Aoife Byrne", "Head of Governance", "Director",
        ["Policy_Owner"],
    )
    session.flush()

    # -- assets ------------------------------------------------------------
    payments = AttackSurface(
        name="Payments API",
        tier="Tier_1",
        description="Customer-facing payment authorisation and settlement service.",
        system_owner_id=system_owner.id,
    )
    warehouse = AttackSurface(
        name="Customer Data Warehouse",
        tier="Tier_1",
        description="Analytical store holding customer PII and transaction history.",
        system_owner_id=system_owner.id,
    )
    corp_idp = AttackSurface(
        name="Corporate Identity Provider",
        tier="Tier_2",
        description="Workforce SSO and directory services.",
        system_owner_id=control_owner.id,
    )
    build = AttackSurface(
        name="CI/CD Pipeline",
        tier="Tier_2",
        description="Build, test and deployment automation.",
        system_owner_id=control_owner.id,
    )
    session.add_all([payments, warehouse, corp_idp, build])
    session.flush()

    # -- controls ----------------------------------------------------------
    def control(ref, title, family, ctype, state, description):
        obj = ControlObjective(
            reference=ref,
            title=title,
            description=description,
            family=family,
            control_type=ctype,
            lifecycle_state=state,
            control_owner_id=control_owner.id,
        )
        session.add(obj)
        session.flush()
        return obj

    def activity(ref, obj, title, state, description):
        act = ControlActivity(
            reference=ref,
            objective_id=obj.id,
            title=title,
            description=description,
            lifecycle_state=state,
            control_operator_id=control_owner.id,
        )
        session.add(act)
        session.flush()
        return act

    def deployment(ref, act, asset, status, ce, evidence, assessed, freq="Quarterly"):
        dep = ControlDeployment(
            reference=ref,
            activity_id=act.id,
            attack_surface_id=asset.id,
            deployment_status=status,
            ce_rating=ce,
            ce_evidence_ref=evidence,
            ce_assessed_by=control_owner.id,
            ce_assessed_at=assessed,
            test_frequency=freq,
            last_test_result="Pass" if ce in ("CE-High", "CE-Medium") else "Not_Tested",
            last_tested_date=assessed,
            next_test_due=(assessed + timedelta(days=90)) if assessed else None,
        )
        session.add(dep)
        session.flush()
        return dep

    ctl1 = control(
        "CTL-001",
        "Multi-factor authentication on privileged access",
        "Identity_Management",
        "Preventive",
        "Operating",
        "All privileged access paths require phishing-resistant MFA.",
    )
    act1 = activity(
        "ACT-001", ctl1, "Enforce WebAuthn on admin roles", "Active",
        "Conditional access policy requiring hardware-backed authenticators.",
    )
    dep1 = deployment(
        "DEP-001", act1, corp_idp, "Active", "CE-High",
        "IdP conditional access export 2026-08-14; 100% enrolment dashboard.",
        TODAY - timedelta(days=30),
    )
    dep2 = deployment(
        "DEP-002", act1, payments, "Active", "CE-Medium",
        "Break-glass accounts documented; 3 service accounts still on TOTP.",
        TODAY - timedelta(days=45),
    )

    ctl2 = control(
        "CTL-002",
        "Encryption of customer data at rest",
        "Data_Protection",
        "Preventive",
        "Operating",
        "Customer PII encrypted at rest with managed keys and annual rotation.",
    )
    act2 = activity(
        "ACT-002", ctl2, "Enable KMS envelope encryption on data stores", "Active",
        "All warehouse volumes and snapshots encrypted with customer-managed keys.",
    )
    dep3 = deployment(
        "DEP-003", act2, warehouse, "Active", "CE-High",
        "KMS key policy export and encryption-at-rest audit report 2026-07-02.",
        TODAY - timedelta(days=60),
    )

    ctl3 = control(
        "CTL-003",
        "Secure software development lifecycle gates",
        "Application_Security",
        "Detective",
        "Implementation",
        "SAST, dependency scanning and peer review enforced before merge.",
    )
    act3 = activity(
        "ACT-003", ctl3, "Block merge on critical SAST findings", "Active",
        "Pipeline gate failing the build on critical severity findings.",
    )
    deployment(
        "DEP-004", act3, build, "Planned", "CE-Unvalidated", None, None,
    )

    ctl4 = control(
        "CTL-004",
        "Privileged session logging and review",
        "Logging_Monitoring",
        "Detective",
        "Operating",
        "All privileged sessions recorded and reviewed on a monthly cadence.",
    )
    act4 = activity(
        "ACT-004", ctl4, "Session recording with monthly review", "Active",
        "Bastion session capture with documented monthly review by the platform team.",
    )
    dep5 = deployment(
        "DEP-005", act4, payments, "Degraded", "CE-Low",
        "Session capture operating; review cadence slipped to quarterly in Q2.",
        TODAY - timedelta(days=20),
        "Monthly",
    )

    # An expired-evidence deployment, so CINV-10 has something to catch.
    ctl5 = control(
        "CTL-005",
        "Third-party access review",
        "Third_Party_Risk",
        "Detective",
        "Operating",
        "Quarterly recertification of all third-party access to production.",
    )
    act5 = activity(
        "ACT-005", ctl5, "Quarterly recertification campaign", "Active",
        "Access recertification run through the IGA platform each quarter.",
    )
    deployment(
        "DEP-006", act5, corp_idp, "Active", "CE-Medium",
        "Q3 2025 recertification campaign completion report.",
        TODAY - timedelta(days=420),
        "Quarterly",
    )

    session.add(
        ControlTest(
            deployment_id=dep1.id,
            result="Pass",
            evidence_ref="Quarterly control test Q3 2026; 0 exceptions.",
            notes="All privileged roles verified as WebAuthn-enforced.",
            tested_by=control_owner.id,
            sequence=1,
        )
    )
    session.add(
        ControlTest(
            deployment_id=dep5.id,
            result="Partial",
            evidence_ref="Q2 review log shows 2 of 3 months reviewed.",
            notes="Review cadence slipped; capture itself is operating correctly.",
            tested_by=control_owner.id,
            sequence=1,
        )
    )
    session.flush()

    # -- policies ----------------------------------------------------------
    pol1 = Policy(
        reference="POL-001",
        title="Information Security Policy",
        policy_type="Information_Security",
        version="3.1",
        lifecycle_state="Active",
        review_cycle="Annual",
        effective_date=TODAY - timedelta(days=200),
        next_review_date=TODAY + timedelta(days=165),
        scope="All employees, contractors and systems processing company or customer data.",
        purpose="Establish the baseline security requirements for the organisation.",
        body=(
            "All systems processing customer data must enforce multi-factor authentication "
            "on privileged access paths, encrypt data at rest and in transit, and maintain "
            "auditable records of privileged activity."
        ),
        compliance_mappings=["ISO27001", "SOC2", "DORA"],
        policy_owner_id=policy_owner.id,
        approved_by=ciso.id,
        approved_at=utcnow(),
        created_by=policy_owner.id,
    )
    pol2 = Policy(
        reference="POL-002",
        title="Data Protection Policy",
        policy_type="Data_Protection",
        version="2.0",
        lifecycle_state="Active",
        review_cycle="Annual",
        effective_date=TODAY - timedelta(days=120),
        next_review_date=TODAY + timedelta(days=245),
        scope="All personal data processed by the organisation.",
        purpose="Define how personal data is classified, protected, retained and erased.",
        body=(
            "Customer personal data must be encrypted at rest using customer-managed keys. "
            "Access is granted on a least-privilege basis and recertified quarterly."
        ),
        compliance_mappings=["GDPR", "ISO27001"],
        policy_owner_id=policy_owner.id,
        approved_by=ciso.id,
        approved_at=utcnow(),
        created_by=policy_owner.id,
    )
    pol3 = Policy(
        reference="POL-003",
        title="AI Governance Policy",
        policy_type="AI_Governance",
        version="0.4",
        lifecycle_state="Draft",
        review_cycle="Annual",
        scope="All internally built and procured AI systems.",
        purpose=(
            "Govern the lifecycle of AI systems from ideation through decommissioning, "
            "including prompt telemetry requirements and named ownership."
        ),
        body=(
            "No AI tool may advance to Build without a named owner. No AI tool may enter "
            "Production without prompt telemetry confirmed in the SIEM."
        ),
        compliance_mappings=["EU-AI-Act"],
        policy_owner_id=policy_owner.id,
        created_by=policy_owner.id,
    )
    session.add_all([pol1, pol2, pol3])
    session.flush()

    for policy, objectives in ((pol1, [ctl1, ctl4]), (pol2, [ctl2, ctl5])):
        for obj in objectives:
            session.add(
                PolicyControlLink(
                    policy_id=policy.id, objective_id=obj.id, linked_by=policy_owner.id
                )
            )
    for policy in (pol1, pol2, pol3):
        session.add(
            PolicyVersion(
                policy_id=policy.id,
                version=policy.version,
                body=policy.body,
                change_summary="Seeded baseline version.",
                lifecycle_state_at_capture=policy.lifecycle_state,
                edited_by=policy_owner.id,
            )
        )

    session.add(
        PolicyException(
            reference="EXC-001",
            policy_id=pol1.id,
            title="TOTP on three legacy payment service accounts",
            business_justification=(
                "Three service accounts authenticate to a vendor gateway that does not "
                "support WebAuthn. Vendor migration is scheduled for Q1."
            ),
            risk_statement=(
                "Phishing-resistant MFA is not enforced on three privileged service "
                "accounts with production payment access."
            ),
            compensating_controls=(
                "IP allow-listing on the vendor gateway, 30-day credential rotation, and "
                "alerting on any interactive use of these accounts."
            ),
            lifecycle_state="Approved",
            expiry_date=TODAY + timedelta(days=21),
            requested_by=control_owner.id,
            approved_by=ciso.id,
        )
    )
    session.add(
        PolicyException(
            reference="EXC-002",
            policy_id=pol2.id,
            title="Unencrypted analytics replica in the reporting sandbox",
            business_justification=(
                "The reporting sandbox predates the customer-managed key rollout and is "
                "scheduled for decommissioning."
            ),
            risk_statement="A replica containing customer PII is not encrypted at rest.",
            compensating_controls=None,
            lifecycle_state="Requested",
            expiry_date=TODAY + timedelta(days=90),
            requested_by=system_owner.id,
        )
    )
    session.flush()

    # -- treatments --------------------------------------------------------
    trt1 = Treatment(
        reference="TRT-001",
        title="Migrate remaining service accounts to workload identity federation",
        description=(
            "Replace the three static TOTP service accounts with short-lived federated "
            "credentials issued per workload."
        ),
        treatment_type="Mitigate",
        lifecycle_state="Complete",
        grc_eng_validated=True,
        grc_eng_validated_by=engineer.id,
        grc_eng_validation_notes=(
            "Federation is supported by the gateway as of v4.2. Delivery is feasible "
            "within the stated horizon."
        ),
        owner_committed=True,
        owner_committed_at=utcnow(),
        treatment_owner_id=delivery.id,
        target_date=TODAY - timedelta(days=15),
        completed_at=utcnow(),
        loe="M",
        expected_impact_delta=0,
        expected_likelihood_delta=-2,
        check_in_frequency="Fortnightly",
        evidence_ref=(
            "Federation rollout runbook, IdP audit log showing zero static credential "
            "use since 2026-08-20, and the post-implementation review."
        ),
        created_by=engineer.id,
    )
    trt2 = Treatment(
        reference="TRT-002",
        title="Restore monthly privileged session review cadence",
        description=(
            "Automate the monthly review assignment and evidence capture so the cadence "
            "does not depend on manual scheduling."
        ),
        treatment_type="Mitigate",
        lifecycle_state="In_Progress",
        grc_eng_validated=True,
        grc_eng_validated_by=engineer.id,
        grc_eng_validation_notes="Workflow automation available in the existing IGA platform.",
        owner_committed=True,
        owner_committed_at=utcnow(),
        treatment_owner_id=delivery.id,
        target_date=TODAY + timedelta(days=45),
        loe="S",
        expected_impact_delta=0,
        expected_likelihood_delta=-1,
        check_in_frequency="Monthly",
        created_by=engineer.id,
    )
    trt3 = Treatment(
        reference="TRT-003",
        title="Deploy SAST merge gate across all production repositories",
        description="Enforce the pipeline gate on every repository deploying to production.",
        treatment_type="Mitigate",
        lifecycle_state="Proposed",
        treatment_owner_id=delivery.id,
        target_date=TODAY + timedelta(days=90),
        loe="L",
        expected_impact_delta=0,
        expected_likelihood_delta=-2,
        check_in_frequency="Monthly",
        created_by=engineer.id,
    )
    session.add_all([trt1, trt2, trt3])
    session.flush()

    session.add(
        TreatmentApproval(
            treatment_id=trt1.id,
            approval_type="treatment_approval",
            requested_by=engineer.id,
            assigned_to=risk_owner.id,
            decision="Approved",
            decision_by=risk_owner.id,
            decision_at=utcnow(),
            decision_notes="Approved at the September governance forum.",
        )
    )
    session.add(
        TreatmentApproval(
            treatment_id=trt2.id,
            approval_type="treatment_approval",
            requested_by=engineer.id,
            assigned_to=risk_owner.id,
            decision="Approved",
            decision_by=risk_owner.id,
            decision_at=utcnow(),
            decision_notes="Approved; low effort, clear benefit.",
        )
    )
    for treatment, notes in (
        (trt1, "Federation configured in staging; production cutover scheduled."),
        (trt1, "Cutover complete. Static credentials revoked and evidence captured."),
        (trt2, "Automation workflow drafted; pending IGA change window."),
    ):
        session.add(
            TreatmentCheckin(
                treatment_id=treatment.id,
                status="On_Track",
                notes=notes,
                submitted_by=delivery.id,
            )
        )
    session.flush()

    # -- risks -------------------------------------------------------------
    risk1 = Risk(
        reference="RISK-001",
        title="Privileged access to payment systems without phishing-resistant MFA",
        lifecycle_state="Monitoring",
        phase=7,
        cause="legacy service accounts authenticate with shared static credentials",
        threat_event="a credential-phishing campaign targeting platform engineers succeeds",
        vulnerability="privileged paths to the Payments API accept non-phishing-resistant factors",
        impact_statement=(
            "unauthorised payment authorisation, regulatory notification obligations under "
            "DORA, and material customer harm"
        ),
        intake_source="Assessment",
        identified_by="Annual control assessment",
        tier="Tier_1",
        tier_rationale="Payment authorisation is an enterprise-critical business process.",
        pre_true_risk_confirmed=True,
        pre_tier_assigned=True,
        pre_stakeholders_identified=True,
        pre_ce_assessed=True,
        impact=5,
        likelihood=4,
        inherent_risk_score=20,
        inherent_rating="Critical",
        inherent_locked=True,
        impact_justification=(
            "Tier 1 scope. Unauthorised payment authorisation carries direct financial loss, "
            "regulatory sanction and reputational damage."
        ),
        likelihood_justification=(
            "Credential phishing against engineering staff is observed multiple times per "
            "year across the sector, with two attempts against this organisation in 12 months."
        ),
        treatment_strategy="Mitigate",
        control_framework_mapping="ISO 27001 A.5.17, A.8.5; NIST 800-53 IA-2(1)",
        readout_confirmed=True,
        readout_conducted_at=utcnow(),
        gate_mitigations_implemented=True,
        gate_evidence_provided=True,
        gate_effectiveness_confirmed=True,
        gate_governance_approved=True,
        gate_drift_tracked=True,
        evidence_ref=(
            "IdP conditional access export, federation rollout runbook, and the "
            "post-implementation review signed off by the Risk Analyst."
        ),
        residual_score_locked=False,
        residual_impact=5,
        residual_likelihood=3,
        residual_risk_score=15,
        residual_rating="High",
        residual_impact_rationale=(
            "Impact is unchanged. Controls reduce likelihood, not consequence (IMP-4)."
        ),
        residual_likelihood_rationale=(
            "Worst-case CE across the linked deployments is CE-Medium (DEP-002 carries "
            "documented gaps), which permits a reduction of one level and no more. The "
            "federation rollout would justify a second level once DEP-002 reaches CE-High."
        ),
        next_review_date=TODAY + timedelta(days=45),
        risk_owner_id=risk_owner.id,
        risk_stakeholder_id=ciso.id,
        risk_analyst_id=analyst.id,
        created_by=analyst.id,
    )

    risk2 = Risk(
        reference="RISK-002",
        title="Privileged activity on payment systems is not reviewed on the required cadence",
        lifecycle_state="Evidence_Residual",
        phase=6,
        cause="the monthly privileged session review depends on manual scheduling",
        threat_event="malicious or erroneous privileged activity goes undetected",
        vulnerability="review cadence slipped to quarterly without a compensating detection",
        impact_statement=(
            "delayed detection of unauthorised change to payment configuration, extending "
            "the window of customer and regulatory exposure"
        ),
        intake_source="Control_Test_Failure",
        identified_by="Q2 control test",
        tier="Tier_2",
        tier_rationale="Scoped to the payment operations process rather than the enterprise.",
        pre_true_risk_confirmed=True,
        pre_tier_assigned=True,
        pre_stakeholders_identified=True,
        pre_ce_assessed=True,
        impact=4,
        likelihood=3,
        inherent_risk_score=12,
        inherent_rating="Moderate",
        inherent_locked=True,
        impact_justification=(
            "Tier 2 scope. Delayed detection materially extends exposure but does not by "
            "itself cause the loss event."
        ),
        likelihood_justification=(
            "Privileged misuse is plausible within one to three years given the number of "
            "standing privileged accounts."
        ),
        treatment_strategy="Mitigate",
        control_framework_mapping="ISO 27001 A.8.15; NIST 800-53 AU-6",
        readout_confirmed=True,
        readout_conducted_at=utcnow(),
        # Three of five conditions met, so the gate panel has something to show.
        gate_mitigations_implemented=False,
        gate_evidence_provided=False,
        gate_effectiveness_confirmed=True,
        gate_governance_approved=True,
        gate_drift_tracked=True,
        residual_score_locked=True,
        risk_owner_id=system_owner.id,
        risk_stakeholder_id=ciso.id,
        risk_analyst_id=analyst.id,
        created_by=analyst.id,
    )

    risk3 = Risk(
        reference="RISK-003",
        title="Unencrypted customer PII replica in the reporting sandbox",
        lifecycle_state="Treatment",
        phase=4,
        cause="the reporting sandbox predates the customer-managed key rollout",
        threat_event="an attacker or insider extracts the analytics replica",
        vulnerability="the replica is stored without encryption at rest and outside key policy",
        impact_statement=(
            "disclosure of customer personal data affecting more than 100,000 records, "
            "triggering GDPR notification and supervisory authority engagement"
        ),
        intake_source="Audit_Finding",
        identified_by="Internal audit, data protection review",
        tier="Tier_1",
        tier_rationale="Customer PII disclosure at this volume is an enterprise-level event.",
        pre_true_risk_confirmed=True,
        pre_tier_assigned=True,
        pre_stakeholders_identified=True,
        pre_ce_assessed=True,
        impact=5,
        likelihood=4,
        inherent_risk_score=20,
        inherent_rating="Critical",
        inherent_locked=True,
        impact_justification=(
            "Tier 1 scope. A breach above 100,000 records is a material regulatory and "
            "reputational event."
        ),
        likelihood_justification=(
            "The replica is reachable from the analytics network segment with broad read "
            "access; exposure is continuous."
        ),
        residual_score_locked=True,
        risk_owner_id=system_owner.id,
        risk_stakeholder_id=ciso.id,
        risk_analyst_id=analyst.id,
        created_by=analyst.id,
    )

    risk4 = Risk(
        reference="RISK-004",
        title="Production deploys bypass security gates on legacy repositories",
        lifecycle_state="Scoring",
        phase=3,
        cause="the SAST merge gate is deployed on only part of the repository estate",
        threat_event="a known-vulnerable dependency reaches production",
        vulnerability="legacy repositories deploy without dependency or static analysis gates",
        impact_statement=(
            "exploitable vulnerability in a customer-facing service, with remediation "
            "under incident conditions"
        ),
        intake_source="Self_Identified",
        identified_by="Platform security review",
        tier="Tier_2",
        tier_rationale="Scoped to the software delivery process.",
        pre_true_risk_confirmed=True,
        pre_tier_assigned=True,
        pre_stakeholders_identified=True,
        pre_ce_assessed=True,
        residual_score_locked=True,
        risk_owner_id=risk_owner.id,
        risk_stakeholder_id=ciso.id,
        risk_analyst_id=analyst.id,
        created_by=analyst.id,
    )

    risk5 = Risk(
        reference="RISK-005",
        title="Third-party access recertification has lapsed beyond its cadence",
        lifecycle_state="Intake",
        phase=1,
        cause="the quarterly recertification campaign was not run in the last two quarters",
        threat_event="a departed vendor employee retains production access",
        vulnerability="access recertification evidence is more than twelve months old",
        impact_statement=(
            "unauthorised third-party access to production systems and the customer data "
            "they process"
        ),
        intake_source="Assessment",
        identified_by="Control effectiveness review",
        residual_score_locked=True,
        risk_analyst_id=analyst.id,
        created_by=analyst.id,
    )

    session.add_all([risk1, risk2, risk3, risk4, risk5])
    session.flush()

    _history(
        session,
        risk1,
        [
            (None, "Intake", "CREATE"),
            ("Intake", "Preconditions", "GATE_INTAKE_COMPLETE"),
            ("Preconditions", "Scoring", "GATE_PRECONDITIONS_MET"),
            ("Scoring", "Treatment", "GATE_SCORING_COMPLETE"),
            ("Treatment", "Readout", "GATE_TREATMENT_ALIGNED"),
            ("Readout", "Evidence_Residual", "GATE_READOUT_COMPLETE"),
            ("Evidence_Residual", "Monitoring", "GATE_RESIDUAL_VALIDATED"),
        ],
    )
    _history(
        session,
        risk2,
        [
            (None, "Intake", "CREATE"),
            ("Intake", "Preconditions", "GATE_INTAKE_COMPLETE"),
            ("Preconditions", "Scoring", "GATE_PRECONDITIONS_MET"),
            ("Scoring", "Treatment", "GATE_SCORING_COMPLETE"),
            ("Treatment", "Readout", "GATE_TREATMENT_ALIGNED"),
            ("Readout", "Evidence_Residual", "GATE_READOUT_COMPLETE"),
        ],
    )
    for risk, pairs in (
        (risk3, [(None, "Intake", "CREATE"), ("Intake", "Preconditions", "GATE_INTAKE_COMPLETE"),
                 ("Preconditions", "Scoring", "GATE_PRECONDITIONS_MET"),
                 ("Scoring", "Treatment", "GATE_SCORING_COMPLETE")]),
        (risk4, [(None, "Intake", "CREATE"), ("Intake", "Preconditions", "GATE_INTAKE_COMPLETE"),
                 ("Preconditions", "Scoring", "GATE_PRECONDITIONS_MET")]),
        (risk5, [(None, "Intake", "CREATE")]),
    ):
        _history(session, risk, pairs)

    # Risk to control linkage, with the CE snapshot taken at link time.
    for risk, objectives in (
        (risk1, [(ctl1, "CE-Medium")]),
        (risk2, [(ctl4, "CE-Low")]),
        (risk3, [(ctl2, "CE-High")]),
        (risk4, [(ctl3, "CE-Unvalidated")]),
    ):
        for obj, ce in objectives:
            session.add(
                RiskControlLink(
                    risk_id=risk.id,
                    objective_id=obj.id,
                    ce_at_assessment=ce,
                    linked_by=analyst.id,
                )
            )

    session.add(
        RiskTreatmentLink(
            risk_id=risk1.id, treatment_id=trt1.id, is_primary=True, linked_by=analyst.id
        )
    )
    session.add(
        RiskTreatmentLink(
            risk_id=risk2.id, treatment_id=trt2.id, is_primary=True, linked_by=analyst.id
        )
    )
    session.add(
        RiskTreatmentLink(
            risk_id=risk4.id, treatment_id=trt3.id, is_primary=True, linked_by=analyst.id
        )
    )
    session.flush()

    # -- threat model ------------------------------------------------------
    tm1 = ThreatModel(
        reference="TM-001",
        title="Payments API authorisation flow",
        attack_surface_id=payments.id,
        lifecycle_state="Active",
        methodology="STRIDE",
        description=(
            "Threat model covering the payment authorisation path from client request "
            "through risk scoring to settlement instruction."
        ),
        system_owner_id=system_owner.id,
        appsec_partner_id=appsec.id,
        appsec_signoff_by=appsec.id,
        appsec_signoff_at=utcnow(),
        owner_signoff_by=system_owner.id,
        owner_signoff_at=utcnow(),
        created_by=appsec.id,
    )
    session.add(tm1)
    session.flush()

    gateway = ThreatComponent(
        threat_model_id=tm1.id,
        name="Authorisation service",
        component_type="Process",
        description="Evaluates and authorises payment instructions.",
        data_classification="Restricted",
        data_types=["Payment_Card", "PII", "Financial_Records"],
        trust_zone="Internal_Network",
        exposure="Partner_Facing",
        attack_surface_id=payments.id,
    )
    ledger = ThreatComponent(
        threat_model_id=tm1.id,
        name="Transaction ledger",
        component_type="Datastore",
        description="Append-only record of authorised transactions.",
        data_classification="Restricted",
        data_types=["Financial_Records", "PII"],
        trust_zone="Restricted_Enclave",
        exposure="Internal_Only",
        attack_surface_id=payments.id,
    )
    boundary = ThreatComponent(
        threat_model_id=tm1.id,
        name="Internet to DMZ boundary",
        component_type="Trust_Boundary",
        description="Public edge terminating at the API gateway.",
        data_classification="Public",
        data_types=["Public_Content"],
        trust_zone="DMZ",
        exposure="Internet_Facing",
        attack_surface_id=payments.id,
    )
    admin_console = ThreatComponent(
        threat_model_id=tm1.id,
        name="Operations console",
        component_type="External_Entity",
        description="Internal console used by payment operations staff.",
        data_classification="Confidential",
        data_types=["Credentials", "PII"],
        trust_zone="Internal_Network",
        exposure="Internal_Only",
        attack_surface_id=payments.id,
    )
    # A deliberate gap: Restricted data replicated into the reporting sandbox,
    # which sits on an asset with no operating control covering it. The context
    # panel reports this; the Review gate blocks sign-off on it (TINV-11) until
    # someone has actually thought about it.
    replica_flow = ThreatComponent(
        threat_model_id=tm1.id,
        name="Analytics replication flow",
        component_type="Data_Flow",
        description=(
            "Nightly replication of settled transactions into the reporting sandbox."
        ),
        data_classification="Restricted",
        data_types=["PII", "Financial_Records"],
        trust_zone="Third_Party",
        exposure="Partner_Facing",
        attack_surface_id=warehouse.id,
    )
    session.add_all([gateway, ledger, boundary, admin_console, replica_flow])
    session.flush()
    replica_flow.source_component_id = ledger.id
    session.flush()

    thr1 = ThreatScenario(
        reference="THR-001",
        threat_model_id=tm1.id,
        component_id=admin_console.id,
        category="Spoofing",
        description=(
            "An attacker who phishes an operations engineer authenticates to the console "
            "and authorises fraudulent payment instructions."
        ),
        inherent_severity="Critical",
        status="Mitigated",
        status_rationale=(
            "Phishing-resistant MFA is enforced on every console authentication path "
            "and evidenced in the IdP conditional access export."
        ),
        created_by=appsec.id,
    )
    thr2 = ThreatScenario(
        reference="THR-002",
        threat_model_id=tm1.id,
        component_id=ledger.id,
        category="Tampering",
        description=(
            "A privileged operator alters historical ledger entries to conceal an "
            "unauthorised transaction."
        ),
        inherent_severity="High",
        status="Promoted_To_Risk",
        promoted_risk_id=risk2.id,
        created_by=appsec.id,
    )
    thr3 = ThreatScenario(
        reference="THR-003",
        threat_model_id=tm1.id,
        component_id=boundary.id,
        category="Denial_of_Service",
        description=(
            "Volumetric traffic against the public edge degrades authorisation latency "
            "beyond the settlement window."
        ),
        inherent_severity="Low",
        status="Accepted",
        acceptance_expiry=TODAY + timedelta(days=300),
        acceptance_rationale=(
            "Edge rate limiting and upstream scrubbing reduce this to an availability "
            "inconvenience within the agreed appetite. Reviewed at the next model refresh."
        ),
        status_rationale="Accepted locally at Low severity with a time-bound expiry.",
        created_by=appsec.id,
    )
    thr4 = ThreatScenario(
        reference="THR-004",
        threat_model_id=tm1.id,
        component_id=gateway.id,
        category="Repudiation",
        description=(
            "An operator disputes having authorised a transaction and no independent "
            "record establishes who acted."
        ),
        inherent_severity="Medium",
        status="Mitigated",
        status_rationale=(
            "Privileged session capture provides an independent record of who acted, "
            "though the review cadence itself is the subject of RISK-002."
        ),
        created_by=appsec.id,
    )
    # The gap scenario: sits on the replication flow, unresolved, and maps to an
    # exposure the register already carries rather than a new one.
    thr5 = ThreatScenario(
        reference="THR-005",
        threat_model_id=tm1.id,
        component_id=replica_flow.id,
        category="Information_Disclosure",
        description=(
            "The nightly replication writes Restricted customer records into a "
            "third-party managed sandbox with no encryption at rest, exposing them to "
            "anyone with read access to that environment."
        ),
        inherent_severity="High",
        # Carried by RISK-003 rather than promoted into a duplicate, which is what
        # linking with a resolving link type produces (TINV-1 / TINV-8).
        status="Promoted_To_Risk",
        promoted_risk_id=risk3.id,
        status_rationale=(
            "Carried by RISK-003, which already holds the unencrypted analytics "
            "replica at Tier 1."
        ),
        remediation_target_date=TODAY + timedelta(days=45),
        created_by=appsec.id,
    )
    session.add_all([thr1, thr2, thr3, thr4, thr5])
    session.flush()

    # THR-001 is mitigated by the MFA deployment on the Payments API. Failing that
    # deployment re-opens the scenario and strips the model's sign-off.
    session.add(
        ThreatMitigationLink(
            scenario_id=thr1.id,
            deployment_id=dep2.id,
            effectiveness_assurance="Fully_Mitigated",
            linked_by=appsec.id,
        )
    )
    # THR-004 is mitigated by privileged session logging, which is already Degraded.
    session.add(
        ThreatMitigationLink(
            scenario_id=thr4.id,
            deployment_id=dep5.id,
            effectiveness_assurance="Fully_Mitigated",
            linked_by=appsec.id,
        )
    )

    # -- discussion, evidence and risk linkage ----------------------------
    #
    # THR-005 is the connective tissue in miniature: a threat that maps onto an
    # exposure the register already carries (RISK-003), referenced rather than
    # promoted, with the conversation and the evidence that got it there.
    session.add(
        ThreatScenarioRiskLink(
            scenario_id=thr5.id,
            risk_id=risk3.id,
            link_type="Represents",
            rationale=(
                "RISK-003 already carries the unencrypted analytics replica at Tier 1. "
                "This scenario is the threat-model view of that same exposure, so it "
                "references the existing record rather than minting a duplicate."
            ),
            linked_by=appsec.id,
        )
    )
    for scenario, body, author in (
        (
            thr5,
            "Confirmed with the data platform team: the sandbox predates the "
            "customer-managed key rollout and the replication target has no KMS policy "
            "attached. Encryption at rest is not on by default in that account.",
            appsec.id,
        ),
        (
            thr5,
            "This is the same exposure the audit finding raised. Linking to RISK-003 "
            "rather than promoting a second record; the treatment plan there covers it.",
            analyst.id,
        ),
        (
            thr1,
            "Re-tested after the federation rollout. No static credential paths remain "
            "on the console.",
            appsec.id,
        ),
    ):
        session.add(
            ThreatScenarioComment(scenario_id=scenario.id, body=body, created_by=author)
        )

    for scenario, title, ref, etype, supports in (
        (
            thr1,
            "IdP conditional access export",
            "idp-conditional-access-2026-08-14.json; 100% WebAuthn enrolment on admin roles",
            "Configuration_Export",
            "Mitigated",
        ),
        (
            thr5,
            "Data platform architecture review",
            "DPR-2026-041: replication target account has no default encryption policy",
            "Design_Review",
            "Identified",
        ),
        (
            thr3,
            "Edge rate limiting configuration",
            "waf-ratelimit-policy-2026-06.yaml plus upstream scrubbing contract",
            "Configuration_Export",
            "Accepted",
        ),
    ):
        session.add(
            ThreatScenarioEvidence(
                scenario_id=scenario.id,
                title=title,
                evidence_ref=ref,
                evidence_type=etype,
                supports=supports,
                created_by=appsec.id,
            )
        )

    session.commit()
