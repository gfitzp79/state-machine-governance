"""Domain 4: Treatment Management.

Treatments are the delivery vehicle for a Mitigate decision. RINV-12 is the rule
that matters here: nothing reaches a governance readout without GRC Engineer
feasibility validation and an explicit commitment from the treatment owner.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.governance import TREATMENT_STRATEGIES, governance
from app.core.model_base import Timestamped, UUIDPrimaryKey

TREATMENT_STATES = ("Proposed", "Validated", "Approved", "In_Progress", "Complete", "Cancelled")
TREATMENT_TYPES = TREATMENT_STRATEGIES
LOE_BANDS = governance.loe_bands
CHECKIN_FREQUENCIES = governance.checkin_frequencies


class Treatment(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "treatments"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN " + str(TREATMENT_STATES), name="ck_treatments_lifecycle_state"
        ),
        CheckConstraint(
            "treatment_type IN " + str(TREATMENT_TYPES), name="ck_treatments_type"
        ),
        CheckConstraint(
            "expected_impact_delta BETWEEN -4 AND 0", name="ck_treatments_impact_delta"
        ),
        CheckConstraint(
            "expected_likelihood_delta BETWEEN -4 AND 0", name="ck_treatments_likelihood_delta"
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    treatment_type: Mapped[str] = mapped_column(String(16), nullable=False, default="Mitigate")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Proposed")

    # RINV-12: both flags must be true before the parent risk can reach readout.
    grc_eng_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    grc_eng_validated_by: Mapped[str | None] = mapped_column(String(36))
    grc_eng_validation_notes: Mapped[str | None] = mapped_column(Text)
    owner_committed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    treatment_owner_id: Mapped[str | None] = mapped_column(String(36), index=True)
    target_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    loe: Mapped[str | None] = mapped_column(String(8))
    loe_implementation_hours: Mapped[int | None] = mapped_column(Integer)
    loe_operational_hours_pa: Mapped[int | None] = mapped_column(Integer)
    cost_implementation: Mapped[float | None] = mapped_column(Numeric(14, 2))
    cost_operational_pa: Mapped[float | None] = mapped_column(Numeric(14, 2))

    expected_impact_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_likelihood_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    check_in_frequency: Mapped[str | None] = mapped_column(String(16))
    last_checkin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_checkin_due: Mapped[date | None] = mapped_column(Date)

    # Evidence that the mitigation is real, required by residual gate condition 2.
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(36))

    checkins: Mapped[list["TreatmentCheckin"]] = relationship(
        back_populates="treatment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TreatmentCheckin.created_at.desc()",
    )
    approvals: Mapped[list["TreatmentApproval"]] = relationship(
        back_populates="treatment", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_complete(self) -> bool:
        return self.lifecycle_state == "Complete"

    @property
    def readout_ready(self) -> bool:
        """RINV-12 expressed on a single treatment."""
        return self.grc_eng_validated and self.owner_committed


class TreatmentApproval(Base, UUIDPrimaryKey):
    __tablename__ = "treatment_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('Pending', 'Approved', 'Rejected')", name="ck_treatment_approvals_decision"
        ),
    )

    treatment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("treatments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approval_type: Mapped[str] = mapped_column(
        String(48), nullable=False, default="treatment_approval"
    )
    requested_by: Mapped[str | None] = mapped_column(String(36))
    assigned_to: Mapped[str | None] = mapped_column(String(36))
    proposed_new_date: Mapped[date | None] = mapped_column(Date)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="Pending")
    decision_by: Mapped[str | None] = mapped_column(String(36))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    treatment: Mapped[Treatment] = relationship(back_populates="approvals")


class TreatmentCheckin(Base, UUIDPrimaryKey):
    """Progress record. Append-only: the drift trail depends on it."""

    __tablename__ = "treatment_checkins"

    treatment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("treatments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    blockers: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    treatment: Mapped[Treatment] = relationship(back_populates="checkins")
