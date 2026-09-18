"""Treatment service."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.errors import Conflict
from app.core.model_base import utcnow
from app.core.service import LifecycleService
from app.modules.treatment.machine import TREATMENT_MACHINE
from app.modules.treatment.models import Treatment, TreatmentApproval, TreatmentCheckin

CHECKIN_INTERVAL_DAYS = {"Weekly": 7, "Fortnightly": 14, "Monthly": 30, "Quarterly": 90}


class TreatmentService(LifecycleService[Treatment]):
    model = Treatment
    machine = TREATMENT_MACHINE
    entity_name = "treatment"
    reference_prefix = "TRT"
    taxonomy = {"loe": "loe_bands", "check_in_frequency": "checkin_frequencies"}

    def create_treatment(self, data: dict[str, Any]) -> Treatment:
        treatment = Treatment(
            reference=self.next_reference(), created_by=self.actor_id, **data
        )
        self.create(treatment)
        self.session.commit()
        return treatment

    def validate_feasibility(self, treatment: Treatment, notes: str | None) -> Treatment:
        """RINV-12 half one. Recorded against the named GRC Engineer, and refused
        if that person is also on the hook for delivery (SEP-5)."""
        if not self.actor_roles or not any(
            r in self.actor_roles for r in ("GRC_Engineer", "CISO", "Admin")
        ):
            raise Conflict(
                "RINV-12: feasibility validation must be performed by a GRC Engineer"
            )
        if self.actor_id == treatment.treatment_owner_id:
            raise Conflict(
                "SEP-5: the GRC Engineer validating feasibility cannot be the treatment owner"
            )
        self.apply(
            treatment,
            {
                "grc_eng_validated": True,
                "grc_eng_validated_by": self.actor_id,
                "grc_eng_validation_notes": notes,
            },
            action="GRC_VALIDATION",
        )
        self.session.commit()
        return treatment

    def commit_owner(self, treatment: Treatment) -> Treatment:
        """RINV-12 half two. Only the named treatment owner can commit."""
        if treatment.treatment_owner_id is None:
            raise Conflict("assign a treatment owner before recording a commitment")
        if self.actor_id != treatment.treatment_owner_id and not any(
            r in self.actor_roles for r in ("Admin",)
        ):
            raise Conflict(
                "RINV-12: only the named treatment owner can record their own commitment"
            )
        self.apply(
            treatment,
            {"owner_committed": True, "owner_committed_at": utcnow()},
            action="OWNER_COMMITMENT",
        )
        self.session.commit()
        return treatment

    def add_checkin(self, treatment: Treatment, data: dict[str, Any]) -> TreatmentCheckin:
        checkin = TreatmentCheckin(
            treatment_id=treatment.id,
            status=data["status"],
            notes=data["notes"],
            blockers=data.get("blockers"),
            submitted_by=self.actor_id,
        )
        self.session.add(checkin)
        interval = CHECKIN_INTERVAL_DAYS.get(treatment.check_in_frequency or "Monthly", 30)
        treatment.last_checkin_at = utcnow()
        treatment.next_checkin_due = date.today() + timedelta(days=interval)
        self.session.commit()
        return checkin

    def request_approval(self, treatment: Treatment, data: dict[str, Any]) -> TreatmentApproval:
        approval = TreatmentApproval(
            treatment_id=treatment.id,
            approval_type=data.get("approval_type", "treatment_approval"),
            requested_by=self.actor_id,
            assigned_to=data.get("assigned_to"),
            proposed_new_date=data.get("proposed_new_date"),
        )
        self.session.add(approval)
        self.session.commit()
        return approval

    def decide_approval(
        self, approval_id: str, decision: str, notes: str | None
    ) -> TreatmentApproval:
        approval = self.session.get(TreatmentApproval, approval_id)
        if approval is None:
            raise Conflict("approval request not found")
        if approval.requested_by == self.actor_id:
            raise Conflict("SEP-4: the requester cannot approve their own request")
        approval.decision = decision
        approval.decision_by = self.actor_id
        approval.decision_at = utcnow()
        approval.decision_notes = notes

        if decision == "Approved" and approval.proposed_new_date:
            treatment = self.session.get(Treatment, approval.treatment_id)
            if treatment is not None:
                treatment.target_date = approval.proposed_new_date
        self.session.commit()
        return approval

    def detail(self, treatment: Treatment) -> dict[str, Any]:
        return {
            **summarise_treatment(treatment),
            "description": treatment.description,
            "grc_eng_validated_by": treatment.grc_eng_validated_by,
            "grc_eng_validation_notes": treatment.grc_eng_validation_notes,
            "evidence_ref": treatment.evidence_ref,
            "loe_implementation_hours": treatment.loe_implementation_hours,
            "loe_operational_hours_pa": treatment.loe_operational_hours_pa,
            "cost_implementation": (
                float(treatment.cost_implementation)
                if treatment.cost_implementation is not None
                else None
            ),
            "cost_operational_pa": (
                float(treatment.cost_operational_pa)
                if treatment.cost_operational_pa is not None
                else None
            ),
            "checkins": [
                {
                    "id": c.id,
                    "status": c.status,
                    "notes": c.notes,
                    "blockers": c.blockers,
                    "submitted_by": c.submitted_by,
                    "created_at": c.created_at,
                }
                for c in treatment.checkins
            ],
            "approvals": [
                {
                    "id": a.id,
                    "approval_type": a.approval_type,
                    "requested_by": a.requested_by,
                    "assigned_to": a.assigned_to,
                    "proposed_new_date": a.proposed_new_date,
                    "decision": a.decision,
                    "decision_by": a.decision_by,
                    "decision_at": a.decision_at,
                    "decision_notes": a.decision_notes,
                }
                for a in treatment.approvals
            ],
            "linked_risks": self._linked_risks(treatment),
            "gates": self.gate_report(treatment),
        }

    def _linked_risks(self, treatment: Treatment) -> list[dict[str, Any]]:
        from app.modules.risk.models import Risk, RiskTreatmentLink

        links = (
            self.session.query(RiskTreatmentLink)
            .filter(RiskTreatmentLink.treatment_id == treatment.id)
            .all()
        )
        if not links:
            return []
        risks = self.session.query(Risk).filter(Risk.id.in_([l.risk_id for l in links])).all()
        return [
            {
                "id": r.id,
                "reference": r.reference,
                "title": r.title,
                "reported_rating": r.reported_rating,
                "lifecycle_state": r.lifecycle_state,
            }
            for r in risks
        ]


def summarise_treatment(t: Treatment) -> dict[str, Any]:
    overdue = bool(
        t.target_date and t.target_date < date.today() and t.lifecycle_state != "Complete"
    )
    return {
        "id": t.id,
        "reference": t.reference,
        "title": t.title,
        "treatment_type": t.treatment_type,
        "lifecycle_state": t.lifecycle_state,
        "grc_eng_validated": t.grc_eng_validated,
        "owner_committed": t.owner_committed,
        "readout_ready": t.readout_ready,
        "treatment_owner_id": t.treatment_owner_id,
        "target_date": t.target_date,
        "completed_at": t.completed_at,
        "overdue": overdue,
        "loe": t.loe,
        "expected_impact_delta": t.expected_impact_delta,
        "expected_likelihood_delta": t.expected_likelihood_delta,
        "check_in_frequency": t.check_in_frequency,
        "last_checkin_at": t.last_checkin_at,
        "next_checkin_due": t.next_checkin_due,
        "checkin_count": len(t.checkins),
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }
