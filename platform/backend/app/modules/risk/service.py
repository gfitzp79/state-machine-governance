"""Risk service.

The scoring methods are the interesting part. `score_inherent` and
`score_residual` are the only ways a score can be written, and both refuse the
write when the state machine says the fields are not open.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.errors import Conflict, DomainError, NotFound
from app.core.governance import governance
from app.core.service import LifecycleService
from app.engine import AuditTrail
from app.engine.scoring import ScoringEngine
from app.modules.control.models import ControlObjective
from app.modules.risk.machine import RISK_MACHINE
from app.modules.risk.models import (
    PHASE_NUMBERS,
    Risk,
    RiskComment,
    RiskControlLink,
    RiskPhaseHistory,
    RiskPolicyLink,
    RiskTreatmentLink,
)
from app.modules.treatment.models import Treatment


class RiskService(LifecycleService[Risk]):
    model = Risk
    machine = RISK_MACHINE
    entity_name = "risk"
    reference_prefix = "RISK"
    taxonomy = {"tier": "risk_tiers", "intake_source": "intake_sources"}

    # -- creation ---------------------------------------------------------

    def create_risk(self, data: dict[str, Any]) -> Risk:
        risk = Risk(
            reference=self.next_reference(),
            title=data["title"],
            cause=data.get("cause"),
            threat_event=data.get("threat_event"),
            vulnerability=data.get("vulnerability"),
            impact_statement=data.get("impact_statement"),
            intake_source=data.get("intake_source"),
            identified_by=data.get("identified_by"),
            tier=data.get("tier"),
            tier_rationale=data.get("tier_rationale"),
            risk_owner_id=data.get("risk_owner_id"),
            risk_stakeholder_id=data.get("risk_stakeholder_id"),
            risk_analyst_id=data.get("risk_analyst_id"),
            created_by=self.actor_id,
        )
        self.create(risk)
        self._record_history(risk, None, "Intake", "CREATE", {})
        self.session.commit()
        return risk

    # -- scoring ----------------------------------------------------------

    def score_inherent(self, risk: Risk, impact: int, likelihood: int, **fields: Any) -> Risk:
        """RINV-8: refused before the preconditions gate has passed.
        OUT-5: refused once the risk has left Phase 3."""
        if risk.phase_number < PHASE_NUMBERS["Scoring"]:
            raise Conflict(
                "RINV-8: scoring cannot begin until the Phase 2 preconditions gate has passed"
            )
        if risk.inherent_locked:
            raise Conflict(
                "OUT-5: the inherent score is frozen for this assessment cycle. "
                "Start a re-assessment to score again."
            )

        score = ScoringEngine.inherent(impact, likelihood)
        if score is None:
            raise Conflict("impact and likelihood are both required")

        changes: dict[str, Any] = {
            "impact": score.impact,
            "likelihood": score.likelihood,
            "inherent_risk_score": score.score,
            "inherent_rating": score.rating,
        }
        for key in ("impact_justification", "likelihood_justification"):
            if key in fields:
                changes[key] = fields[key]

        # While residual is locked, it tracks inherent (RES-1 / RINV-1).
        if risk.residual_score_locked:
            changes["residual_impact"] = None
            changes["residual_likelihood"] = None
            changes["residual_risk_score"] = None
            changes["residual_rating"] = None

        self.apply(risk, changes, action="SCORE_INHERENT")
        self.session.commit()
        return risk

    def score_residual(self, risk: Risk, impact: int, likelihood: int, **fields: Any) -> Risk:
        """RINV-1: refused while the residual lock is on. The lock is released only
        by the Phase 6 gate, and re-applied by any control cascade."""
        if risk.residual_score_locked:
            raise Conflict(
                "RINV-1: residual scores are locked. All five conditions of "
                "GATE_RESIDUAL_VALIDATED must be satisfied before residual becomes editable.",
                detail=risk.residual_gate_conditions,
            )
        if risk.likelihood is None:
            raise Conflict("score the inherent risk before scoring residual")

        resolution = self.resolve_ce(risk)
        ok, reason = ScoringEngine.validate_residual_likelihood(
            risk.likelihood, likelihood, resolution
        )
        if not ok:
            raise Conflict(reason, detail=resolution.as_dict())

        score = ScoringEngine.residual(impact, likelihood)
        if score is None:
            raise Conflict("residual impact and likelihood are both required")

        changes: dict[str, Any] = {
            "residual_impact": score.impact,
            "residual_likelihood": score.likelihood,
            "residual_risk_score": score.score,
            "residual_rating": score.rating,
            "next_review_date": ScoringEngine.next_review_date(score.rating),
        }
        for key in ("residual_impact_rationale", "residual_likelihood_rationale"):
            if key in fields:
                changes[key] = fields[key]

        self.apply(risk, changes, action="SCORE_RESIDUAL")
        self.session.commit()
        return risk

    def resolve_ce(self, risk: Risk):
        """Traceable CE resolution across every linked control."""
        objectives = [link.objective for link in risk.control_links if link.objective]
        return ScoringEngine.resolve_ce(objectives)

    # -- treatment decision -----------------------------------------------

    def set_treatment_decision(self, risk: Risk, data: dict[str, Any]) -> Risk:
        strategy = data.get("treatment_strategy")
        rating = risk.inherent_rating

        if strategy == "Accept":
            # RINV-5 and the acceptance window rules, refused before the write.
            if not ScoringEngine.acceptance_permitted(rating):
                raise Conflict(
                    "RINV-5: a " + str(rating) + " risk cannot be accepted. "
                    "Select Mitigate, Transfer or Avoid.",
                    detail={"rating": rating},
                )
            expiry = data.get("acceptance_expiry_date")
            if not expiry:
                raise Conflict("RINV-4: acceptance requires an expiry date")
            if isinstance(expiry, str):
                expiry = date.fromisoformat(expiry)
            ceiling = ScoringEngine.max_acceptance_expiry(rating or "Low")
            if ceiling and expiry > ceiling:
                raise Conflict(
                    "RINV-4: a " + str(rating) + " risk may be accepted until at most "
                    + ceiling.isoformat()
                    + " (approval level: "
                    + str(ScoringEngine.required_approver(rating))
                    + ")",
                    detail={"max_expiry": ceiling.isoformat()},
                )
            data["acceptance_expiry_date"] = expiry

            # The approval level is part of the rule, not decoration. An
            # acceptance approved below the required seniority is not an
            # acceptance (codified-rules section 5.5, section 2.3).
            required = ScoringEngine.required_approver(rating)
            approver_id = data.get("acceptance_approved_by") or risk.acceptance_approved_by
            if required:
                if not approver_id:
                    raise Conflict(
                        "Acceptance at " + str(rating) + " requires approval at "
                        + required + " or above. Record the approver."
                    )
                from app.modules.identity.models import User

                approver = self.session.get(User, approver_id)
                if approver is None:
                    raise NotFound("approver not found")
                ladder = list(governance.seniority_ladder)
                if approver.seniority not in ladder or ladder.index(
                    approver.seniority
                ) < ladder.index(required):
                    raise Conflict(
                        "Acceptance at " + str(rating) + " requires approval at "
                        + required + " or above. " + approver.full_name + " is "
                        + str(approver.seniority) + ".",
                        detail={"required": required, "actual": approver.seniority},
                    )

            # Renewal caps: an exposure carried repeatedly is one nobody intends
            # to treat, which is the thing the cap exists to surface.
            cap = ScoringEngine.max_renewals(rating)
            if risk.acceptance_reassessment_count > cap:
                raise Conflict(
                    "A " + str(rating) + " risk may be accepted at most "
                    + str(cap + 1) + " time(s). This risk has been re-assessed "
                    + str(risk.acceptance_reassessment_count)
                    + " times and must now be treated, transferred or avoided.",
                    detail={"renewals": risk.acceptance_reassessment_count, "cap": cap},
                )

        self.apply(
            risk,
            {
                k: v
                for k, v in data.items()
                if k
                in (
                    "treatment_strategy",
                    "acceptance_expiry_date",
                    "acceptance_rationale",
                    "acceptance_approved_by",
                    "transfer_description",
                    "avoidance_description",
                    "partial_treatment_rationale",
                    "control_framework_mapping",
                )
            },
            action="TREATMENT_DECISION",
        )
        self.session.commit()
        return risk

    # -- links ------------------------------------------------------------

    def link_control(self, risk: Risk, objective_id: str) -> RiskControlLink:
        objective = self.session.get(ControlObjective, objective_id)
        if objective is None:
            raise NotFound("control objective " + objective_id + " not found")

        # RINV-3 / SEP-3, refused at the point of linking rather than later.
        if risk.risk_owner_id and objective.control_owner_id == risk.risk_owner_id:
            raise Conflict(
                "RINV-3 (SEP-3): " + objective.reference + " is owned by this risk's Risk "
                "Owner. A control owner cannot influence the scoring of a risk they own."
            )
        if any(link.objective_id == objective_id for link in risk.control_links):
            raise Conflict("control already linked to this risk")

        resolution = ScoringEngine.resolve_ce([objective])
        link = RiskControlLink(
            risk_id=risk.id,
            objective_id=objective_id,
            ce_at_assessment=resolution.effective_ce,
            linked_by=self.actor_id,
        )
        self.session.add(link)
        self.session.flush()
        self.enforce(risk)
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="risk",
            entity_id=risk.id,
            action="LINK_CONTROL",
            changed_fields={
                "objective": objective.reference,
                "ce_at_assessment": resolution.effective_ce,
            },
        )
        self.session.commit()
        self.session.refresh(risk)
        return link

    def unlink_control(self, risk: Risk, link_id: str) -> None:
        link = self.session.get(RiskControlLink, link_id)
        if link is None or link.risk_id != risk.id:
            raise NotFound("link not found on this risk")
        self.session.delete(link)
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="risk",
            entity_id=risk.id,
            action="UNLINK_CONTROL",
            changed_fields={"link_id": link_id},
        )
        self.session.commit()
        self.session.refresh(risk)

    def link_treatment(self, risk: Risk, treatment_id: str, is_primary: bool = False):
        treatment = self.session.get(Treatment, treatment_id)
        if treatment is None:
            raise NotFound("treatment " + treatment_id + " not found")
        if any(link.treatment_id == treatment_id for link in risk.treatment_links):
            raise Conflict("treatment already linked to this risk")
        # SEP-2: the decision maker is not the executor.
        if treatment.treatment_owner_id and treatment.treatment_owner_id == risk.risk_owner_id:
            raise Conflict(
                "SEP-2: the Risk Owner cannot also own the treatment. The decision maker "
                "and the executor must be different people."
            )
        link = RiskTreatmentLink(
            risk_id=risk.id,
            treatment_id=treatment_id,
            is_primary=is_primary,
            linked_by=self.actor_id,
        )
        self.session.add(link)
        self.session.flush()
        self.enforce(risk)
        self.session.commit()
        self.session.refresh(risk)
        return link

    def link_policy(self, risk: Risk, policy_id: str):
        existing = (
            self.session.query(RiskPolicyLink)
            .filter(RiskPolicyLink.risk_id == risk.id, RiskPolicyLink.policy_id == policy_id)
            .first()
        )
        if existing:
            raise Conflict("policy already linked to this risk")
        link = RiskPolicyLink(risk_id=risk.id, policy_id=policy_id, linked_by=self.actor_id)
        self.session.add(link)
        self.session.commit()
        return link

    # -- comments ---------------------------------------------------------

    def add_comment(self, risk: Risk, body: str, parent_id: str | None = None) -> RiskComment:
        comment = RiskComment(
            risk_id=risk.id, body=body, parent_comment_id=parent_id, created_by=self.actor_id
        )
        self.session.add(comment)
        self.session.commit()
        return comment

    # -- transition hook --------------------------------------------------

    def on_transition(self, entity: Risk, result, transition, payload: dict) -> None:
        entity.phase = PHASE_NUMBERS.get(result.target, entity.phase)

        # The Phase 6 gate is the only thing that releases the residual lock.
        if result.gate == "GATE_RESIDUAL_VALIDATED":
            entity.residual_score_locked = False
        if result.target in ("Preconditions", "Scoring") and result.source == "Monitoring":
            entity.residual_score_locked = True
        if result.gate == "GATE_CLOSURE":
            entity.closure_rationale = payload.get("reason") or entity.closure_rationale

        self._record_history(entity, result.source, result.target, result.gate, result.as_dict())

    def release_residual_lock(self, risk: Risk) -> Risk:
        """Explicit unlock once all five conditions hold, without advancing phase.
        Lets an analyst score residual and review it before committing the phase."""
        conditions = risk.residual_gate_conditions
        if not all(conditions.values()):
            raise Conflict(
                "RINV-1: the residual validation gate has unmet conditions",
                detail=conditions,
            )
        risk.residual_score_locked = False
        self.session.flush()
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type="risk",
            entity_id=risk.id,
            action="RESIDUAL_UNLOCKED",
            changed_fields={"conditions": conditions},
        )
        self.session.commit()
        return risk

    def _record_history(
        self, risk: Risk, source: str | None, target: str, gate: str, evaluation: dict
    ) -> None:
        self.session.add(
            RiskPhaseHistory(
                risk_id=risk.id,
                from_state=source,
                to_state=target,
                from_phase=PHASE_NUMBERS.get(source) if source else None,
                to_phase=PHASE_NUMBERS.get(target, 1),
                gate=gate,
                gate_evaluation=evaluation,
                changed_by=self.actor_id,
            )
        )

    # -- serialisation ----------------------------------------------------

    def detail(self, risk: Risk) -> dict[str, Any]:
        resolution = self.resolve_ce(risk)
        return {
            **summarise(risk),
            "statement": risk.statement,
            "cause": risk.cause,
            "threat_event": risk.threat_event,
            "vulnerability": risk.vulnerability,
            "impact_statement": risk.impact_statement,
            "intake_source": risk.intake_source,
            "identified_by": risk.identified_by,
            "tier_rationale": risk.tier_rationale,
            "impact_justification": risk.impact_justification,
            "likelihood_justification": risk.likelihood_justification,
            "residual_impact_rationale": risk.residual_impact_rationale,
            "residual_likelihood_rationale": risk.residual_likelihood_rationale,
            "acceptance_rationale": risk.acceptance_rationale,
            "transfer_description": risk.transfer_description,
            "avoidance_description": risk.avoidance_description,
            "partial_treatment_rationale": risk.partial_treatment_rationale,
            "control_framework_mapping": risk.control_framework_mapping,
            "closure_rationale": risk.closure_rationale,
            "evidence_ref": risk.evidence_ref,
            "readout_conducted_at": risk.readout_conducted_at,
            "readout_adjustment_rationale": risk.readout_adjustment_rationale,
            "preconditions": risk.preconditions,
            "residual_gate": risk.residual_gate_conditions,
            "ce_resolution": resolution.as_dict(),
            "controls": [
                {
                    "link_id": link.id,
                    "objective_id": link.objective_id,
                    "reference": link.objective.reference if link.objective else None,
                    "title": link.objective.title if link.objective else None,
                    "lifecycle_state": link.objective.lifecycle_state if link.objective else None,
                    "ce_at_assessment": link.ce_at_assessment,
                }
                for link in risk.control_links
            ],
            "treatments": [
                {
                    "link_id": link.id,
                    "treatment_id": link.treatment_id,
                    "reference": link.treatment.reference,
                    "title": link.treatment.title,
                    "lifecycle_state": link.treatment.lifecycle_state,
                    "grc_eng_validated": link.treatment.grc_eng_validated,
                    "owner_committed": link.treatment.owner_committed,
                    "target_date": link.treatment.target_date,
                    "is_primary": link.is_primary,
                }
                for link in risk.treatment_links
            ],
            "history": [
                {
                    "from": h.from_state,
                    "to": h.to_state,
                    "gate": h.gate,
                    "evaluation": h.gate_evaluation,
                    "changed_by": h.changed_by,
                    "created_at": h.created_at,
                }
                for h in risk.phase_history
            ],
            "comments": [
                {
                    "id": c.id,
                    "body": c.body,
                    "parent_comment_id": c.parent_comment_id,
                    "created_by": c.created_by,
                    "created_at": c.created_at,
                }
                for c in risk.comments
            ],
            "gates": self.gate_report(risk),
            "invariants": self.invariant_report(risk),
        }


def summarise(risk: Risk) -> dict[str, Any]:
    return {
        "id": risk.id,
        "reference": risk.reference,
        "title": risk.title,
        "lifecycle_state": risk.lifecycle_state,
        "phase": risk.phase_number,
        "tier": risk.tier,
        "impact": risk.impact,
        "likelihood": risk.likelihood,
        "inherent_risk_score": risk.inherent_risk_score,
        "inherent_rating": risk.inherent_rating,
        "inherent_locked": risk.inherent_locked,
        "residual_impact": risk.residual_impact,
        "residual_likelihood": risk.residual_likelihood,
        "residual_risk_score": risk.residual_risk_score,
        "residual_rating": risk.residual_rating,
        "residual_score_locked": risk.residual_score_locked,
        "reported_score": risk.reported_score,
        "reported_rating": risk.reported_rating,
        "appetite": (
            ScoringEngine.appetite_for(risk.reported_rating)
            if risk.reported_rating
            else None
        ),
        "treatment_strategy": risk.treatment_strategy,
        "acceptance_expiry_date": risk.acceptance_expiry_date,
        "next_review_date": risk.next_review_date,
        "sla_status": risk.sla_status,
        "rating_drift": risk.rating_drift,
        "escalation_flag": risk.escalation_flag,
        "escalation_reason": risk.escalation_reason,
        "control_change_flag": risk.control_change_flag,
        "control_change_detail": risk.control_change_detail,
        "readout_confirmed": risk.readout_confirmed,
        "reassessment_count": risk.reassessment_count,
        "risk_owner_id": risk.risk_owner_id,
        "risk_stakeholder_id": risk.risk_stakeholder_id,
        "risk_analyst_id": risk.risk_analyst_id,
        "created_at": risk.created_at,
        "updated_at": risk.updated_at,
    }
