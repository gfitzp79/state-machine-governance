"""Environmental context for threat modelling.

Threat modelling is not performed in isolation. When a model is scoped to an
asset, the platform already knows what controls are deployed there, how
effective they are, which risks depend on them, and what residual exposure has
been accepted. Withholding that from the modeller wastes it.

    THE GOVERNING CONSTRAINT

    Context is INFORMATIVE, never determinative.

    Nothing in this module writes to a threat scenario. It cannot mitigate, it
    cannot downgrade a severity, it cannot mark anything covered. Threats are
    identified against the architecture AS DESIGNED, not as currently defended.

    This is the threat-modelling analogue of LKH-3, which scores inherent
    likelihood with no control adjustment. The reasoning is identical: a
    well-controlled system that is modelled against its controls looks
    threat-free, and the moment a control fails there is no record that the
    threat ever existed. Identify the threat, then assess what covers it, and
    keep the two separable so the first survives the second.

    Coverage is therefore reported alongside scenarios, never folded into them.
    Linking a control to a scenario stays a deliberate assertion by a person
    (TINV-7).

What this module is for is the inverse: making control GAPS visible. A component
carrying Restricted data in a DMZ with no operating control covering it is the
thing a threat model should be loudest about, and it is precisely what a
scenario list alone will not tell you.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.governance import CE_RATING_NAMES, governance
from app.engine.scoring import CE_STRENGTH, ScoringEngine
from app.modules.control.models import (
    AttackSurface,
    ControlDeployment,
    ControlObjective,
)
from app.modules.risk.models import Risk, RiskControlLink
from app.modules.threat.models import ThreatComponent, ThreatModel

# A deployment at or below this CE is reported as a gap rather than as coverage.
WEAK_CE_RANK = CE_STRENGTH.get(governance.weak_coverage_at_or_below, 0)


class CoverageFinding:
    """One control deployment considered against one component."""

    __slots__ = ("deployment", "objective", "status", "reason")

    def __init__(self, deployment: Any, objective: Any, status: str, reason: str) -> None:
        self.deployment = deployment
        self.objective = objective
        self.status = status  # effective | weak | absent
        self.reason = reason

    def as_dict(self) -> dict[str, Any]:
        dep = self.deployment
        obj = self.objective
        return {
            "deployment_id": dep.id,
            "deployment_reference": dep.reference,
            "deployment_status": dep.deployment_status,
            "objective_id": obj.id if obj else None,
            "objective_reference": obj.reference if obj else None,
            "objective_title": obj.title if obj else None,
            "objective_state": obj.lifecycle_state if obj else None,
            "family": obj.family if obj else None,
            "ce_rating": dep.ce_rating,
            "ce_expired": ScoringEngine.ce_expired(dep.ce_assessed_at, dep.test_frequency),
            "ce_assessed_at": dep.ce_assessed_at,
            "asset": dep.surface.name if dep.surface else None,
            "status": self.status,
            "reason": self.reason,
        }


class ThreatContext:
    """Assembles the read-only picture of the environment a model sits in."""

    # -- coverage ---------------------------------------------------------

    @staticmethod
    def _deployments_on_asset(session: Session, asset_id: str) -> list[ControlDeployment]:
        if not asset_id:
            return []
        return list(
            session.execute(
                select(ControlDeployment).where(
                    ControlDeployment.attack_surface_id == asset_id
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _classify(deployment: ControlDeployment) -> CoverageFinding:
        """Rate one deployment as effective, weak, or absent coverage.

        The same filters the scoring engine applies to control effectiveness
        (CE-5, CE-6, CINV-1) apply here, so the coverage panel and the residual
        score never disagree about whether a control counts.
        """
        activity = deployment.activity
        objective = activity.objective if activity else None

        if objective is None:
            return CoverageFinding(deployment, None, "absent", "deployment has no parent objective")

        if objective.lifecycle_state != "Operating":
            return CoverageFinding(
                deployment,
                objective,
                "absent",
                "CE-5: objective is " + objective.lifecycle_state + ", not Operating, so it "
                "contributes nothing to scoring and should not be assumed to cover anything",
            )

        if deployment.deployment_status not in ("Active", "Degraded"):
            return CoverageFinding(
                deployment,
                objective,
                "absent",
                "deployment is " + deployment.deployment_status + ", so it is not running here",
            )

        if ScoringEngine.ce_expired(deployment.ce_assessed_at, deployment.test_frequency):
            return CoverageFinding(
                deployment,
                objective,
                "weak",
                "CE-6: effectiveness evidence has expired, so the control is operating "
                "without current assurance",
            )

        if not deployment.ce_evidence_ref:
            return CoverageFinding(
                deployment, objective, "weak", "CINV-1: no effectiveness evidence recorded"
            )

        if CE_STRENGTH.get(deployment.ce_rating, 0) <= WEAK_CE_RANK:
            return CoverageFinding(
                deployment,
                objective,
                "weak",
                "effectiveness is " + deployment.ce_rating + ", at or below the configured "
                "weak-coverage threshold",
            )

        if deployment.deployment_status == "Degraded":
            return CoverageFinding(
                deployment, objective, "weak", "deployment is Degraded"
            )

        return CoverageFinding(deployment, objective, "effective", "")

    @classmethod
    def coverage_for_component(
        cls, session: Session, component: ThreatComponent, default_asset_id: str
    ) -> dict[str, Any]:
        """Control coverage on the asset this component sits on.

        Coverage is asset-scoped because that is the granularity at which
        controls are actually deployed. A control on the asset is *candidate*
        coverage for every component on it; whether it genuinely addresses a
        given threat is the modeller's call, which is why nothing here links
        anything.
        """
        asset_id = component.attack_surface_id or default_asset_id
        findings = [cls._classify(d) for d in cls._deployments_on_asset(session, asset_id)]

        effective = [f for f in findings if f.status == "effective"]
        weak = [f for f in findings if f.status == "weak"]
        absent = [f for f in findings if f.status == "absent"]

        # Which STRIDE categories the effective controls plausibly speak to. A
        # hint for ordering the panel, never a claim of mitigation.
        families = {f.objective.family for f in effective if f.objective}
        addressed: list[str] = []
        for category, relevant in governance.stride_control_families.items():
            if families.intersection(relevant):
                addressed.append(category)

        return {
            "asset_id": asset_id,
            "effective": [f.as_dict() for f in effective],
            "weak": [f.as_dict() for f in weak],
            "absent": [f.as_dict() for f in absent],
            "effective_count": len(effective),
            "weak_count": len(weak),
            "families_present": sorted(families),
            "stride_categories_with_some_control": sorted(addressed),
            "stride_categories_without_control": sorted(
                set(governance.stride_control_families) - set(addressed)
            ),
        }

    # -- risk posture -----------------------------------------------------

    @classmethod
    def risk_posture(cls, session: Session, asset_id: str) -> dict[str, Any]:
        """Risks that depend on controls deployed on this asset.

        This is the 'what has already been accepted here' view. A modeller who
        can see that RISK-003 already carries this exposure at Critical, with a
        locked residual, is modelling with the register rather than beside it.
        """
        deployments = cls._deployments_on_asset(session, asset_id)
        objective_ids = {
            d.activity.objective_id for d in deployments if d.activity is not None
        }
        if not objective_ids:
            return {"risks": [], "above_appetite": 0, "residual_locked": 0, "accepted": 0}

        links = list(
            session.execute(
                select(RiskControlLink).where(
                    RiskControlLink.objective_id.in_(objective_ids)
                )
            )
            .scalars()
            .all()
        )
        if not links:
            return {"risks": [], "above_appetite": 0, "residual_locked": 0, "accepted": 0}

        risks = list(
            session.execute(
                select(Risk)
                .where(Risk.id.in_({link.risk_id for link in links}))
                .where(Risk.lifecycle_state != "Closed")
            )
            .scalars()
            .all()
        )

        rows = [
            {
                "id": r.id,
                "reference": r.reference,
                "title": r.title,
                "lifecycle_state": r.lifecycle_state,
                "inherent_rating": r.inherent_rating,
                "residual_rating": r.residual_rating,
                "reported_score": r.reported_score,
                "reported_rating": r.reported_rating,
                "appetite": (
                    ScoringEngine.appetite_for(r.reported_rating) if r.reported_rating else None
                ),
                "residual_score_locked": r.residual_score_locked,
                "treatment_strategy": r.treatment_strategy,
                "acceptance_expiry_date": r.acceptance_expiry_date,
                "control_change_flag": r.control_change_flag,
            }
            for r in risks
        ]
        rows.sort(key=lambda r: -(r["reported_score"] or 0))

        return {
            "risks": rows,
            "above_appetite": sum(
                1 for r in rows if ScoringEngine.is_above_appetite(r["reported_rating"])
            ),
            "residual_locked": sum(1 for r in rows if r["residual_score_locked"]),
            "accepted": sum(1 for r in rows if r["treatment_strategy"] == "Accept"),
        }

    # -- gaps -------------------------------------------------------------

    @classmethod
    def gaps(cls, session: Session, model: ThreatModel) -> list[dict[str, Any]]:
        """Where the environment does not cover what the decomposition exposes.

        This is the output that justifies showing context at all. A gap is an
        observation for the modeller, not a blocker, with two exceptions that the
        Review gate enforces: TINV-9 and TINV-11.
        """
        findings: list[dict[str, Any]] = []
        weak_by_asset: dict[str, int] = {}
        scenarios_by_component: dict[str, int] = {}
        for scenario in model.scenarios:
            scenarios_by_component[scenario.component_id] = (
                scenarios_by_component.get(scenario.component_id, 0) + 1
            )

        for component in model.components:
            coverage = cls.coverage_for_component(session, component, model.attack_surface_id)
            sensitive = component.is_sensitive
            trust = component.trust_level
            scenario_count = scenarios_by_component.get(component.id, 0)

            if sensitive and coverage["effective_count"] == 0:
                findings.append(
                    {
                        "severity": "high",
                        "component_id": component.id,
                        "component": component.name,
                        "kind": "uncovered_sensitive_component",
                        "detail": component.name + " handles "
                        + str(component.data_classification)
                        + " data and has no control operating on its asset with current "
                        "effectiveness evidence.",
                    }
                )

            if sensitive and trust is not None and trust <= 1:
                findings.append(
                    {
                        "severity": "high",
                        "component_id": component.id,
                        "component": component.name,
                        "kind": "sensitive_data_in_low_trust_zone",
                        "detail": component.name + " carries "
                        + str(component.data_classification)
                        + " data in the "
                        + str(component.trust_zone).replace("_", " ")
                        + " zone.",
                    }
                )

            if sensitive and scenario_count == 0:
                findings.append(
                    {
                        "severity": "blocking",
                        "component_id": component.id,
                        "component": component.name,
                        "kind": "sensitive_component_unanalysed",
                        "detail": "TINV-11: " + component.name + " handles "
                        + str(component.data_classification)
                        + " data but carries no threat scenario. You decomposed it, so "
                        "it needs to have been thought about.",
                    }
                )

            if component.is_sensitive and not component.trust_zone:
                findings.append(
                    {
                        "severity": "blocking",
                        "component_id": component.id,
                        "component": component.name,
                        "kind": "sensitive_component_unzoned",
                        "detail": "TINV-9: " + component.name + " handles "
                        + str(component.data_classification)
                        + " data and must declare a trust zone.",
                    }
                )

            weak_by_asset.setdefault(
                coverage["asset_id"], coverage["weak_count"]
            )

        # Weak coverage is a property of an asset, not of each component sitting
        # on it. Reporting it per component turns one finding into five and
        # buries the ones that are actually per component.
        for asset_id, weak_count in weak_by_asset.items():
            if weak_count <= 0:
                continue
            asset = session.get(AttackSurface, asset_id) if asset_id else None
            findings.append(
                {
                    "severity": "medium",
                    "component_id": None,
                    "component": asset.name if asset else "this asset",
                    "kind": "weak_coverage",
                    "detail": str(weak_count)
                    + " control deployment(s) on "
                    + (asset.name if asset else "this asset")
                    + " are operating without current or sufficient effectiveness "
                    "evidence, so they should not be assumed to cover anything here.",
                }
            )

        return findings

    # -- assembly ---------------------------------------------------------

    @classmethod
    def for_model(cls, session: Session, model: ThreatModel) -> dict[str, Any]:
        if not governance.show_environmental_context:
            return {"enabled": False}

        asset_id = model.attack_surface_id
        deployments = cls._deployments_on_asset(session, asset_id)
        findings = [cls._classify(d) for d in deployments]
        gaps = cls.gaps(session, model)

        return {
            "enabled": True,
            "informative_only": True,
            "notice": (
                "Control and risk posture is shown to reveal gaps, not to resolve "
                "scenarios. Threats are identified against the architecture as "
                "designed; nothing here mitigates anything (TINV-7)."
            ),
            "asset": {
                "id": asset_id,
                "name": model.surface.name if model.surface else None,
                "tier": model.surface.tier if model.surface else None,
            },
            "control_posture": {
                "total_deployments": len(findings),
                "effective": sum(1 for f in findings if f.status == "effective"),
                "weak": sum(1 for f in findings if f.status == "weak"),
                "absent": sum(1 for f in findings if f.status == "absent"),
                "deployments": [f.as_dict() for f in findings],
            },
            "risk_posture": cls.risk_posture(session, asset_id),
            "gaps": gaps,
            "blocking_gaps": [g for g in gaps if g["severity"] == "blocking"],
            "component_coverage": {
                c.id: cls.coverage_for_component(session, c, asset_id)
                for c in model.components
            },
        }
