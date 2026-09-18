"""Domain 5: Policy and Standards.

Policy versions are immutable (PINV-9) and exceptions are always time-bound
(PINV-2). PL-3 is handled architecturally rather than by a rule: revising a policy
creates a draft version while the Active version remains system of record, so
there is no window in which nothing is enforceable.
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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.governance import governance
from app.core.model_base import Timestamped, UUIDPrimaryKey

POLICY_STATES = ("Draft", "Under_Review", "Approved", "Active", "Under_Revision", "Deprecated")
EXCEPTION_STATES = ("Requested", "Approved", "Rejected", "Expired")
REVIEW_CYCLES = governance.review_cycles
POLICY_TYPES = governance.policy_types

# Frameworks whose audit cadence forces an annual review cycle (CF-4 / PINV-4).
ANNUAL_AUDIT_FRAMEWORKS = governance.annual_audit_frameworks


class Policy(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN " + str(POLICY_STATES), name="ck_policies_lifecycle_state"
        ),
        # PINV-5 at the schema layer: no self-approval, ever.
        CheckConstraint(
            "approved_by IS NULL OR policy_owner_id IS NULL OR approved_by <> policy_owner_id",
            name="ck_policies_no_self_approval",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    policy_type: Mapped[str] = mapped_column(
        String(48), nullable=False, default="Information_Security"
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    review_cycle: Mapped[str] = mapped_column(String(16), nullable=False, default="Annual")

    effective_date: Mapped[date | None] = mapped_column(Date)
    next_review_date: Mapped[date | None] = mapped_column(Date)

    scope: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(Text)

    compliance_mappings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    exception_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Set by the revision cascade; the count of controls awaiting re-alignment.
    realignment_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    realignment_due: Mapped[date | None] = mapped_column(Date)

    policy_owner_id: Mapped[str | None] = mapped_column(String(36), index=True)
    approved_by: Mapped[str | None] = mapped_column(String(36))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(36))

    versions: Mapped[list["PolicyVersion"]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PolicyVersion.created_at.desc()",
    )
    exceptions: Mapped[list["PolicyException"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan", lazy="selectin"
    )
    control_links: Mapped[list["PolicyControlLink"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan", lazy="selectin"
    )
    standards: Mapped[list["Standard"]] = relationship(
        back_populates="parent_policy", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def requires_annual_review(self) -> bool:
        """CF-4 / PINV-4."""
        mappings = self.compliance_mappings or []
        return any(m in ANNUAL_AUDIT_FRAMEWORKS for m in mappings)

    @property
    def active_exception_count(self) -> int:
        return sum(1 for e in self.exceptions if e.lifecycle_state == "Approved")


class Standard(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "standards"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN " + str(POLICY_STATES), name="ck_standards_lifecycle_state"
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    parent_policy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE")
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    review_cycle: Mapped[str] = mapped_column(String(16), nullable=False, default="Annual")
    scope: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    compliance_mappings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str | None] = mapped_column(String(36))

    parent_policy: Mapped[Policy | None] = relationship(back_populates="standards")


class PolicyVersion(Base, UUIDPrimaryKey):
    """Immutable (PINV-9). UPDATE and DELETE rejected by database trigger."""

    __tablename__ = "policy_versions"

    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(Text)
    lifecycle_state_at_capture: Mapped[str | None] = mapped_column(String(32))
    edited_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    policy: Mapped[Policy] = relationship(back_populates="versions")


class PolicyException(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "policy_exceptions"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN " + str(EXCEPTION_STATES),
            name="ck_policy_exceptions_lifecycle_state",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    business_justification: Mapped[str] = mapped_column(Text, nullable=False)
    risk_statement: Mapped[str | None] = mapped_column(Text)
    compensating_controls: Mapped[str | None] = mapped_column(Text)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Requested")
    # PINV-2: NOT NULL. An exception is never open-ended.
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(36))
    approved_by: Mapped[str | None] = mapped_column(String(36))
    rejection_rationale: Mapped[str | None] = mapped_column(Text)
    promoted_risk_id: Mapped[str | None] = mapped_column(String(36))

    policy: Mapped[Policy] = relationship(back_populates="exceptions")

    @property
    def days_to_expiry(self) -> int:
        return (self.expiry_date - date.today()).days


class PolicyControlLink(Base, UUIDPrimaryKey):
    __tablename__ = "policy_controls"
    __table_args__ = (UniqueConstraint("policy_id", "objective_id", name="uq_policy_controls"),)

    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objective_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_objectives.id", ondelete="CASCADE"), nullable=False
    )
    # Set by the policy revision cascade; cleared when the owner confirms.
    realignment_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    realignment_due: Mapped[date | None] = mapped_column(Date)
    linked_by: Mapped[str | None] = mapped_column(String(36))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    policy: Mapped[Policy] = relationship(back_populates="control_links")
    objective = relationship("ControlObjective", lazy="selectin")
