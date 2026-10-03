"""The effectiveness review record (codified-rules 10.3)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.model_base import Timestamped, UUIDPrimaryKey

REVIEW_STATES = ("Open", "Completed", "Cancelled")


class ControlReview(Base, UUIDPrimaryKey, Timestamped):
    """One review per repair. Opened by the engine when a deployment returns to
    Active, closed by a Control Analyst once a retest proves the control works.

    A control coming back used to be silent: the risk it held up stayed at its
    inherent score, the threat scenario it mitigated stayed open, and the
    compliance requirement it covered stayed in Gap, with nothing telling anyone
    to look. This record is the thing that tells them, and the retest is what
    earns the telling.
    """

    __tablename__ = "control_reviews"
    __table_args__ = (
        CheckConstraint("lifecycle_state IN " + str(REVIEW_STATES), name="ck_control_reviews_state"),
        CheckConstraint(
            "lifecycle_state <> 'Completed' OR (completed_by IS NOT NULL AND completion_test_id IS NOT NULL)",
            name="ck_control_reviews_completion_evidenced",
        ),
        # REV-1 at the schema layer: one open review per deployment.
        Index(
            "uq_control_reviews_one_open",
            "deployment_id",
            unique=True,
            postgresql_where=text("lifecycle_state = 'Open'"),
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    deployment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objective_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_objectives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(16), nullable=False, default="Open")
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_by: Mapped[str | None] = mapped_column(String(36))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_test_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("control_tests.id", ondelete="SET NULL")
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deployment = relationship("ControlDeployment", lazy="selectin")
    objective = relationship("ControlObjective", lazy="selectin")

    @property
    def overdue(self) -> bool:
        return self.lifecycle_state == "Open" and self.due_date < date.today()
