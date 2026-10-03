"""Control services: objective, activity, deployment, and CE assessment."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.errors import Conflict, NotFound
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
)

TEST_INTERVAL_DAYS = {"Continuous": 7, "Monthly": 30, "Quarterly": 90, "Annual": 365}


class ObjectiveService(LifecycleService[ControlObjective]):
    edit_kind = "control"
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

    def on_transition(self, entity, result, transition, payload: dict) -> None:
        """A reason given when firing fills the rationale the gate asked for."""
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            return
        if result.gate in ("GATE_CONTROL_RECOVERED", "GATE_CONTROL_REDESIGN") and not entity.remediation_plan:
            entity.remediation_plan = reason
        if result.target == "Deprecated" and not entity.deprecation_rationale:
            entity.deprecation_rationale = reason

    def create_objective(self, data: dict[str, Any]) -> ControlObjective:
        self.require_edit()
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
            # PERM-1, so the interface can disable what the API would refuse.
            "can_edit": self.can_edit(),
            "linked_policies": self._linked_policies(obj),
            "gates": self.gate_report(obj),
            "invariants": self.invariant_report(obj),
        }

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
        """Closes out a PINV-7 re-alignment obligation. The control's own owner
        confirms it, or anyone who may edit controls."""
        self.require_edit(also_user=obj.control_owner_id)
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
    edit_kind = "control"
    model = ControlActivity
    machine = CONTROL_ACTIVITY_MACHINE
    entity_name = "control_activity"
    taxonomy = {
        "automation_level": "automation_levels",
        "operating_frequency": "operating_frequencies",
        "evidence_type": "evidence_types",
    }
    reference_prefix = "ACT"

    def on_transition(self, entity, result, transition, payload: dict) -> None:
        reason = str(payload.get("reason") or "").strip()
        if reason and result.target == "Suspended" and not entity.suspension_rationale:
            entity.suspension_rationale = reason

    def create_activity(self, data: dict[str, Any]) -> ControlActivity:
        self.require_edit()
        act = ControlActivity(reference=self.next_reference(), **data)
        self.create(act)
        self.session.commit()
        return act


class DeploymentService(LifecycleService[ControlDeployment]):
    edit_kind = "control"
    model = ControlDeployment
    machine = CONTROL_DEPLOYMENT_MACHINE
    entity_name = "control_deployment"
    reference_prefix = "DEP"
    taxonomy = {"test_frequency": "test_frequencies"}

    def on_transition(self, entity, result, transition, payload: dict) -> None:
        reason = str(payload.get("reason") or "").strip()
        if reason and result.target == "Decommissioned" and not entity.decommission_rationale:
            entity.decommission_rationale = reason

    def create_deployment(self, data: dict[str, Any]) -> ControlDeployment:
        self.require_edit()
        dep = ControlDeployment(reference=self.next_reference(), **data)
        self.create(dep)
        self.session.commit()
        return dep

    def assess_ce(self, dep: ControlDeployment, data: dict[str, Any]) -> ControlDeployment:
        """CINV-1 and CINV-4 both land here, before the write."""
        self.require_edit()
        if dep.is_read_only:
            raise Conflict(
                "CINV-4 / DL-3: this deployment is decommissioned and read-only. "
                "Control effectiveness cannot be assessed on it."
            )
        if not dep.ce_editable:
            raise Conflict(
                "DL-2: control effectiveness is assessable only while the deployment is "
                "Active, Degraded or Failed. This one is " + dep.deployment_status + "."
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

    def record_test(self, dep: ControlDeployment, data: dict[str, Any]) -> ControlTest:
        """Append-only. A Fail drives the deployment through its own state machine
        rather than just setting a column, so the cascade fires.

        The state change is fired as a system transition. DL-1 says a failed test
        triggers failure propagation; it is a consequence of the evidence, not a
        discretionary decision someone opts into, so it does not depend on the
        tester holding a control-lifecycle role. The gate preconditions still apply.

        A test result is evidence about a control, not an edit to it, so it is
        not governed by PERM-1: independent testers (internal audit, AppSec)
        record results on controls they could never edit. The roles that may
        edit controls are added to the testers.
        """
        from app.core.governance import governance

        if dep.is_read_only:
            raise Conflict("CINV-4 / DL-3: this deployment is decommissioned and read-only")
        testers = tuple(dict.fromkeys(self.TESTER_ROLES + governance.edit_permissions.get("control", ())))
        if not any(r in self.actor_roles for r in testers):
            raise Conflict(
                "recording a control test result requires one of: " + ", ".join(testers)
            )

        sequence = len(dep.tests) + 1
        test = ControlTest(
            deployment_id=dep.id,
            result=data["result"],
            evidence_ref=data.get("evidence_ref"),
            notes=data.get("notes"),
            tested_by=self.actor_id,
            sequence=sequence,
            supersedes_id=data.get("supersedes_id"),
        )
        self.session.add(test)

        interval = TEST_INTERVAL_DAYS.get(dep.test_frequency, 90)
        dep.last_test_result = data["result"]
        dep.last_tested_date = date.today()
        dep.next_test_due = date.today() + timedelta(days=interval)
        self.session.flush()

        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type=self.entity_name,
            entity_id=dep.id,
            action="CONTROL_TEST",
            changed_fields={"result": data["result"], "sequence": sequence},
        )

        # A failing test is not a note on a record. It moves the state machine.
        if data["result"] == "Fail" and dep.deployment_status in ("Active", "Degraded"):
            self.transition(dep, "Failed", system=True, reason="control test failed")
        elif data["result"] == "Partial" and dep.deployment_status == "Active":
            self.transition(
                dep, "Degraded", system=True, reason="control test returned partial"
            )
        else:
            self.session.commit()
        return test

    def detail(self, dep: ControlDeployment) -> dict[str, Any]:
        return {
            **summarise_deployment(dep),
            "ce_notes": dep.ce_notes,
            "decommission_rationale": dep.decommission_rationale,
            "tests": [
                {
                    "id": t.id,
                    "sequence": t.sequence,
                    "result": t.result,
                    "evidence_ref": t.evidence_ref,
                    "notes": t.notes,
                    "tested_by": t.tested_by,
                    "tested_at": t.tested_at,
                    "supersedes_id": t.supersedes_id,
                }
                for t in dep.tests
            ],
            "gates": self.gate_report(dep),
            "invariants": self.invariant_report(dep),
        }


class AssetService(LifecycleService[AttackSurface]):
    edit_kind = "asset"
    model = AttackSurface
    machine = CONTROL_OBJECTIVE_MACHINE  # unused; assets have no lifecycle
    entity_name = "attack_surface"
    taxonomy = {"tier": "asset_tiers"}

    EDITABLE = ("name", "tier", "description", "system_owner_id")

    def create_asset(self, data: dict[str, Any]) -> AttackSurface:
        """Registered by anyone who may edit assets, or by any System_Owner:
        owners register their own systems.

        This used to add the row directly, which skipped the invariants, so
        CINV-14 (the named system owner holds System_Owner) never ran on a new
        asset, and the creation was not audited.
        """
        if not ("System_Owner" in self.actor_roles or self.can_edit()):
            self.require_edit()
        asset = AttackSurface(**data)
        self.create(asset)
        self.session.commit()
        return asset

    def update_asset(self, asset: AttackSurface, data: dict[str, Any]) -> AttackSurface:
        """An asset changes: renamed, re-tiered, re-described or handed to a new
        owner. Edited by its own system owner or by anyone who may edit assets
        (PERM-1). A new owner must hold System_Owner (CINV-14), which apply()
        enforces before anything is written."""
        self.require_edit(also_user=asset.system_owner_id)
        changes = {k: v for k, v in data.items() if k in self.EDITABLE}
        self.apply(asset, changes)
        self.session.commit()
        return asset


# -- serialisation ---------------------------------------------------------


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
