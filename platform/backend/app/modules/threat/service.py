"""Threat model service.

Scenario resolution is the interesting method: it is the single place where
TINV-3, TINV-4 and TINV-5 are all applied, and where a Medium-or-above scenario
that cannot be mitigated is turned into a real risk record rather than a note.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.errors import Conflict, NotFound
from app.core.governance import governance
from app.core.model_base import utcnow
from app.core.service import LifecycleService
from app.engine import AuditTrail, cascades
from app.modules.control.models import ControlDeployment
from app.modules.threat.context import ThreatContext
from app.modules.threat.machine import THREAT_MODEL_MACHINE
from app.modules.threat.models import (
    SEVERITY_ORDER,
    ThreatComponent,
    ThreatMitigationLink,
    ThreatModel,
    ThreatScenario,
    ThreatScenarioComment,
    ThreatScenarioEvidence,
    ThreatScenarioRiskLink,
)


class ThreatModelService(LifecycleService[ThreatModel]):
    model = ThreatModel
    machine = THREAT_MODEL_MACHINE
    entity_name = "threat_model"
    reference_prefix = "TM"

    def create_model(self, data: dict[str, Any]) -> ThreatModel:
        tm = ThreatModel(reference=self.next_reference(), created_by=self.actor_id, **data)
        self.create(tm)
        self.session.commit()
        return tm

    # -- components -------------------------------------------------------

    COMPONENT_TAXONOMY = {
        "data_classification": "data_classifications",
        "trust_zone": "trust_zones",
        "exposure": "exposure_levels",
    }

    def _validate_component(self, data: dict[str, Any]) -> None:
        """Component attributes are configured taxonomy, so a value outside the
        organisation's model is refused with the file to change."""
        for field, config_key in self.COMPONENT_TAXONOMY.items():
            value = data.get(field)
            if value is None:
                continue
            allowed = getattr(governance, config_key)
            if value not in allowed:
                raise Conflict(
                    str(value) + " is not a configured " + field.replace("_", " ")
                    + ". Configured values are: " + ", ".join(str(a) for a in allowed)
                    + ". Add it to config/governance.yml and restart the API.",
                    detail={"field": field, "allowed": list(allowed)},
                )
        for data_type in data.get("data_types") or []:
            if data_type not in governance.data_types:
                raise Conflict(
                    str(data_type) + " is not a configured data type. Configured "
                    "values are: " + ", ".join(governance.data_types)
                )

    def add_component(self, tm: ThreatModel, data: dict[str, Any]) -> ThreatComponent:
        self._validate_component(data)
        component = ThreatComponent(threat_model_id=tm.id, **data)
        self.session.add(component)
        self.session.flush()
        # TINV-9: sensitive data cannot float outside a declared trust zone.
        self.enforce(component, "threat_component")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_component",
            entity_id=component.id,
            action="CREATE",
            changed_fields={
                "name": component.name,
                "component_type": component.component_type,
                "data_classification": component.data_classification,
                "trust_zone": component.trust_zone,
            },
        )
        self.session.commit()
        self.session.refresh(tm)
        return component

    def update_component(
        self, tm: ThreatModel, component_id: str, data: dict[str, Any]
    ) -> ThreatComponent:
        component = self.session.get(ThreatComponent, component_id)
        if component is None or component.threat_model_id != tm.id:
            raise NotFound("component not found on this model")
        self._validate_component(data)
        before = {k: getattr(component, k, None) for k in data}
        for field, value in data.items():
            if hasattr(component, field):
                setattr(component, field, value)
        self.session.flush()
        self.enforce(component, "threat_component")
        diff = AuditTrail.diff(before, {k: getattr(component, k, None) for k in data})
        if diff:
            AuditTrail.record(
                self.session,
                actor_id=self.actor_id,
                entity_type="threat_component",
                entity_id=component.id,
                action="UPDATE",
                changed_fields=diff,
            )
        self.session.commit()
        self.session.refresh(tm)
        return component

    def delete_component(self, tm: ThreatModel, component_id: str) -> None:
        component = self.session.get(ThreatComponent, component_id)
        if component is None or component.threat_model_id != tm.id:
            raise NotFound("component not found on this model")
        if any(s.component_id == component_id for s in tm.scenarios):
            raise Conflict("remove the scenarios on this component first")
        self.session.delete(component)
        self.session.commit()

    # -- scenarios --------------------------------------------------------

    # -- context ----------------------------------------------------------

    def environment(self, tm: ThreatModel) -> dict[str, Any]:
        """The environment this model sits in. Read-only by construction.

        Deliberately not named `context`: the base service uses that for the
        TransitionContext every gate and invariant is evaluated against, and the
        two must never be confused.
        """
        return ThreatContext.for_model(self.session, tm)

    # -- scenarios --------------------------------------------------------

    def add_scenario(self, tm: ThreatModel, data: dict[str, Any]) -> ThreatScenario:
        count = self.session.query(ThreatScenario).count()
        scenario = ThreatScenario(
            reference="THR-" + str(count + 1).zfill(3),
            threat_model_id=tm.id,
            created_by=self.actor_id,
            **data,
        )
        self.session.add(scenario)
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        self.session.commit()
        return scenario

    def mitigate(self, scenario: ThreatScenario, deployment_id: str, assurance: str):
        """TINV-4: a scenario is Mitigated only by a control that is actually running."""
        deployment = self.session.get(ControlDeployment, deployment_id)
        if deployment is None:
            raise NotFound("control deployment not found")
        if deployment.deployment_status not in ("Active", "Degraded"):
            raise Conflict(
                "TINV-4: " + deployment.reference + " is " + deployment.deployment_status
                + ". A threat is only mitigated by a control that is actually operating."
            )
        if any(link.deployment_id == deployment_id for link in scenario.mitigations):
            raise Conflict("this deployment is already linked to the scenario")

        link = ThreatMitigationLink(
            scenario_id=scenario.id,
            deployment_id=deployment_id,
            effectiveness_assurance=assurance,
            linked_by=self.actor_id,
        )
        self.session.add(link)
        self.session.flush()
        self.session.refresh(scenario)

        # TM-PARTIAL: the scenario is Mitigated only when every link asserts full
        # coverage. Adding a partial link to an already-mitigated scenario pulls
        # it back to Identified, because partial coverage is an open threat.
        previous_status = scenario.status
        if scenario.fully_mitigated:
            scenario.status = "Mitigated"
            scenario.reopened_reason = None
        elif scenario.status == "Mitigated":
            scenario.status = "Identified"
            scenario.status_rationale = (
                "TM-PARTIAL: a mitigation link asserts only partial coverage, so "
                "the scenario remains open."
            )
            scenario.reopened_at = utcnow()

        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="MITIGATION_LINKED",
            changed_fields={
                "deployment": deployment.reference,
                "assurance": assurance,
                "status": scenario.status,
            },
        )

        # codified-rules section 20.3: mitigating a threat the register carries is
        # news the risk side needs. The residual is NOT updated here; the full
        # validation gate (RINV-1) still applies.
        effects = []
        if scenario.status == "Mitigated" and previous_status != "Mitigated":
            effects = cascades.emit(
                "threat.scenario_mitigated",
                self.session,
                "threat_scenario",
                scenario.id,
                self.actor_id,
            )
        self.session.flush()
        self.session.commit()
        self.session.refresh(scenario)
        return link

    def accept_locally(self, scenario: ThreatScenario, expiry: date, rationale: str):
        """TINV-3 and TINV-5 both refuse here before any write happens."""
        if (
            SEVERITY_ORDER[scenario.inherent_severity]
            >= governance.minimum_promotable_severity_rank
        ):
            raise Conflict(
                "TINV-3: a " + scenario.inherent_severity + " severity scenario cannot be "
                "accepted locally. Promote it to the risk register instead.",
                detail={"severity": scenario.inherent_severity, "required_action": "promote"},
            )
        if expiry <= date.today():
            raise Conflict("TINV-5: the acceptance expiry must be in the future")
        limit = date.today() + timedelta(
            days=governance.threat_local_acceptance_max_days
        )
        if expiry > limit:
            raise Conflict(
                "TINV-5: a local acceptance runs for at most "
                + str(governance.threat_local_acceptance_max_days)
                + " days. Latest permitted expiry is "
                + limit.isoformat()
            )
        scenario.status = "Accepted"
        scenario.acceptance_expiry = expiry
        scenario.acceptance_rationale = rationale
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        self.session.commit()
        return scenario

    def promote_to_risk(self, scenario: ThreatScenario, data: dict[str, Any]):
        """The bidirectional link that makes threat modelling part of GRC rather
        than an adjacent activity."""
        from app.modules.risk.service import RiskService

        if scenario.promoted_risk_id:
            raise Conflict("this scenario has already been promoted")

        model = scenario.model
        risk_service = RiskService(self.session, self.actor_id, self.actor_roles)
        severity_to_impact = {"Low": 2, "Medium": 3, "High": 4, "Critical": 5}
        risk = risk_service.create_risk(
            {
                "title": data.get("title")
                or ("Threat: " + scenario.description[:200]),
                "cause": data.get("cause")
                or (
                    "the "
                    + (scenario.component.name if scenario.component else "system")
                    + " component is exposed to "
                    + scenario.category.replace("_", " ").lower()
                ),
                "threat_event": data.get("threat_event") or scenario.description,
                "vulnerability": data.get("vulnerability")
                or (
                    "no operational control mitigates this threat on "
                    + (model.surface.name if model and model.surface else "the asset")
                ),
                "impact_statement": data.get("impact_statement")
                or (
                    "business impact assessed at "
                    + scenario.inherent_severity
                    + " severity in threat model "
                    + (model.reference if model else "")
                ),
                "intake_source": "Threat_Model",
                "tier": data.get("tier", "Tier_3"),
                # codified-rules section 20.1: a promoted threat is owned by the
                # system owner unless the promoter names someone else. A promotion
                # that produces an ownerless risk has moved the problem, not the
                # accountability.
                "risk_owner_id": data.get("risk_owner_id")
                or (model.system_owner_id if model else None),
                "risk_stakeholder_id": data.get("risk_stakeholder_id"),
                "risk_analyst_id": data.get("risk_analyst_id") or self.actor_id,
                "identified_by": "Threat model " + (model.reference if model else ""),
            }
        )
        scenario.status = "Promoted_To_Risk"
        scenario.promoted_risk_id = risk.id
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="PROMOTED_TO_RISK",
            changed_fields={
                "risk": risk.reference,
                "severity": scenario.inherent_severity,
                "suggested_impact": severity_to_impact.get(scenario.inherent_severity),
            },
        )
        self.session.commit()
        return risk

    def reopen_scenario(
        self, scenario: ThreatScenario, rationale: str
    ) -> ThreatScenario:
        """Return a resolved scenario to Identified.

        The reverse of mitigation or acceptance, and the same rule applies: a
        status change is a decision that carries a reason (TINV-10).
        """
        if scenario.status == "Identified":
            raise Conflict("this scenario is already Identified")
        if scenario.status == "Promoted_To_Risk":
            raise Conflict(
                "TINV-8: a promoted scenario is represented by a risk record. "
                "Manage it through that risk rather than reopening the scenario."
            )
        previous = scenario.status
        scenario.status = "Identified"
        scenario.status_rationale = rationale
        scenario.reopened_reason = rationale
        scenario.reopened_at = utcnow()
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="SCENARIO_REOPENED",
            changed_fields={"from": previous, "to": "Identified", "rationale": rationale},
        )
        self.session.commit()
        return scenario

    def update_scenario(
        self, scenario: ThreatScenario, data: dict[str, Any]
    ) -> ThreatScenario:
        """Edit the substance of a scenario. Status is never changed here; it
        moves only through the operations that carry its rules."""
        editable = (
            "description",
            "category",
            "inherent_severity",
            "remediation_target_date",
            "status_rationale",
            "component_id",
        )
        before = {k: getattr(scenario, k, None) for k in data if k in editable}
        for field, value in data.items():
            if field in editable:
                setattr(scenario, field, value)
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        diff = AuditTrail.diff(
            before, {k: getattr(scenario, k, None) for k in data if k in editable}
        )
        if diff:
            AuditTrail.record(
                self.session,
                actor_id=self.actor_id,
                entity_type="threat_scenario",
                entity_id=scenario.id,
                action="UPDATE",
                changed_fields=diff,
            )
        self.session.commit()
        return scenario

    def unlink_mitigation(self, scenario: ThreatScenario, link_id: str) -> ThreatScenario:
        """Removing the last mitigation returns the scenario to Identified.

        TINV-7 again: Mitigated is an assertion backed by a link. Remove the
        backing and the assertion cannot stand.
        """
        link = self.session.get(ThreatMitigationLink, link_id)
        if link is None or link.scenario_id != scenario.id:
            raise NotFound("mitigation link not found on this scenario")
        self.session.delete(link)
        self.session.flush()
        self.session.refresh(scenario)
        if scenario.status == "Mitigated" and not scenario.fully_mitigated:
            scenario.status = "Identified"
            scenario.status_rationale = (
                "Mitigating control link removed; the scenario is no longer fully "
                "covered (TINV-7 / TM-PARTIAL)."
            )
            scenario.reopened_at = utcnow()
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="MITIGATION_UNLINKED",
            changed_fields={"link_id": link_id, "status": scenario.status},
        )
        self.session.commit()
        return scenario

    # -- discussion and evidence -------------------------------------------

    def add_comment(
        self, scenario: ThreatScenario, body: str, parent_id: str | None = None
    ) -> ThreatScenarioComment:
        comment = ThreatScenarioComment(
            scenario_id=scenario.id,
            body=body,
            parent_comment_id=parent_id,
            created_by=self.actor_id,
        )
        self.session.add(comment)
        self.session.commit()
        self.session.refresh(scenario)
        return comment

    def add_evidence(
        self, scenario: ThreatScenario, data: dict[str, Any]
    ) -> ThreatScenarioEvidence:
        """Append-only. The database rejects UPDATE and DELETE on this table, so a
        correction supersedes rather than rewrites (TINV-10)."""
        evidence = ThreatScenarioEvidence(
            scenario_id=scenario.id,
            title=data["title"],
            evidence_ref=data["evidence_ref"],
            evidence_type=data.get("evidence_type"),
            notes=data.get("notes"),
            supports=data.get("supports"),
            supersedes_id=data.get("supersedes_id"),
            created_by=self.actor_id,
        )
        self.session.add(evidence)
        self.session.flush()
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="EVIDENCE_ADDED",
            changed_fields={"title": evidence.title, "supports": evidence.supports},
        )
        self.session.commit()
        self.session.refresh(scenario)
        return evidence

    # -- risk linkage -------------------------------------------------------

    def link_risk(
        self, scenario: ThreatScenario, risk_id: str, link_type: str, rationale: str | None
    ) -> ThreatScenarioRiskLink:
        """Reference an existing risk rather than minting a duplicate (TINV-8).

        On a mature system most threats map to exposures the register already
        carries. Promotion is for the ones it does not.
        """
        from app.modules.risk.models import Risk

        if link_type not in governance.risk_link_types:
            raise Conflict(
                link_type + " is not a configured risk link type. Configured values "
                "are: " + ", ".join(governance.risk_link_types)
            )
        creators = {
            t["id"] for t in governance.risk_link_type_detail if t.get("creates_risk")
        }
        if link_type in creators:
            raise Conflict(
                "TINV-8: " + link_type + " is the promotion link type and is created "
                "by promoting the scenario, not by linking. Use the promote action, "
                "or choose a referencing link type."
            )

        risk = self.session.get(Risk, risk_id)
        if risk is None:
            raise NotFound("risk " + risk_id + " not found")
        if any(link.risk_id == risk_id for link in scenario.risk_links):
            raise Conflict("this scenario is already linked to " + risk.reference)

        link = ThreatScenarioRiskLink(
            scenario_id=scenario.id,
            risk_id=risk_id,
            link_type=link_type,
            rationale=rationale,
            linked_by=self.actor_id,
        )
        self.session.add(link)
        self.session.flush()
        self.session.refresh(scenario)

        # A resolving link means the register demonstrably carries this exposure,
        # which is the same governance outcome as promotion. The scenario reaches
        # its end state without a duplicate record being minted (TINV-1 / TINV-8).
        if (
            link_type in governance.scenario_resolving_link_types
            and scenario.status == "Identified"
        ):
            scenario.status = "Promoted_To_Risk"
            scenario.promoted_risk_id = risk_id
            scenario.status_rationale = rationale or (
                "Carried by " + risk.reference + " in the risk register."
            )
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="RISK_LINKED",
            changed_fields={"risk": risk.reference, "link_type": link_type},
        )
        # The risk gains visibility of the threat that informed it.
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="risk",
            entity_id=risk.id,
            action="THREAT_LINKED",
            changed_fields={"scenario": scenario.reference, "link_type": link_type},
        )
        self.session.commit()
        self.session.refresh(scenario)
        return link

    def unlink_risk(self, scenario: ThreatScenario, link_id: str) -> None:
        """Removing the link that carried the exposure returns the scenario to
        Identified: the register no longer demonstrably holds it."""
        link = self.session.get(ThreatScenarioRiskLink, link_id)
        if link is None or link.scenario_id != scenario.id:
            raise NotFound("risk link not found on this scenario")
        was_resolving = link.link_type in governance.scenario_resolving_link_types
        risk_id = link.risk_id
        self.session.delete(link)
        self.session.flush()
        self.session.refresh(scenario)

        if was_resolving and scenario.promoted_risk_id == risk_id:
            scenario.promoted_risk_id = None
            if scenario.status == "Promoted_To_Risk":
                scenario.status = "Identified"
                scenario.status_rationale = (
                    "Risk register reference removed; the exposure is no longer "
                    "demonstrably carried."
                )
                scenario.reopened_at = utcnow()
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="RISK_UNLINKED",
            changed_fields={"link_id": link_id, "status": scenario.status},
        )
        self.session.commit()
        self.session.refresh(scenario)

    # -- sign-off ---------------------------------------------------------

    def sign_off(self, tm: ThreatModel, as_role: str) -> ThreatModel:
        """TINV-2. Team membership satisfies the AppSec signature; the System
        Owner signature is personal to the named owner."""
        if as_role == "appsec":
            if not any(
                r in self.actor_roles for r in ("AppSec_Lead", "AppSec_Engineer", "Admin")
            ):
                raise Conflict(
                    "TINV-2: AppSec sign-off requires AppSec_Lead or AppSec_Engineer"
                )
            if self.actor_id == tm.system_owner_id:
                raise Conflict(
                    "TINV-2: the System Owner cannot provide the AppSec signature. "
                    "The two signatures must be independent."
                )
            tm.appsec_signoff_by = self.actor_id
            tm.appsec_signoff_at = utcnow()
        elif as_role == "owner":
            if self.actor_id != tm.system_owner_id and "Admin" not in self.actor_roles:
                raise Conflict(
                    "TINV-2: only the named System Owner can provide the owner signature"
                )
            tm.owner_signoff_by = self.actor_id
            tm.owner_signoff_at = utcnow()
        else:
            raise Conflict("sign-off role must be 'appsec' or 'owner'")

        tm.signoff_stripped_reason = None
        self.session.flush()
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_model",
            entity_id=tm.id,
            action="SIGNOFF",
            changed_fields={"role": as_role},
        )
        self.session.commit()
        return tm

    # -- serialisation ----------------------------------------------------

    def _refresh_for_report(self, entity) -> None:
        """Re-read the entity before evaluating gates against it.

        Gate preconditions walk relationships. Any mutation that added or
        removed a child in this session leaves those collections cached, so a
        gate evaluated without this reports the state before the write the user
        just made. Cheap, and the alternative is remembering a refresh at every
        call site that touches a collection.
        """
        try:
            self.session.refresh(entity)
        except Exception:  # detached or pending: the caller's view is already fresh
            pass

    def detail(self, tm: ThreatModel) -> dict[str, Any]:
        self._refresh_for_report(tm)
        return {
            **summarise_model(tm),
            "description": tm.description,
            "signoff_stripped_reason": tm.signoff_stripped_reason,
            "components": [self.component_detail(c, tm) for c in tm.components],
            "scenarios": [self.scenario_detail(s) for s in tm.scenarios],
            "context": self.environment(tm),
            "gates": self.gate_report(tm),
            "invariants": self.invariant_report(tm),
        }

    def component_detail(self, c, tm) -> dict[str, Any]:
        return {
            "id": c.id,
            "name": c.name,
            "component_type": c.component_type,
            "description": c.description,
            "data_classification": c.data_classification,
            "data_types": list(c.data_types or []),
            "trust_zone": c.trust_zone,
            "trust_level": c.trust_level,
            "exposure": c.exposure,
            "attack_surface_id": c.attack_surface_id,
            "asset_name": c.surface.name if c.surface else (
                tm.surface.name if tm.surface else None
            ),
            "is_sensitive": c.is_sensitive,
            "crosses_boundary": c.crosses_boundary,
            "scenario_count": sum(1 for s in tm.scenarios if s.component_id == c.id),
            "invariants": self.invariant_report(c, "threat_component"),
        }

    def scenario_detail(self, s: ThreatScenario) -> dict[str, Any]:
        return {
            "id": s.id,
            "reference": s.reference,
            "component_id": s.component_id,
            "component_name": s.component.name if s.component else None,
            "category": s.category,
            "description": s.description,
            "inherent_severity": s.inherent_severity,
            "status": s.status,
            "requires_promotion": s.requires_promotion,
            "is_resolved": s.is_resolved,
            "carried_by_register": s.carried_by_register,
            "has_partial_mitigation": s.has_partial_mitigation,
            "fully_mitigated": s.fully_mitigated,
            "remediation_target_date": s.remediation_target_date,
            "acceptance_expiry": s.acceptance_expiry,
            "acceptance_rationale": s.acceptance_rationale,
            "promoted_risk_id": s.promoted_risk_id,
            "reopened_reason": s.reopened_reason,
            "reopened_at": s.reopened_at,
            "status_rationale": s.status_rationale,
            "component_classification": (
                s.component.data_classification if s.component else None
            ),
            "component_trust_zone": s.component.trust_zone if s.component else None,
            "component_sensitive": s.component.is_sensitive if s.component else False,
            "comments": [
                {
                    "id": c.id,
                    "body": c.body,
                    "parent_comment_id": c.parent_comment_id,
                    "created_by": c.created_by,
                    "created_at": c.created_at,
                }
                for c in s.comments
            ],
            "evidence": [
                {
                    "id": e.id,
                    "title": e.title,
                    "evidence_ref": e.evidence_ref,
                    "evidence_type": e.evidence_type,
                    "notes": e.notes,
                    "supports": e.supports,
                    "supersedes_id": e.supersedes_id,
                    "created_by": e.created_by,
                    "created_at": e.created_at,
                }
                for e in s.evidence
            ],
            "risk_links": [
                {
                    "link_id": rl.id,
                    "risk_id": rl.risk_id,
                    "reference": rl.risk.reference if rl.risk else None,
                    "title": rl.risk.title if rl.risk else None,
                    "reported_rating": rl.risk.reported_rating if rl.risk else None,
                    "lifecycle_state": rl.risk.lifecycle_state if rl.risk else None,
                    "residual_score_locked": (
                        rl.risk.residual_score_locked if rl.risk else None
                    ),
                    "link_type": rl.link_type,
                    "rationale": rl.rationale,
                }
                for rl in s.risk_links
            ],
            "mitigations": [
                {
                    "link_id": m.id,
                    "deployment_id": m.deployment_id,
                    "deployment_reference": m.deployment.reference if m.deployment else None,
                    "deployment_status": (
                        m.deployment.deployment_status if m.deployment else None
                    ),
                    "asset": (
                        m.deployment.surface.name
                        if m.deployment and m.deployment.surface
                        else None
                    ),
                    "effectiveness_assurance": m.effectiveness_assurance,
                    "live": (
                        m.deployment is not None
                        and m.deployment.deployment_status in ("Active", "Degraded")
                    ),
                }
                for m in s.mitigations
            ],
            "invariants": self.invariant_report(s, "threat_scenario"),
        }


def summarise_model(tm: ThreatModel) -> dict[str, Any]:
    scenarios = tm.scenarios
    return {
        "id": tm.id,
        "reference": tm.reference,
        "title": tm.title,
        "attack_surface_id": tm.attack_surface_id,
        "asset_name": tm.surface.name if tm.surface else None,
        "lifecycle_state": tm.lifecycle_state,
        "methodology": tm.methodology,
        "system_owner_id": tm.system_owner_id,
        "appsec_partner_id": tm.appsec_partner_id,
        "appsec_signoff_by": tm.appsec_signoff_by,
        "appsec_signoff_at": tm.appsec_signoff_at,
        "owner_signoff_by": tm.owner_signoff_by,
        "owner_signoff_at": tm.owner_signoff_at,
        "fully_signed_off": tm.fully_signed_off,
        "component_count": len(tm.components),
        "scenario_count": len(scenarios),
        "unresolved_count": len(tm.unresolved_scenarios),
        "mitigated_count": sum(1 for s in scenarios if s.status == "Mitigated"),
        "promoted_count": sum(1 for s in scenarios if s.status == "Promoted_To_Risk"),
        "accepted_count": sum(1 for s in scenarios if s.status == "Accepted"),
        "risk_linked_count": sum(1 for s in scenarios if s.risk_links),
        "sensitive_components": sum(1 for c in tm.components if c.is_sensitive),
        "unanalysed_sensitive": sum(
            1
            for c in tm.components
            if c.is_sensitive and not any(s.component_id == c.id for s in scenarios)
        ),
        "created_at": tm.created_at,
        "updated_at": tm.updated_at,
    }
