"""Opening, completing and escalating effectiveness reviews."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.core.governance import governance
from app.core.service import LifecycleService
from app.engine import AuditTrail
from app.modules.review.machine import CONTROL_REVIEW_MACHINE, _passing_test
from app.modules.review.models import ControlReview


def control_editors(session) -> list[str]:
    """Everyone holding a role that may edit controls: the people a review is for."""
    from app.modules.identity.models import User, UserRole

    roles = governance.edit_permissions.get("control", ())
    if not roles:
        return []
    return list(dict.fromkeys(session.execute(
        select(User.id).join(UserRole, UserRole.user_id == User.id).where(UserRole.role.in_(roles))
    ).scalars()))


def role_holders(session, role: str) -> list[str]:
    from app.modules.identity.models import User, UserRole

    return list(session.execute(
        select(User.id).join(UserRole, UserRole.user_id == User.id).where(UserRole.role == role)
    ).scalars())


class ReviewService(LifecycleService[ControlReview]):
    model = ControlReview
    machine = CONTROL_REVIEW_MACHINE
    entity_name = "control_review"
    reference_prefix = "CRV"

    def open_for(self, deployment, trigger: str) -> ControlReview | None:
        """REV-1: a deployment back in service gets exactly one open review.
        Called by the engine, so it needs no role."""
        existing = self.session.execute(
            select(ControlReview).where(
                ControlReview.deployment_id == deployment.id,
                ControlReview.lifecycle_state == "Open",
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None
        review = ControlReview(
            reference=self.next_reference(),
            deployment_id=deployment.id,
            objective_id=deployment.activity.objective_id,
            trigger=trigger,
            due_date=date.today() + timedelta(days=governance.control_recovery_review_days),
        )
        self.session.add(review)
        self.session.flush()
        self.session.refresh(review)
        return review

    def on_transition(self, entity: ControlReview, result, transition, payload: dict) -> None:
        if result.target == "Completed":
            test = _passing_test(entity)
            entity.completed_by = self.actor_id
            entity.completed_at = datetime.now(timezone.utc)
            entity.completion_test_id = test.id if test else None
        if result.target == "Cancelled":
            entity.cancellation_reason = str(payload.get("reason") or "").strip() or None

    def detail(self, review: ControlReview) -> dict[str, Any]:
        dep = review.deployment
        obj = review.objective
        asset = getattr(getattr(dep, "surface", None), "name", None) if dep else None
        return {
            "id": review.id,
            "reference": review.reference,
            "lifecycle_state": review.lifecycle_state,
            "trigger": review.trigger,
            "deployment_id": review.deployment_id,
            "deployment_reference": dep.reference if dep else None,
            "deployment_status": dep.deployment_status if dep else None,
            "asset": asset,
            "objective_id": review.objective_id,
            "objective_reference": obj.reference if obj else None,
            "objective_title": obj.title if obj else None,
            "opened_at": review.opened_at,
            "due_date": review.due_date,
            "overdue": review.overdue,
            "escalated_at": review.escalated_at,
            "completed_by": review.completed_by,
            "completed_at": review.completed_at,
            "completion_test_id": review.completion_test_id,
            "cancellation_reason": review.cancellation_reason,
            "gates": self.gate_report(review),
        }


def escalate_overdue_reviews(session, actor_id: str | None = None) -> list[str]:
    """REV-4: a review still open past its due date goes to the CISO, once."""
    late = session.execute(
        select(ControlReview).where(
            ControlReview.lifecycle_state == "Open",
            ControlReview.due_date < date.today(),
            ControlReview.escalated_at.is_(None),
        )
    ).scalars().all()
    for review in late:
        review.escalated_at = datetime.now(timezone.utc)
        obj = review.objective
        for recipient in role_holders(session, "CISO"):
            AuditTrail.notify(
                session,
                recipient_id=recipient,
                entity_type="control_review",
                entity_id=review.id,
                event_type="control_review_overdue",
                title=review.reference + " is overdue: " + (obj.reference if obj else "a control")
                + " has not been retested since its repair",
                body=(
                    "The control came back into service on "
                    + review.opened_at.date().isoformat()
                    + " and nobody has shown it works. Everything that depends on it is "
                    "still waiting to be re-assessed (REV-4)."
                ),
            )
        AuditTrail.record(
            session,
            actor_id=actor_id,
            entity_type="control_review",
            entity_id=review.id,
            action="REVIEW_ESCALATED",
            changed_fields={"due": review.due_date.isoformat(), "rule": "REV-4"},
        )
    return [r.reference for r in late]
