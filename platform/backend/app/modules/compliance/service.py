"""Compliance service.

The interesting method is `posture`, because it is where the module either earns
its place or becomes a spreadsheet. It reports coverage derived from the live
control estate rather than from what somebody once ticked, which means the
number moves when a deployment fails and moves back when it recovers, without
anybody revisiting the Statement of Applicability.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.core.errors import Conflict, NotFound
from app.core.governance import governance
from app.core.model_base import utcnow
from app.core.service import LifecycleService
from app.engine import AuditTrail
from app.modules.compliance.machine import REQUIREMENT_ASSESSMENT_MACHINE
from app.modules.compliance.models import (
    ComplianceFramework,
    ComplianceRequirement,
    ControlRequirementLink,
    RequirementAssessment,
)
from app.modules.control.models import AttackSurface, ControlObjective


class ComplianceService(LifecycleService[RequirementAssessment]):
    model = RequirementAssessment
    machine = REQUIREMENT_ASSESSMENT_MACHINE
    entity_name = "requirement_assessment"

    # -- frameworks -------------------------------------------------------

    def frameworks(self) -> list[ComplianceFramework]:
        return list(
            self.session.execute(
                select(ComplianceFramework).order_by(ComplianceFramework.name)
            ).scalars()
        )

    def framework(self, framework_id: str) -> ComplianceFramework:
        f = self.session.get(ComplianceFramework, framework_id)
        if f is None:
            f = self.session.execute(
                select(ComplianceFramework).where(
                    ComplianceFramework.framework_id == framework_id
                )
            ).scalar_one_or_none()
        if f is None:
            raise NotFound("framework " + framework_id + " not found")
        return f

    def set_adoption(self, framework_id: str, adopted: bool) -> ComplianceFramework:
        f = self.framework(framework_id)
        before = f.adopted
        f.adopted = adopted
        f.adopted_at = utcnow() if adopted else None
        self.session.flush()
        self.enforce(f, entity_name="compliance_framework")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="compliance_framework",
            entity_id=f.id,
            action="ADOPT" if adopted else "UNADOPT",
            changed_fields={"adopted": {"from": before, "to": adopted}},
        )
        self.session.commit()
        return f

    # -- requirements -----------------------------------------------------

    def requirements(self, framework_id: str) -> list[ComplianceRequirement]:
        f = self.framework(framework_id)
        return sorted(f.requirements, key=lambda r: (r.sort_order, r.ref))

    def assessment_for(self, requirement_id: str) -> RequirementAssessment:
        """Every requirement has exactly one position, created lazily.

        Not_Assessed is a real state rather than a missing row, because "we have
        not looked at this" is itself a finding and should be countable.
        """
        requirement = self.session.get(ComplianceRequirement, requirement_id)
        if requirement is None:
            raise NotFound("requirement " + requirement_id + " not found")
        if requirement.assessment is None:
            assessment = RequirementAssessment(requirement_id=requirement.id)
            self.session.add(assessment)
            self.session.flush()
            self.session.refresh(requirement)
        return requirement.assessment

    def assess(self, requirement_id: str, target: str, **payload: Any) -> dict[str, Any]:
        assessment = self.assessment_for(requirement_id)
        # Carry the decision onto the record before the gate reads it, so the
        # rationale a precondition demands is the one that gets stored.
        for field in ("rationale", "owner_id", "compensating_expiry"):
            if payload.get(field) is not None:
                setattr(assessment, field, payload[field])
        if target != "Gap":
            assessment.gap_reason = None
        assessment.assessed_by = self.actor_id
        assessment.assessed_at = utcnow()
        self.session.flush()
        return self.transition(assessment, target, **payload)

    # -- coverage assertions ----------------------------------------------

    def link_control(
        self,
        requirement_id: str,
        objective_id: str,
        coverage_level: str = "Full",
        rationale: str | None = None,
    ) -> ControlRequirementLink:
        requirement = self.session.get(ComplianceRequirement, requirement_id)
        if requirement is None:
            raise NotFound("requirement " + requirement_id + " not found")
        objective = self.session.get(ControlObjective, objective_id)
        if objective is None:
            raise NotFound("control objective " + objective_id + " not found")
        if coverage_level not in governance.coverage_levels:
            raise Conflict(
                str(coverage_level)
                + " is not a configured coverage level. Configured levels are: "
                + ", ".join(governance.coverage_levels)
                + ". Add it to config/governance.yml and restart the API.",
                detail={"allowed": list(governance.coverage_levels)},
            )

        existing = next(
            (link for link in requirement.control_links if link.objective_id == objective_id),
            None,
        )
        if existing is not None:
            raise Conflict(
                objective.reference
                + " is already linked to "
                + requirement.ref
                + " at coverage level "
                + existing.coverage_level
                + ". Change the level rather than adding a second assertion."
            )

        link = ControlRequirementLink(
            requirement_id=requirement.id,
            objective_id=objective_id,
            coverage_level=coverage_level,
            rationale=rationale,
            asserted_by=self.actor_id,
        )
        self.session.add(link)
        self.session.flush()
        self.enforce(link, entity_name="control_requirement_link")

        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="control_requirement_link",
            entity_id=link.id,
            action="LINK",
            changed_fields={
                "requirement": requirement.ref,
                "control": objective.reference,
                "coverage_level": coverage_level,
            },
        )
        self._revalidate(requirement)
        self.session.commit()
        return link

    def set_coverage_level(self, link_id: str, coverage_level: str) -> ControlRequirementLink:
        link = self.session.get(ControlRequirementLink, link_id)
        if link is None:
            raise NotFound("link " + link_id + " not found")
        if coverage_level not in governance.coverage_levels:
            raise Conflict(
                str(coverage_level) + " is not a configured coverage level",
                detail={"allowed": list(governance.coverage_levels)},
            )
        before = link.coverage_level
        link.coverage_level = coverage_level
        self.session.flush()
        self.enforce(link, entity_name="control_requirement_link")
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="control_requirement_link",
            entity_id=link.id,
            action="UPDATE",
            changed_fields={"coverage_level": {"from": before, "to": coverage_level}},
        )
        # Downgrading the last satisfying link must re-open the requirement
        # rather than leave a Covered position resting on nothing (AINV-3).
        self._revalidate(link.requirement)
        self.session.commit()
        return link

    def unlink_control(self, link_id: str) -> None:
        link = self.session.get(ControlRequirementLink, link_id)
        if link is None:
            raise NotFound("link " + link_id + " not found")
        requirement = link.requirement
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="control_requirement_link",
            entity_id=link.id,
            action="UNLINK",
            changed_fields={"requirement": requirement.ref, "removed": True},
        )
        self.session.delete(link)
        self.session.flush()
        self.session.refresh(requirement)
        self._revalidate(requirement)
        self.session.commit()

    def _revalidate(self, requirement: ComplianceRequirement) -> None:
        """Re-open a Covered requirement whose coverage no longer holds.

        This is the same shape as the threat module's re-open on control
        failure: the position is not a note somebody typed, it is a claim about
        the current estate, and a claim that has stopped being true is corrected
        rather than preserved.
        """
        assessment = requirement.assessment
        if assessment is None or assessment.lifecycle_state != "Covered":
            return
        if requirement.satisfying_links:
            return
        assessment.gap_reason = (
            "The last satisfying coverage assertion was removed or downgraded to a "
            "level that does not satisfy (AINV-3)."
        )
        self.transition(assessment, "Gap", system=True, reason=assessment.gap_reason)

    # -- scope ------------------------------------------------------------

    def set_asset_scopes(self, asset_id: str, scopes: list[str]) -> AttackSurface:
        """Declare which compliance regimes an asset sits inside.

        AINV-2 reads this to decide where a control must be deployed for a
        requirement to count as covered, and AINV-9 refuses to report coverage
        for a framework no asset has claimed. Getting this wrong is how a
        compliance tool reports a confident number over an empty set.
        """
        asset = self.session.get(AttackSurface, asset_id)
        if asset is None:
            raise NotFound("asset " + asset_id + " not found")

        known = {f.framework_id for f in self.frameworks()}
        unknown = [s for s in scopes if s not in known]
        if unknown:
            raise Conflict(
                "no framework loaded with id: " + ", ".join(unknown)
                + ". Loaded frameworks are: " + ", ".join(sorted(known)) + ".",
                detail={"unknown": unknown, "known": sorted(known)},
            )

        before = list(asset.compliance_scopes or [])
        asset.compliance_scopes = list(scopes)
        self.session.flush()
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="attack_surface",
            entity_id=asset.id,
            action="SCOPE",
            changed_fields={"compliance_scopes": {"from": before, "to": list(scopes)}},
        )
        self.session.commit()
        return asset

    # -- posture ----------------------------------------------------------

    def posture(self, framework_id: str | None = None) -> dict[str, Any]:
        """Coverage derived from the live estate, not from what was once ticked."""
        frameworks = (
            [self.framework(framework_id)] if framework_id else
            [f for f in self.frameworks() if f.adopted]
        )

        out: list[dict[str, Any]] = []
        for f in frameworks:
            counts = dict.fromkeys(
                ("Not_Assessed", "Not_Applicable", "Applicable", "Covered", "Compensating", "Gap"),
                0,
            )
            for requirement in f.requirements:
                state = (
                    requirement.assessment.lifecycle_state
                    if requirement.assessment
                    else "Not_Assessed"
                )
                counts[state] = counts.get(state, 0) + 1

            in_scope = sum(
                v for k, v in counts.items() if k not in ("Not_Assessed", "Not_Applicable")
            )
            satisfied = counts["Covered"] + counts["Compensating"]
            scoped_assets = [
                a
                for a in self.session.execute(select(AttackSurface)).scalars()
                if f.framework_id in (a.compliance_scopes or [])
            ]

            out.append(
                {
                    "framework_id": f.framework_id,
                    "name": f.name,
                    "version": f.version,
                    "adopted": f.adopted,
                    "redistributable": f.redistributable,
                    "requirements": f.requirement_count,
                    "counts": counts,
                    "in_scope": in_scope,
                    "satisfied": satisfied,
                    # Deliberately null rather than 100% when nothing is in
                    # scope: a percentage over an empty set is the most
                    # misleading number a compliance tool can print (AINV-9).
                    "coverage_pct": round(100 * satisfied / in_scope) if in_scope else None,
                    "scoped_assets": [{"id": a.id, "name": a.name} for a in scoped_assets],
                    "scope_declared": bool(scoped_assets),
                }
            )
        return {"frameworks": out}

    def asset_coverage(self, requirement: ComplianceRequirement) -> dict[str, Any]:
        """Which in-scope assets this requirement's controls actually reach.

        AINV-2 asks whether a satisfying control runs anywhere inside scope,
        because demanding it run everywhere would make the register unusable and
        push people to stop declaring scope at all. The stricter question is
        still worth answering, so it is answered here: informative, attached to
        the requirement, and impossible to mistake for a blocking rule.

        A requirement covered on one of four in-scope assets is genuinely
        covered and genuinely incomplete, and an assessor should see both.
        """
        framework_id = requirement.framework.framework_id
        scoped = [
            a
            for a in self.session.execute(select(AttackSurface)).scalars()
            if framework_id in (a.compliance_scopes or [])
        ]
        live = governance.live_deployment_statuses
        reached: set[str] = set()
        for link in requirement.satisfying_links:
            objective = link.objective
            if objective is None or objective.lifecycle_state != "Operating":
                continue
            for activity in objective.activities:
                for deployment in activity.deployments:
                    if deployment.deployment_status in live:
                        reached.add(deployment.attack_surface_id)

        covered = [a for a in scoped if a.id in reached]
        uncovered = [a for a in scoped if a.id not in reached]
        return {
            "in_scope": len(scoped),
            "covered": len(covered),
            "uncovered_assets": [{"id": a.id, "name": a.name} for a in uncovered],
            "complete": bool(scoped) and not uncovered,
        }

    def gaps(self, framework_id: str | None = None) -> list[dict[str, Any]]:
        """Every requirement in scope and not satisfied, with why."""
        frameworks = (
            [self.framework(framework_id)] if framework_id else
            [f for f in self.frameworks() if f.adopted]
        )
        rows: list[dict[str, Any]] = []
        for f in frameworks:
            for requirement in sorted(f.requirements, key=lambda r: (r.sort_order, r.ref)):
                assessment = requirement.assessment
                state = assessment.lifecycle_state if assessment else "Not_Assessed"
                if state in ("Not_Applicable", "Covered"):
                    continue
                partial = [
                    link.objective.reference
                    for link in requirement.control_links
                    if not link.satisfies and link.objective is not None
                ]
                rows.append(
                    {
                        "framework_id": f.framework_id,
                        "ref": requirement.ref,
                        "title": requirement.title,
                        "category": requirement.category,
                        "state": state,
                        "gap_reason": assessment.gap_reason if assessment else None,
                        "compensating_expiry": (
                            assessment.compensating_expiry.isoformat()
                            if assessment and assessment.compensating_expiry
                            else None
                        ),
                        "partial_controls": partial,
                        "asset_coverage": self.asset_coverage(requirement),
                        "linked_controls": [
                            link.objective.reference
                            for link in requirement.control_links
                            if link.objective is not None
                        ],
                    }
                )
        return rows

    def requirements_for_control(self, objective_id: str) -> list[dict[str, Any]]:
        """The other direction: what does this control carry?

        Worth having on the control page, because it is the question that stops
        somebody deprecating a control that is holding up an audit.
        """
        links = list(
            self.session.execute(
                select(ControlRequirementLink).where(
                    ControlRequirementLink.objective_id == objective_id
                )
            ).scalars()
        )
        rows = []
        for link in links:
            requirement = link.requirement
            rows.append(
                {
                    "link_id": link.id,
                    "framework_id": requirement.framework.framework_id,
                    "ref": requirement.ref,
                    "title": requirement.title,
                    "coverage_level": link.coverage_level,
                    "satisfies": link.satisfies,
                    "state": (
                        requirement.assessment.lifecycle_state
                        if requirement.assessment
                        else "Not_Assessed"
                    ),
                }
            )
        return rows

    def expiring_compensations(self, within_days: int | None = None) -> list[RequirementAssessment]:
        horizon = date.today() + timedelta(
            days=within_days
            if within_days is not None
            else governance.compensating_warning_days
        )
        return [
            a
            for a in self.session.execute(select(RequirementAssessment)).scalars()
            if a.lifecycle_state == "Compensating"
            and a.compensating_expiry
            and a.compensating_expiry <= horizon
        ]
