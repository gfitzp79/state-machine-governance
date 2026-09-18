"""Domain 8: Compliance and Assurance.

The register holds framework REQUIREMENTS as first-class records rather than
deriving compliance from the policies that happen to reference a control. The
previous model had control objectives inherit their mappings from linked
policies (CF-2), which is lossy in the one direction that matters: a policy
mapped to three clauses passes all three to every control beneath it, so the
system can say a control is "ISO-mapped" but cannot say which clause it
satisfies. That is the only question an assessor asks.

Holding requirements as records also makes CF-3 implementable. A coverage gap
cannot be detected without the set to compare against, and a list of framework
NAMES is not that set.

The coverage model reuses two arguments already made elsewhere in this
specification:

  * coverage is asserted against a DEPLOYMENT, not an objective, because a
    control only satisfies a requirement where it actually runs (TINV-4)
  * partial coverage is a gap with work in progress, not coverage, because a
    requirement half-satisfied is a requirement not satisfied (TM-PARTIAL)
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.governance import governance
from app.core.model_base import Timestamped, UUIDPrimaryKey

ASSESSMENT_STATES = (
    "Not_Assessed",
    "Not_Applicable",
    "Applicable",
    "Covered",
    "Compensating",
    "Gap",
)

# Configuration-driven, validated at the service layer so an organisation can
# add a coverage level without a schema migration.
COVERAGE_LEVELS = governance.coverage_levels


class ComplianceFramework(Base, UUIDPrimaryKey, Timestamped):
    """One framework at one version.

    Version is part of the identity, not an attribute to be edited. ISO
    27001:2013 and ISO 27001:2022 renumbered and merged controls; treating the
    change as an edit would silently re-point every existing coverage assertion
    at a clause that may no longer mean the same thing. AINV-7 makes a new
    version a new record.
    """

    __tablename__ = "compliance_frameworks"
    __table_args__ = (
        UniqueConstraint("framework_id", name="uq_compliance_framework_id"),
    )

    # Natural key from the catalogue file, e.g. NIST-CSF-2.0.
    framework_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    authority: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(Text)

    # AINV-6. False means this repository may not carry the requirement text,
    # and the loader refuses a catalogue that claims otherwise.
    redistributable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    licence_note: Mapped[str | None] = mapped_column(Text)

    # Adopted means in scope for the organisation. A framework may be loaded and
    # browsable without being something the organisation is held to.
    adopted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    adopted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requirements: Mapped[list["ComplianceRequirement"]] = relationship(
        back_populates="framework", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def requirement_count(self) -> int:
        return len(self.requirements)

    @property
    def carries_text(self) -> bool:
        """AINV-6 support: does any requirement carry redistributable prose?"""
        return any(bool(r.requirement_text) for r in self.requirements)


class ComplianceRequirement(Base, UUIDPrimaryKey, Timestamped):
    """One clause, control or subcategory of a framework."""

    __tablename__ = "compliance_requirements"
    __table_args__ = (
        UniqueConstraint("framework_id", "ref", name="uq_requirement_ref_per_framework"),
    )

    framework_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("compliance_frameworks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The identifier as the framework writes it: GV.OC-01, A.5.15, 8.3.1.
    ref: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Full prose. Null for a framework whose text may not be redistributed;
    # populated by an operator importing from their own licensed copy.
    requirement_text: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    framework: Mapped[ComplianceFramework] = relationship(back_populates="requirements")
    assessment: Mapped["RequirementAssessment"] = relationship(
        back_populates="requirement",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    control_links: Mapped[list["ControlRequirementLink"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def satisfying_links(self) -> list["ControlRequirementLink"]:
        """Links whose coverage level can, on its own, satisfy the requirement.

        Partial is excluded by configuration rather than by name, so an
        organisation adding its own level decides whether it satisfies.
        """
        satisfying = governance.satisfying_coverage_levels
        return [link for link in self.control_links if link.coverage_level in satisfying]


class RequirementAssessment(Base, UUIDPrimaryKey, Timestamped):
    """The organisation's position on one requirement.

    This is a Statement of Applicability entry. ISO 27001 requires a documented
    justification for every excluded control, which is why AINV-1 refuses a
    Not_Applicable without a rationale: an unexplained exclusion is the single
    most common audit finding against an SoA.
    """

    __tablename__ = "requirement_assessments"
    __table_args__ = (
        UniqueConstraint("requirement_id", name="uq_assessment_per_requirement"),
        CheckConstraint(
            "lifecycle_state IN " + str(ASSESSMENT_STATES),
            name="ck_requirement_assessments_state",
        ),
        # AINV-1 at the schema layer: an exclusion always carries its reason.
        CheckConstraint(
            "lifecycle_state <> 'Not_Applicable' OR rationale IS NOT NULL",
            name="ck_requirement_assessments_exclusion_justified",
        ),
        # AINV-4 at the schema layer: compensating coverage is never permanent.
        CheckConstraint(
            "lifecycle_state <> 'Compensating' OR compensating_expiry IS NOT NULL",
            name="ck_requirement_assessments_compensating_time_bound",
        ),
    )

    requirement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("compliance_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Not_Assessed"
    )
    rationale: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(String(36))
    assessed_by: Mapped[str | None] = mapped_column(String(36))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set when the position rests on a compensating control (AINV-4).
    compensating_expiry: Mapped[date | None] = mapped_column(Date)

    # Set by the AINV-5 cascade when a deployment this requirement depended on
    # fails, so the reason a requirement became a gap survives in the record.
    gap_reason: Mapped[str | None] = mapped_column(Text)

    requirement: Mapped[ComplianceRequirement] = relationship(back_populates="assessment")

    @property
    def is_in_scope(self) -> bool:
        return self.lifecycle_state not in ("Not_Assessed", "Not_Applicable")

    @property
    def is_satisfied(self) -> bool:
        return self.lifecycle_state in ("Covered", "Compensating")


class ControlRequirementLink(Base, UUIDPrimaryKey):
    """A person's assertion that a control objective addresses a requirement.

    The assertion is deliberately explicit and attributed. Nothing infers a link
    from a shared policy, a matching control family, or a keyword: the same
    argument as TINV-7, where the ambient presence of a control never resolves a
    threat. Somebody has to say so, and the record says who.
    """

    __tablename__ = "control_requirement_links"
    __table_args__ = (
        UniqueConstraint(
            "objective_id", "requirement_id", name="uq_control_requirement"
        ),
    )

    objective_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("control_objectives.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("compliance_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coverage_level: Mapped[str] = mapped_column(String(32), nullable=False, default="Full")
    rationale: Mapped[str | None] = mapped_column(Text)
    asserted_by: Mapped[str | None] = mapped_column(String(36))
    asserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    requirement: Mapped[ComplianceRequirement] = relationship(back_populates="control_links")
    # Deliberately one-directional. The control module must not carry a
    # relationship to this one: modules depend downward, and a back-reference
    # would make importing control.models fail unless compliance.models had
    # already been imported.
    objective = relationship("ControlObjective", lazy="selectin")

    @property
    def satisfies(self) -> bool:
        return self.coverage_level in governance.satisfying_coverage_levels
