"""Domain 2: Risk Management.

The risk register and its 7-phase lifecycle. Every gate flag on this model exists
because a specific gate in the specification reads it; none of them are advisory
metadata. The residual score fields are locked until GATE_RESIDUAL_VALIDATED
passes, which is the single most important enforcement point in the platform.
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
from app.core.governance import RATING_NAMES, TREATMENT_STRATEGIES, governance
from app.core.model_base import Timestamped, UUIDPrimaryKey

# The 7 phases, in order. Index + 1 is the phase number.
RISK_PHASES = (
    "Intake",
    "Preconditions",
    "Scoring",
    "Treatment",
    "Readout",
    "Evidence_Residual",
    "Monitoring",
)
RISK_STATES = RISK_PHASES + ("Closed",)

PHASE_NUMBERS = {name: i + 1 for i, name in enumerate(RISK_PHASES)}
PHASE_NUMBERS["Closed"] = 7

# Band names and treatment strategies are framework-fixed: the invariants and
# the CHECK constraints below reference them by name.
RATINGS = RATING_NAMES
# Tiers and intake sources are configuration.
RISK_TIERS = governance.risk_tiers
SLA_STATUSES = ("On_Track", "At_Risk", "Breached")
INTAKE_SOURCES = governance.intake_sources


class Risk(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint("phase BETWEEN 1 AND 7", name="ck_risks_phase"),
        CheckConstraint("lifecycle_state IN " + str(RISK_STATES), name="ck_risks_lifecycle_state"),
        CheckConstraint("impact IS NULL OR impact BETWEEN 1 AND 5", name="ck_risks_impact"),
        CheckConstraint(
            "likelihood IS NULL OR likelihood BETWEEN 1 AND 5", name="ck_risks_likelihood"
        ),
        CheckConstraint(
            "residual_impact IS NULL OR residual_impact BETWEEN 1 AND 5",
            name="ck_risks_residual_impact",
        ),
        CheckConstraint(
            "residual_likelihood IS NULL OR residual_likelihood BETWEEN 1 AND 5",
            name="ck_risks_residual_likelihood",
        ),
        CheckConstraint(
            "inherent_rating IS NULL OR inherent_rating IN " + str(RATINGS),
            name="ck_risks_inherent_rating",
        ),
        CheckConstraint(
            "residual_rating IS NULL OR residual_rating IN " + str(RATINGS),
            name="ck_risks_residual_rating",
        ),
        CheckConstraint(
            "treatment_strategy IS NULL OR treatment_strategy IN " + str(TREATMENT_STRATEGIES),
            name="ck_risks_treatment_strategy",
        ),
        CheckConstraint("sla_status IN " + str(SLA_STATUSES), name="ck_risks_sla_status"),
        # RINV-4 at the schema layer: acceptance is never open-ended.
        CheckConstraint(
            "treatment_strategy IS DISTINCT FROM 'Accept' OR acceptance_expiry_date IS NOT NULL",
            name="ck_risks_acceptance_time_bound",
        ),
        # RINV-5 at the schema layer, backing the service-layer check.
        CheckConstraint(
            "treatment_strategy IS DISTINCT FROM 'Accept' "
            "OR inherent_rating IS DISTINCT FROM 'Critical'",
            name="ck_risks_critical_never_accepted",
        ),
        # SEP-1: the decision maker is never their own oversight.
        CheckConstraint(
            "risk_owner_id IS NULL OR risk_stakeholder_id IS NULL "
            "OR risk_owner_id <> risk_stakeholder_id",
            name="ck_risks_sep1_owner_not_stakeholder",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    # -- lifecycle --------------------------------------------------------
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Intake")
    phase: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # -- structured risk statement (Phase 1 gate) -------------------------
    cause: Mapped[str | None] = mapped_column(Text)
    threat_event: Mapped[str | None] = mapped_column(Text)
    vulnerability: Mapped[str | None] = mapped_column(Text)
    impact_statement: Mapped[str | None] = mapped_column(Text)
    intake_source: Mapped[str | None] = mapped_column(String(48))
    identified_by: Mapped[str | None] = mapped_column(String(200))

    # -- Phase 2 preconditions checklist ----------------------------------
    pre_true_risk_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pre_tier_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pre_stakeholders_identified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    pre_ce_assessed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    precondition_notes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    tier: Mapped[str | None] = mapped_column(String(16))
    tier_rationale: Mapped[str | None] = mapped_column(Text)

    # -- inherent scoring (Phase 3) ---------------------------------------
    impact: Mapped[int | None] = mapped_column(Integer)
    likelihood: Mapped[int | None] = mapped_column(Integer)
    inherent_risk_score: Mapped[int | None] = mapped_column(Integer)
    inherent_rating: Mapped[str | None] = mapped_column(String(16))
    impact_justification: Mapped[str | None] = mapped_column(Text)
    likelihood_justification: Mapped[str | None] = mapped_column(Text)
    # OUT-5: inherent scores freeze once the risk passes Phase 3.
    inherent_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # -- treatment (Phase 4) ----------------------------------------------
    treatment_strategy: Mapped[str | None] = mapped_column(String(16))
    acceptance_expiry_date: Mapped[date | None] = mapped_column(Date)
    acceptance_rationale: Mapped[str | None] = mapped_column(Text)
    acceptance_approved_by: Mapped[str | None] = mapped_column(String(36))
    acceptance_reassessment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transfer_description: Mapped[str | None] = mapped_column(Text)
    avoidance_description: Mapped[str | None] = mapped_column(Text)
    partial_treatment_rationale: Mapped[str | None] = mapped_column(Text)
    control_framework_mapping: Mapped[str | None] = mapped_column(Text)

    # -- readout (Phase 5) ------------------------------------------------
    readout_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    readout_conducted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    readout_adjustment_rationale: Mapped[str | None] = mapped_column(Text)

    # -- residual validation gate (Phase 6), all five conditions ----------
    gate_mitigations_implemented: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    gate_evidence_provided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gate_effectiveness_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    gate_governance_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gate_drift_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    residual_gate_notes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # RINV-1: residual is locked until the gate releases it. Cascades re-lock it.
    residual_score_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    residual_impact: Mapped[int | None] = mapped_column(Integer)
    residual_likelihood: Mapped[int | None] = mapped_column(Integer)
    residual_risk_score: Mapped[int | None] = mapped_column(Integer)
    residual_rating: Mapped[str | None] = mapped_column(String(16))
    residual_impact_rationale: Mapped[str | None] = mapped_column(Text)
    residual_likelihood_rationale: Mapped[str | None] = mapped_column(Text)

    # -- monitoring (Phase 7) ---------------------------------------------
    next_review_date: Mapped[date | None] = mapped_column(Date)
    sla_status: Mapped[str] = mapped_column(String(16), nullable=False, default="On_Track")
    escalation_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    # Set by the control-failure cascade; surfaced as a banner in the UI.
    control_change_flag: Mapped[str | None] = mapped_column(String(64))
    control_change_detail: Mapped[str | None] = mapped_column(Text)
    reassessment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    closure_rationale: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[str | None] = mapped_column(String(36))

    # -- ownership --------------------------------------------------------
    risk_owner_id: Mapped[str | None] = mapped_column(String(36), index=True)
    risk_stakeholder_id: Mapped[str | None] = mapped_column(String(36))
    risk_analyst_id: Mapped[str | None] = mapped_column(String(36))
    created_by: Mapped[str | None] = mapped_column(String(36))

    # -- relationships ----------------------------------------------------
    control_links: Mapped[list["RiskControlLink"]] = relationship(
        back_populates="risk", cascade="all, delete-orphan", lazy="selectin"
    )
    treatment_links: Mapped[list["RiskTreatmentLink"]] = relationship(
        back_populates="risk", cascade="all, delete-orphan", lazy="selectin"
    )
    phase_history: Mapped[list["RiskPhaseHistory"]] = relationship(
        back_populates="risk",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RiskPhaseHistory.created_at.desc()",
    )
    comments: Mapped[list["RiskComment"]] = relationship(
        back_populates="risk", cascade="all, delete-orphan", lazy="selectin"
    )

    # -- derived ----------------------------------------------------------
    @property
    def phase_number(self) -> int:
        return PHASE_NUMBERS.get(self.lifecycle_state, 1)

    @property
    def reported_score(self) -> int | None:
        """RES-2 / OUT-2: a risk under treatment reports its inherent score. Only
        a validated residual replaces it."""
        if self.residual_score_locked or self.residual_risk_score is None:
            return self.inherent_risk_score
        return self.residual_risk_score

    @property
    def reported_rating(self) -> str | None:
        if self.residual_score_locked or self.residual_rating is None:
            return self.inherent_rating
        return self.residual_rating

    @property
    def residual_gate_conditions(self) -> dict[str, bool]:
        return {
            "mitigations_implemented": self.gate_mitigations_implemented,
            "evidence_provided": self.gate_evidence_provided and bool(self.evidence_ref),
            "effectiveness_confirmed": self.gate_effectiveness_confirmed,
            "governance_approved": self.gate_governance_approved,
            "drift_tracked": self.gate_drift_tracked,
        }

    @property
    def preconditions(self) -> dict[str, bool]:
        return {
            "true_risk_confirmed": self.pre_true_risk_confirmed,
            "tier_assigned": self.pre_tier_assigned and bool(self.tier),
            "stakeholders_identified": self.pre_stakeholders_identified,
            "control_effectiveness_assessed": self.pre_ce_assessed,
        }

    @property
    def rating_drift(self) -> dict[str, str] | None:
        """Appetite bands are configuration, and a stored rating is a snapshot of
        the assessment that produced it (OUT-5 / RES-5). When the organisation
        moves its appetite bands, existing risks are not silently re-rated: the
        drift is surfaced here so the analyst re-assesses deliberately, exactly as
        they would for control effectiveness drift."""
        from app.engine.scoring import ScoringEngine

        for score, stored, field in (
            (self.inherent_risk_score, self.inherent_rating, "inherent"),
            (self.residual_risk_score, self.residual_rating, "residual"),
        ):
            if score is None or not stored:
                continue
            current = ScoringEngine.rating_for(score)
            if current != stored:
                return {
                    "field": field,
                    "score": str(score),
                    "assessed_as": stored,
                    "would_rate_today": current,
                }
        return None

    @property
    def statement(self) -> str | None:
        if not all([self.cause, self.threat_event, self.vulnerability, self.impact_statement]):
            return None
        return (
            "Because " + str(self.cause) + ", there is a risk that " + str(self.threat_event)
            + " exploits " + str(self.vulnerability) + ", resulting in " + str(self.impact_statement)
        )


class RiskPhaseHistory(Base, UUIDPrimaryKey):
    """Immutable phase transition trail. UPDATE and DELETE rejected by trigger."""

    __tablename__ = "risk_phase_history"

    risk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    from_phase: Mapped[int | None] = mapped_column(Integer)
    to_phase: Mapped[int] = mapped_column(Integer, nullable=False)
    gate: Mapped[str | None] = mapped_column(String(64))
    gate_evaluation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    changed_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    risk: Mapped[Risk] = relationship(back_populates="phase_history")


class RiskControlLink(Base, UUIDPrimaryKey):
    """Junction to control objectives. Snapshots the CE at link time (RES-5 /
    CALC-4) so later CE drift flags the risk rather than silently rescoring it."""

    __tablename__ = "risk_controls"
    __table_args__ = (UniqueConstraint("risk_id", "objective_id", name="uq_risk_controls"),)

    risk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objective_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_objectives.id", ondelete="CASCADE"), nullable=False
    )
    ce_at_assessment: Mapped[str | None] = mapped_column(String(32))
    linked_by: Mapped[str | None] = mapped_column(String(36))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    risk: Mapped[Risk] = relationship(back_populates="control_links")
    objective = relationship("ControlObjective", lazy="selectin")


class RiskTreatmentLink(Base, UUIDPrimaryKey):
    __tablename__ = "risk_treatments"
    __table_args__ = (UniqueConstraint("risk_id", "treatment_id", name="uq_risk_treatments"),)

    risk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    treatment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("treatments.id", ondelete="CASCADE"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_by: Mapped[str | None] = mapped_column(String(36))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    risk: Mapped[Risk] = relationship(back_populates="treatment_links")
    treatment = relationship("Treatment", lazy="selectin")


class RiskPolicyLink(Base, UUIDPrimaryKey):
    __tablename__ = "risk_policy_links"
    __table_args__ = (UniqueConstraint("risk_id", "policy_id", name="uq_risk_policy_links"),)

    risk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    linked_by: Mapped[str | None] = mapped_column(String(36))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RiskComment(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "risk_comments"

    risk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_comment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("risk_comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))

    risk: Mapped[Risk] = relationship(back_populates="comments")
