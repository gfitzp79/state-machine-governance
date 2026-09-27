"""Control services: objective, activity, deployment, and CE assessment."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.errors import Conflict, NotFound
from app.core.governance import FAILURE_TYPES
from app.core.service import LifecycleService
from app.engine import AuditTrail, cascades
from app.engine.scoring import CE_EXPIRY_MONTHS, ScoringEngine
from app.modules.control.machine import (
    CONTROL_ACTIVITY_MACHINE,
    CONTROL_DEPLOYMENT_MACHINE,
    CONTROL_OBJECTIVE_MACHINE,
)
from app.modules.control.models import (
    AttackSurface,
    ControlActivity,
    ControlDeployment,
    ControlObjective,
    ControlTest,
    ControlTestCampaign,
)

TEST_INTERVAL_DAYS = {"Continuous": 7, "Monthly": 30, "Quarterly": 90, "Annual": 365}


class ObjectiveService(LifecycleService[ControlObjective]):
    model = ControlObjective
    machine = CONTROL_OBJECTIVE_MACHINE
    entity_name = "control_objective"
    reference_prefix = "CTL"
    taxonomy = {
        "family": "control_families",
        "control_type": "control_types",
        "automation_level": "automation_levels",
        "implementation_type": "implementation_types",
        "operating_frequency": "operating_frequencies",
        "assurance_method": "assurance_methods",
    }

    def create_objective(self, data: dict[str, Any]) -> ControlObjective:
        obj = ControlObjective(reference=self.next_reference(), **data)
        self.create(obj)
        self.session.commit()
        return obj

    def detail(self, obj: ControlObjective) -> dict[str, Any]:
        resolution = ScoringEngine.resolve_ce([obj])
        return {
            **summarise_objective(obj),
            "description": obj.description,
            "objective_statement": obj.objective_statement,
            "remediation_plan": obj.remediation_plan,
            "deprecation_rationale": obj.deprecation_rationale,
            "ce_resolution": resolution.as_dict(),
            "activities": [
                {
                    **summarise_activity(a),
                    "deployments": [summarise_deployment(d) for d in a.deployments],
                }
                for a in obj.activities
            ],
            "linked_risks": self._linked_risks(obj),
            "linked_policies": self._linked_policies(obj),
            "test_history": self._test_history(obj),
            "campaigns": [
                summarise_campaign(c)
                for c in self.session.execute(
                    select(ControlTestCampaign)
                    .where(ControlTestCampaign.objective_id == obj.id)
                    .order_by(ControlTestCampaign.tested_at.desc())
                ).scalars()
            ],
            "gates": self.gate_report(obj),
            "invariants": self.invariant_report(obj),
        }

    def _test_history(self, obj: ControlObjective, limit: int = 25) -> list[dict[str, Any]]:
        """Every deployment's tests in one timeline, each with what it changed."""
        rows = [
            {
                **summarise_test(t),
                "deployment_id": d.id,
                "deployment_reference": d.reference,
                "asset_name": d.surface.name if d.surface else None,
            }
            for d in obj.deployments
            for t in d.tests
        ]
        rows.sort(key=lambda r: (r["tested_at"], r["sequence"]), reverse=True)
        return rows[:limit]

    def _linked_risks(self, obj: ControlObjective) -> list[dict[str, Any]]:
        from app.modules.risk.models import Risk, RiskControlLink

        links = (
            self.session.query(RiskControlLink)
            .filter(RiskControlLink.objective_id == obj.id)
            .all()
        )
        if not links:
            return []
        risks = (
            self.session.query(Risk).filter(Risk.id.in_([l.risk_id for l in links])).all()
        )
        return [
            {
                "id": r.id,
                "reference": r.reference,
                "title": r.title,
                "reported_rating": r.reported_rating,
                "lifecycle_state": r.lifecycle_state,
                "treatment_strategy": r.treatment_strategy,
                "residual_score_locked": r.residual_score_locked,
            }
            for r in risks
        ]

    def _linked_policies(self, obj: ControlObjective) -> list[dict[str, Any]]:
        from app.modules.policy.models import Policy, PolicyControlLink

        links = (
            self.session.query(PolicyControlLink)
            .filter(PolicyControlLink.objective_id == obj.id)
            .all()
        )
        if not links:
            return []
        policies = {
            p.id: p
            for p in self.session.query(Policy)
            .filter(Policy.id.in_([l.policy_id for l in links]))
            .all()
        }
        return [
            {
                "id": l.policy_id,
                "reference": policies[l.policy_id].reference if l.policy_id in policies else None,
                "title": policies[l.policy_id].title if l.policy_id in policies else None,
                "realignment_required": l.realignment_required,
                "realignment_due": l.realignment_due,
            }
            for l in links
        ]

    def confirm_alignment(self, obj: ControlObjective, policy_id: str) -> None:
        """Closes out a PINV-7 re-alignment obligation."""
        from app.modules.policy.models import Policy, PolicyControlLink

        link = (
            self.session.query(PolicyControlLink)
            .filter(
                PolicyControlLink.objective_id == obj.id,
                PolicyControlLink.policy_id == policy_id,
            )
            .first()
        )
        if link is None:
            raise NotFound("no policy link to confirm")
        link.realignment_required = False
        policy = self.session.get(Policy, policy_id)
        if policy is not None:
            policy.realignment_pending = sum(
                1 for l in policy.control_links if l.realignment_required
            )
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="control_objective",
            entity_id=obj.id,
            action="ALIGNMENT_CONFIRMED",
            changed_fields={"policy_id": policy_id},
        )
        self.session.commit()


class ActivityService(LifecycleService[ControlActivity]):
    model = ControlActivity
    machine = CONTROL_ACTIVITY_MACHINE
    entity_name = "control_activity"
    taxonomy = {
        "automation_level": "automation_levels",
        "operating_frequency": "operating_frequencies",
        "evidence_type": "evidence_types",
    }
    reference_prefix = "ACT"

    def create_activity(self, data: dict[str, Any]) -> ControlActivity:
        act = ControlActivity(reference=self.next_reference(), **data)
        self.create(act)
        self.session.commit()
        return act


class DeploymentService(LifecycleService[ControlDeployment]):
    model = ControlDeployment
    machine = CONTROL_DEPLOYMENT_MACHINE
    entity_name = "control_deployment"
    reference_prefix = "DEP"
    taxonomy = {"test_frequency": "test_frequencies"}

    def create_deployment(self, data: dict[str, Any]) -> ControlDeployment:
        dep = ControlDeployment(reference=self.next_reference(), **data)
        self.create(dep)
        self.session.commit()
        return dep

    def assess_ce(self, dep: ControlDeployment, data: dict[str, Any]) -> ControlDeployment:
        """CINV-1 and CINV-4 both land here, before the write."""
        if dep.is_read_only:
            raise Conflict(
                "CINV-4 / DL-3: this deployment is decommissioned and read-only. "
                "Control effectiveness cannot be assessed on it."
            )
        if not dep.ce_editable:
            raise Conflict(
                "DL-2: control effectiveness is assessable only while the deployment is "
                "Active or Degraded. This one is " + dep.deployment_status + "."
            )
        rating = data.get("ce_rating", dep.ce_rating)
        evidence = data.get("ce_evidence_ref", dep.ce_evidence_ref)
        if rating != "CE-Unvalidated" and not (evidence or "").strip():
            raise Conflict(
                "CINV-1: a rating above CE-Unvalidated requires an evidence reference. "
                "Configurations, logs, dashboards, audit artefacts or test output. "
                "Verbal attestation is not evidence."
            )

        changes = {
            "ce_rating": rating,
            "ce_evidence_ref": evidence,
            "ce_notes": data.get("ce_notes", dep.ce_notes),
            "ce_assessed_by": self.actor_id,
            "ce_assessed_at": date.today(),
        }
        previous = dep.ce_rating
        self.apply(dep, changes, action="CE_ASSESSMENT")
        self.session.flush()

        # CE movement is a cascade trigger even without a lifecycle transition.
        from app.engine.scoring import CE_STRENGTH

        effects: list[dict[str, Any]] = []
        if CE_STRENGTH.get(rating, 0) < CE_STRENGTH.get(previous, 0):
            effects = cascades.emit(
                "deployment.degraded", self.session, self.entity_name, dep.id, self.actor_id
            )
        elif CE_STRENGTH.get(rating, 0) > CE_STRENGTH.get(previous, 0):
            effects = cascades.emit(
                "deployment.restored", self.session, self.entity_name, dep.id, self.actor_id
            )
        if effects:
            AuditTrail.record(
                self.session,
                actor_id=self.actor_id,
                entity_type=self.entity_name,
                entity_id=dep.id,
                action="CE_CASCADE",
                changed_fields={"from": previous, "to": rating, "cascades": effects},
            )
        self.session.commit()
        return dep

    # Who may record a control test result. The consequent state change is not
    # gated on the same list, because DL-1 makes it automatic rather than
    # discretionary: the test result is the decision.
    TESTER_ROLES = (
        "Control_Owner",
        "Control_Operator",
        "Risk_Analyst",
        "GRC_Engineer",
        "AppSec_Lead",
        "AppSec_Engineer",
        "CISO",
        "Admin",
        "Auditor",
    )

    def record_test(
        self,
        dep: ControlDeployment,
        data: dict[str, Any],
        *,
        campaign: ControlTestCampaign | None = None,
        commit: bool = True,
    ) -> ControlTest:
        """Append-only. A Fail drives the deployment through its own state machine
        rather than just setting a column, so the cascade fires.

        The state change is fired as a system transition. DL-1 says a failed test
        triggers failure propagation; it is a consequence of the evidence, not a
        discretionary decision someone opts into, so it does not depend on the
        tester holding a control-lifecycle role. The gate preconditions still apply.

        How far a failure propagates depends on what failed (CINV-16): a Design
        failure takes the objective into Failure, an Operating failure stays on
        this asset. What it changed is measured before and after the cascade
        and written onto the test row in the same transaction (section 25.4).
        """
        from app.modules import impact

        if dep.is_read_only:
            raise Conflict("CINV-4 / DL-3: this deployment is decommissioned and read-only")
        if not any(r in self.actor_roles for r in self.TESTER_ROLES):
            raise Conflict(
                "recording a control test result requires one of: "
                + ", ".join(self.TESTER_ROLES)
            )

        result = data["result"]
        failure_type = data.get("failure_type")
        if result != "Fail" and failure_type:
            raise Conflict(
                "CINV-16: a failure type describes a Fail. A " + result
                + " result carries none."
            )
        if failure_type and failure_type not in FAILURE_TYPES:
            raise Conflict(
                "CINV-16: " + str(failure_type) + " is not a failure type. Use one of: "
                + ", ".join(FAILURE_TYPES),
                detail={"allowed": list(FAILURE_TYPES)},
            )
        classified_by_default = result == "Fail" and not failure_type
        if classified_by_default:
            failure_type = "Design"

        objective = dep.activity.objective
        before = impact.snapshot(self.session, objective)

        sequence = len(dep.tests) + 1
        interval = TEST_INTERVAL_DAYS.get(dep.test_frequency, 90)
        dep.last_test_result = result
        dep.last_tested_date = date.today()
        dep.next_test_due = date.today() + timedelta(days=interval)
        self.session.flush()

        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type=self.entity_name,
            entity_id=dep.id,
            action="CONTROL_TEST",
            changed_fields={
                "result": result,
                "sequence": sequence,
                "failure_type": failure_type,
                **(
                    {"classification": "unclassified failure recorded as Design (CINV-16)"}
                    if classified_by_default
                    else {}
                ),
                **({"campaign": campaign.reference} if campaign else {}),
            },
        )

        routing = {"campaign_id": campaign.id} if campaign else {}
        effects: list[dict[str, Any]] = []
        # A failing test is not a note on a record. It moves the state machine.
        if result == "Fail" and dep.deployment_status in ("Active", "Degraded"):
            effects = self.transition(
                dep, "Failed", system=True, commit=False,
                reason=failure_type.lower() + " failure: control test failed",
                failure_type=failure_type, **routing,
            )["cascades"]
        elif result == "Partial" and dep.deployment_status == "Active":
            effects = self.transition(
                dep, "Degraded", system=True, commit=False,
                reason="control test returned partial", **routing,
            )["cascades"]
        elif result == "Pass":
            effects = self._pass(dep, data, routing)

        self.session.flush()
        after = impact.snapshot(self.session, objective)
        described = impact.describe(
            before, after, {dep.attack_surface_id}, failure_type=failure_type
        )
        described["cascade_effects"] = len(effects)

        test = ControlTest(
            deployment_id=dep.id,
            result=result,
            failure_type=failure_type,
            evidence_ref=data.get("evidence_ref"),
            notes=data.get("notes"),
            tested_by=self.actor_id,
            sequence=sequence,
            supersedes_id=data.get("supersedes_id"),
            campaign_id=campaign.id if campaign else None,
            impact=described,
        )
        self.session.add(test)
        self.session.flush()
        self.enforce(test, entity_name="control_test")

        # Alerts on outcomes. A campaign sends its digest once, when it closes.
        if campaign is None:
            cascades.emit(
                "control_test.impact_assessed", self.session, "control_objective",
                objective.id, self.actor_id,
                impact=described,
                subject=objective.reference + " test on " + (dep.surface.name if dep.surface else dep.reference),
            )
        if commit:
            self.session.commit()
        return test

    def _pass(self, dep: ControlDeployment, data: dict[str, Any], routing: dict) -> list:
        """A pass is evidence too (TST-4).

        With an evidence reference, a pass on a live deployment renews the
        assessment date behind its existing rating, so the rating does not
        expire while the control keeps passing. The rating itself is a judgement
        and a pass does not change it. On a Failed deployment the same pass is a
        remediation retest: it records the evidence and attempts the DL-4 gate,
        which returns the deployment to Active only if the gate agrees.
        """
        evidence = (data.get("evidence_ref") or "").strip()
        if not evidence:
            return []
        renewal = {
            "ce_evidence_ref": evidence,
            "ce_assessed_at": date.today(),
            "ce_assessed_by": self.actor_id,
        }
        if dep.deployment_status == "Failed":
            self.apply(dep, renewal, action="REMEDIATION_RETEST")
            self.session.flush()
            if self.machine.evaluate(dep, "Active", self.context()).passed:
                return self.transition(
                    dep, "Active", system=True, commit=False,
                    reason="remediation retest passed (DL-4)", **routing,
                )["cascades"]
            return []
        if dep.ce_editable and dep.ce_rating != "CE-Unvalidated":
            self.apply(dep, renewal, action="CE_RENEWED_BY_TEST")
        return []

    def detail(self, dep: ControlDeployment) -> dict[str, Any]:
        return {
            **summarise_deployment(dep),
            "ce_notes": dep.ce_notes,
            "decommission_rationale": dep.decommission_rationale,
            "tests": [summarise_test(t) for t in dep.tests],
            "gates": self.gate_report(dep),
            "invariants": self.invariant_report(dep),
        }


class CampaignService(DeploymentService):
    """A round of testing across a control's deployments (section 25.5).

    Each result goes through DeploymentService.record_test, so every rule that
    binds a single test binds a campaign. What the campaign adds is the
    population, which a single test cannot have, and one digest per owner
    instead of one alert per cascade. All of it is one transaction: a campaign
    half-recorded would be a finding about the tool rather than the control.
    """

    def run(
        self, objective: ControlObjective, title: str, results: list[dict[str, Any]]
    ) -> ControlTestCampaign:
        from app.modules import impact

        if not results:
            raise Conflict("a campaign needs at least one result")
        by_id = {d.id: d for d in objective.deployments}
        unknown = [r["deployment_id"] for r in results if r["deployment_id"] not in by_id]
        if unknown:
            raise Conflict(
                "these deployments do not belong to " + objective.reference + ": "
                + ", ".join(unknown)
            )
        seen: set[str] = set()
        for r in results:
            if r["deployment_id"] in seen:
                raise Conflict("each deployment appears once in a campaign")
            seen.add(r["deployment_id"])

        count = self.session.execute(
            select(func.count()).select_from(ControlTestCampaign)
        ).scalar_one()
        campaign = ControlTestCampaign(
            reference="CMP-" + str(count + 1).zfill(3),
            objective_id=objective.id,
            title=title,
            tested_by=self.actor_id,
            impact={},
        )
        self.session.add(campaign)
        self.session.flush()

        before = impact.snapshot(self.session, objective)
        for r in results:
            data = {k: v for k, v in r.items() if k != "deployment_id" and v is not None}
            self.record_test(by_id[r["deployment_id"]], data, campaign=campaign, commit=False)
        self.session.flush()
        self.session.refresh(objective)
        after = impact.snapshot(self.session, objective)

        tested_assets = {by_id[r["deployment_id"]].attack_surface_id for r in results}
        failures = {r.get("failure_type") or "Design" for r in results if r["result"] == "Fail"}
        described = impact.describe(
            before, after, tested_assets,
            failure_type="Design" if "Design" in failures else ("Operating" if failures else None),
        )
        described["population"] = impact.population(
            self.session, objective, {r["deployment_id"]: r["result"] for r in results}
        )
        described["results"] = [
            {
                "deployment": by_id[r["deployment_id"]].reference,
                "asset": by_id[r["deployment_id"]].surface.name,
                "result": r["result"],
                "failure_type": (r.get("failure_type") or "Design") if r["result"] == "Fail" else None,
            }
            for r in results
        ]
        campaign.impact = described

        effects = cascades.emit(
            "control_test.impact_assessed", self.session, "control_objective",
            objective.id, self.actor_id,
            impact=described,
            campaign_id=campaign.id,
            subject=campaign.reference + " (" + objective.reference + ")",
        )
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="control_objective",
            entity_id=objective.id,
            action="TEST_CAMPAIGN",
            changed_fields={
                "campaign": campaign.reference,
                "results": len(results),
                "failed": sum(1 for r in results if r["result"] == "Fail"),
                "cascades": effects,
            },
        )
        self.session.commit()
        return campaign


def summarise_campaign(campaign: ControlTestCampaign) -> dict[str, Any]:
    return {
        "id": campaign.id,
        "reference": campaign.reference,
        "objective_id": campaign.objective_id,
        "title": campaign.title,
        "tested_by": campaign.tested_by,
        "tested_at": campaign.tested_at,
        "impact": campaign.impact,
    }


class AssetService(LifecycleService[AttackSurface]):
    model = AttackSurface
    machine = CONTROL_OBJECTIVE_MACHINE  # unused; assets have no lifecycle
    entity_name = "attack_surface"
    taxonomy = {"tier": "asset_tiers"}

    def create_asset(self, data: dict[str, Any]) -> AttackSurface:
        self.validate_taxonomy(data)
        asset = AttackSurface(**data)
        self.session.add(asset)
        self.session.commit()
        return asset


# -- serialisation ---------------------------------------------------------


def summarise_test(t: ControlTest) -> dict[str, Any]:
    return {
        "id": t.id,
        "sequence": t.sequence,
        "result": t.result,
        "failure_type": t.failure_type,
        "evidence_ref": t.evidence_ref,
        "notes": t.notes,
        "tested_by": t.tested_by,
        "tested_at": t.tested_at,
        "supersedes_id": t.supersedes_id,
        "campaign_id": t.campaign_id,
        "impact": t.impact or None,
    }


def summarise_objective(obj: ControlObjective) -> dict[str, Any]:
    resolution = ScoringEngine.resolve_ce([obj])
    deployments = obj.deployments
    return {
        "id": obj.id,
        "reference": obj.reference,
        "title": obj.title,
        "family": obj.family,
        "control_type": obj.control_type,
        "lifecycle_state": obj.lifecycle_state,
        "control_owner_id": obj.control_owner_id,
        "automation_level": obj.automation_level,
        "implementation_type": obj.implementation_type,
        "operating_frequency": obj.operating_frequency,
        "assurance_method": obj.assurance_method,
        "is_key_control": obj.is_key_control,
        "effective_ce": resolution.effective_ce,
        "contributes_to_scoring": obj.contributes_to_scoring,
        "activity_count": len(obj.activities),
        "deployment_count": len(deployments),
        "failing_deployments": sum(
            1 for d in deployments if d.deployment_status in ("Failed", "Degraded")
        ),
        "failure_declared_at": obj.failure_declared_at,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


def summarise_activity(act: ControlActivity) -> dict[str, Any]:
    return {
        "id": act.id,
        "reference": act.reference,
        "objective_id": act.objective_id,
        "title": act.title,
        "description": act.description,
        "lifecycle_state": act.lifecycle_state,
        "control_operator_id": act.control_operator_id,
        "suspension_rationale": act.suspension_rationale,
        "automation_level": act.automation_level,
        "operating_frequency": act.operating_frequency,
        "procedure_ref": act.procedure_ref,
        "tooling": act.tooling,
        "evidence_type": act.evidence_type,
        "deployment_count": len(act.deployments),
    }


def summarise_deployment(dep: ControlDeployment) -> dict[str, Any]:
    return {
        "id": dep.id,
        "reference": dep.reference,
        "activity_id": dep.activity_id,
        "attack_surface_id": dep.attack_surface_id,
        "asset_name": dep.surface.name if dep.surface else None,
        "deployment_status": dep.deployment_status,
        "ce_rating": dep.ce_rating,
        "ce_evidence_ref": dep.ce_evidence_ref,
        "ce_assessed_at": dep.ce_assessed_at,
        "ce_assessed_by": dep.ce_assessed_by,
        "ce_expired": ScoringEngine.ce_expired(dep.ce_assessed_at, dep.test_frequency),
        "ce_expiry_months": CE_EXPIRY_MONTHS.get(dep.test_frequency, 24),
        "ce_editable": dep.ce_editable,
        "test_frequency": dep.test_frequency,
        "last_test_result": dep.last_test_result,
        "last_tested_date": dep.last_tested_date,
        "next_test_due": dep.next_test_due,
        "test_count": len(dep.tests),
    }
