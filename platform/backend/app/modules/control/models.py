"""Domain 3: Control Management.

Implements the three-level control object model from the specification:

    Control_Objective   what the control must achieve      (6 lifecycle states)
      -> Control_Activity   how it is implemented           (4 lifecycle states)
        -> Control_Deployment   where it actually runs      (5 lifecycle states)

Control effectiveness is assessed per deployment, not per objective (CE-3),
because operational reality differs per asset. Risk scoring takes the worst case
across a control's qualifying deployments (CE-4 / CINV-6).
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
from app.core.governance import CE_RATING_NAMES, DEPLOYMENT_STATE_NAMES, governance
from app.core.model_base import Timestamped, UUIDPrimaryKey

OBJECTIVE_STATES = (
    "Design",
    "Implementation",
    "Operating",
    "Failure",
    "Redesign",
    "Deprecated",
)
ACTIVITY_STATES = ("Draft", "Active", "Suspended", "Retired")
# Canonical definition lives in core.governance so the configuration validator
# can read it without importing this module.
DEPLOYMENT_STATES = DEPLOYMENT_STATE_NAMES

CE_RATINGS = CE_RATING_NAMES
TEST_RESULTS = ("Not_Tested", "Pass", "Partial", "Fail")
# Configuration-driven taxonomy. Validated at the service layer rather than by a
# CHECK constraint, so an organisation can change its taxonomy without a
# schema migration.
TEST_FREQUENCIES = governance.test_frequencies
CONTROL_TYPES = governance.control_types
ASSET_TIERS = governance.asset_tiers

CONTROL_FAMILIES = governance.control_families
AUTOMATION_LEVELS = governance.automation_levels
IMPLEMENTATION_TYPES = governance.implementation_types
OPERATING_FREQUENCIES = governance.operating_frequencies
ASSURANCE_METHODS = governance.assurance_methods
EVIDENCE_TYPES = governance.evidence_types


class AttackSurface(Base, UUIDPrimaryKey, Timestamped):
    """Asset register. Controls deploy onto assets; threat models scope to them."""

    __tablename__ = "attack_surfaces"
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="Tier_3")
    description: Mapped[str | None] = mapped_column(Text)
    system_owner_id: Mapped[str | None] = mapped_column(String(36))
    # Which compliance regimes this asset sits inside. AINV-2 reads it: a
    # requirement is covered only where the control runs on every in-scope
    # asset, and this is what decides which assets those are.
    compliance_scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class ControlObjective(Base, UUIDPrimaryKey, Timestamped):
    """What the control must achieve. Carries the 6-state lifecycle."""

    __tablename__ = "control_objectives"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN " + str(OBJECTIVE_STATES),
            name="ck_control_objectives_lifecycle_state",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    family: Mapped[str] = mapped_column(String(64), nullable=False, default="Governance")
    control_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Preventive")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Design")
    control_owner_id: Mapped[str | None] = mapped_column(String(36))

    # -- what the control must achieve ------------------------------------
    #
    # `description` says what the control is. `objective_statement` says what
    # "working" means, in terms a test can be written against. A control whose
    # objective cannot be stated testably cannot be assessed, only admired.
    objective_statement: Mapped[str | None] = mapped_column(Text)

    # -- how it runs -------------------------------------------------------
    #
    # CINV-11 caps CE by automation level. A manual control's evidence
    # describes the last time a person performed it, which says nothing about
    # the occasion nobody does, so it cannot hold the top rating.
    automation_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Manual"
    )
    # Orthogonal to preventive/detective/corrective: that is what the control
    # does about a threat, this is what kind of thing it is.
    implementation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Technical"
    )
    # How often the control OPERATES, as distinct from test_frequency on the
    # deployment, which is how often somebody checks that it did. Conflating
    # them is how "tested annually" gets read as "performed annually".
    operating_frequency: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Continuous"
    )

    # -- how it is assured -------------------------------------------------
    #
    # CINV-12: a key control cannot rest on the weaker methods. Asking somebody
    # whether a control works is not evidence that it does.
    assurance_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Inquiry"
    )
    is_key_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Set by the Failure cascade; cleared on return to Operating.
    failure_declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remediation_plan: Mapped[str | None] = mapped_column(Text)
    deprecation_rationale: Mapped[str | None] = mapped_column(Text)

    activities: Mapped[list["ControlActivity"]] = relationship(
        back_populates="objective", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def deployments(self) -> list["ControlDeployment"]:
        return [d for a in self.activities for d in a.deployments]

    @property
    def contributes_to_scoring(self) -> bool:
        """CE-5 / CINV-2: only Operating objectives feed risk scoring."""
        return self.lifecycle_state == "Operating"


class ControlActivity(Base, UUIDPrimaryKey, Timestamped):
    """How the objective is implemented. Carries the 4-state lifecycle."""

    __tablename__ = "control_activities"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN " + str(ACTIVITY_STATES),
            name="ck_control_activities_lifecycle_state",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    objective_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_objectives.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    control_operator_id: Mapped[str | None] = mapped_column(String(36))
    suspension_rationale: Mapped[str | None] = mapped_column(Text)

    # -- how this implementation actually works ---------------------------
    #
    # An activity may be more or less automated than its objective's headline
    # figure: an objective met by a nightly job on one estate and a monthly
    # spreadsheet on another is the normal case, not an edge case.
    automation_level: Mapped[str | None] = mapped_column(String(32))
    operating_frequency: Mapped[str | None] = mapped_column(String(32))

    # Where the procedure is written down. An activity whose runbook nobody can
    # produce is a description of an intention.
    procedure_ref: Mapped[str | None] = mapped_column(Text)
    # Which system performs or records it.
    tooling: Mapped[str | None] = mapped_column(String(200))
    # What this activity produces when it runs. Declaring it up front is what
    # makes a missing artefact detectable rather than arguable at audit.
    evidence_type: Mapped[str | None] = mapped_column(String(48))

    objective: Mapped[ControlObjective] = relationship(back_populates="activities")
    deployments: Mapped[list["ControlDeployment"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", lazy="selectin"
    )


class ControlDeployment(Base, UUIDPrimaryKey, Timestamped):
    """Where the control actually runs. Control effectiveness lives here."""

    __tablename__ = "control_deployments"
    __table_args__ = (
        UniqueConstraint("activity_id", "attack_surface_id", name="uq_deployment_activity_asset"),
        CheckConstraint(
            "deployment_status IN " + str(DEPLOYMENT_STATES),
            name="ck_control_deployments_status",
        ),
        CheckConstraint(
            "ce_rating IN " + str(CE_RATINGS), name="ck_control_deployments_ce_rating"
        ),
        CheckConstraint(
            "last_test_result IN " + str(TEST_RESULTS),
            name="ck_control_deployments_test_result",
        ),
        # CINV-1 at the schema layer: a rating above Unvalidated demands evidence.
        CheckConstraint(
            "ce_rating = 'CE-Unvalidated' OR ce_evidence_ref IS NOT NULL",
            name="ck_control_deployments_ce_evidence_required",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    activity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_activities.id", ondelete="CASCADE"), nullable=False
    )
    attack_surface_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("attack_surfaces.id", ondelete="RESTRICT"), nullable=False
    )
    deployment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Planned")

    ce_rating: Mapped[str] = mapped_column(String(32), nullable=False, default="CE-Unvalidated")
    ce_evidence_ref: Mapped[str | None] = mapped_column(Text)
    ce_assessed_by: Mapped[str | None] = mapped_column(String(36))
    ce_assessed_at: Mapped[date | None] = mapped_column(Date)
    ce_notes: Mapped[str | None] = mapped_column(Text)

    test_frequency: Mapped[str] = mapped_column(String(32), nullable=False, default="Quarterly")
    last_test_result: Mapped[str] = mapped_column(String(32), nullable=False, default="Not_Tested")
    last_tested_date: Mapped[date | None] = mapped_column(Date)
    next_test_due: Mapped[date | None] = mapped_column(Date)

    decommission_rationale: Mapped[str | None] = mapped_column(Text)

    activity: Mapped[ControlActivity] = relationship(back_populates="deployments")
    surface: Mapped[AttackSurface] = relationship(lazy="selectin")
    tests: Mapped[list["ControlTest"]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ControlTest.tested_at.desc()",
    )

    @property
    def ce_editable(self) -> bool:
        """DL-2 / CINV-4: CE is assessable only while the deployment is live."""
        return self.deployment_status in ("Active", "Degraded")

    @property
    def is_read_only(self) -> bool:
        """DL-3: decommissioned deployments are frozen."""
        return self.deployment_status == "Decommissioned"


class ControlTest(Base, UUIDPrimaryKey):
    """Immutable test history (CINV-7). Corrections create a superseding record
    referencing the original; UPDATE and DELETE are rejected by trigger."""

    __tablename__ = "control_tests"
    __table_args__ = (
        CheckConstraint("result IN " + str(TEST_RESULTS), name="ck_control_tests_result"),
    )

    deployment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_deployments.id", ondelete="CASCADE"), nullable=False
    )
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    tested_by: Mapped[str | None] = mapped_column(String(36))
    tested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    supersedes_id: Mapped[str | None] = mapped_column(String(36))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    deployment: Mapped[ControlDeployment] = relationship(back_populates="tests")
