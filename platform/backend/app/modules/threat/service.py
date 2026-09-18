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
from app.engine import AuditTrail
from app.modules.control.models import ControlDeployment
from app.modules.threat.machine import THREAT_MODEL_MACHINE
from app.modules.threat.models import (
    SEVERITY_ORDER,
    ThreatComponent,
    ThreatMitigationLink,
    ThreatModel,
    ThreatScenario,
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

    def add_component(self, tm: ThreatModel, data: dict[str, Any]) -> ThreatComponent:
        component = ThreatComponent(threat_model_id=tm.id, **data)
        self.session.add(component)
        self.session.commit()
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
        if assurance == "Fully_Mitigated":
            scenario.status = "Mitigated"
            scenario.reopened_reason = None
        self.session.flush()
        self.enforce(scenario, "threat_scenario")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="threat_scenario",
            entity_id=scenario.id,
            action="MITIGATION_LINKED",
            changed_fields={"deployment": deployment.reference, "assurance": assurance},
        )
        self.session.commit()
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
                "risk_owner_id": data.get("risk_owner_id"),
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

    def detail(self, tm: ThreatModel) -> dict[str, Any]:
        return {
            **summarise_model(tm),
            "description": tm.description,
            "signoff_stripped_reason": tm.signoff_stripped_reason,
            "components": [
                {
                    "id": c.id,
                    "name": c.name,
                    "component_type": c.component_type,
                    "description": c.description,
                    "scenario_count": sum(1 for s in tm.scenarios if s.component_id == c.id),
                }
                for c in tm.components
            ],
            "scenarios": [self.scenario_detail(s) for s in tm.scenarios],
            "gates": self.gate_report(tm),
            "invariants": self.invariant_report(tm),
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
            "remediation_target_date": s.remediation_target_date,
            "acceptance_expiry": s.acceptance_expiry,
            "acceptance_rationale": s.acceptance_rationale,
            "promoted_risk_id": s.promoted_risk_id,
            "reopened_reason": s.reopened_reason,
            "reopened_at": s.reopened_at,
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
        "created_at": tm.created_at,
        "updated_at": tm.updated_at,
    }
