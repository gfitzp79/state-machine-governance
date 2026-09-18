"""Domain 7: Threat Management.

STRIDE threat models bound bidirectionally to GRC state. The point of this module
is the feedback loop: a threat scenario is only "Mitigated" while the control that
mitigates it is genuinely operating. When that control fails, the scenario re-opens
and the model loses its sign-off.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.governance import SEVERITY_NAMES, governance
from app.core.model_base import Timestamped, UUIDPrimaryKey

THREAT_MODEL_STATES = (
    "Scope",
    "Decomposition",
    "Threat_Analysis",
    "Mitigation_Design",
    "Review",
    "Active",
    "Deprecated",
    "Abandoned",
)
SCENARIO_STATES = ("Identified", "Mitigated", "Accepted", "Promoted_To_Risk")
SEVERITIES = SEVERITY_NAMES
SEVERITY_ORDER = {name: i for i, name in enumerate(SEVERITY_NAMES)}

STRIDE_CATEGORIES = (
    "Spoofing",
    "Tampering",
    "Repudiation",
    "Information_Disclosure",
    "Denial_of_Service",
    "Elevation_of_Privilege",
)
COMPONENT_TYPES = (
    "Process",
    "Datastore",
    "External_Entity",
    "Data_Flow",
    "Trust_Boundary",
)
ASSURANCE_LEVELS = ("Fully_Mitigated", "Partially_Mitigated")

# Decomposition taxonomy, configuration-driven and validated at the service
# layer so an organisation can use its own data model without a migration.
DATA_CLASSIFICATIONS = governance.data_classifications
TRUST_ZONES = governance.trust_zones
EXPOSURE_LEVELS = governance.exposure_levels
DATA_TYPES = governance.data_types
RISK_LINK_TYPES = governance.risk_link_types


class ThreatModel(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "threat_models"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN " + str(THREAT_MODEL_STATES),
            name="ck_threat_models_lifecycle_state",
        ),
        # TINV-2 support: AppSec sign-off must come from someone other than the
        # system owner. Team membership, not a named individual.
        CheckConstraint(
            "appsec_signoff_by IS NULL OR appsec_signoff_by <> system_owner_id",
            name="ck_threat_models_appsec_independent",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    attack_surface_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("attack_surfaces.id", ondelete="RESTRICT"), nullable=False
    )
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="Scope")
    methodology: Mapped[str] = mapped_column(String(32), nullable=False, default="STRIDE")
    description: Mapped[str | None] = mapped_column(Text)

    system_owner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    appsec_partner_id: Mapped[str | None] = mapped_column(String(36))

    # TINV-2: both signatures required, and stripped by the re-open cascade.
    appsec_signoff_by: Mapped[str | None] = mapped_column(String(36))
    appsec_signoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_signoff_by: Mapped[str | None] = mapped_column(String(36))
    owner_signoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signoff_stripped_reason: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[str | None] = mapped_column(String(36))

    components: Mapped[list["ThreatComponent"]] = relationship(
        back_populates="model", cascade="all, delete-orphan", lazy="selectin"
    )
    scenarios: Mapped[list["ThreatScenario"]] = relationship(
        back_populates="model", cascade="all, delete-orphan", lazy="selectin"
    )
    surface = relationship("AttackSurface", lazy="selectin")

    @property
    def has_trust_boundary(self) -> bool:
        return any(c.component_type == "Trust_Boundary" for c in self.components)

    @property
    def unresolved_scenarios(self) -> list["ThreatScenario"]:
        """TINV-1: every scenario must reach a permitted end state.

        Those are: mitigated by a live control, locally accepted below the
        promotion threshold, or carried by the risk register. The register
        carrying it is the same governance outcome whether the record was minted
        by promotion or already existed and is referenced (TINV-8), so both
        count.
        """
        return [s for s in self.scenarios if not s.is_resolved]

    @property
    def unhandled_high_severity(self) -> list["ThreatScenario"]:
        return [
            s
            for s in self.scenarios
            if s.status == "Identified" and SEVERITY_ORDER[s.inherent_severity] >= 2
        ]

    @property
    def fully_signed_off(self) -> bool:
        return bool(self.appsec_signoff_by) and bool(self.owner_signoff_by)


class ThreatComponent(Base, UUIDPrimaryKey, Timestamped):
    """A DFD element: process, datastore, external entity, flow, or boundary.

    A component is not just a box on a diagram. What data it handles and where it
    sits determine what a compromise costs and which boundary it crosses, so both
    are first-class attributes rather than prose in a description. TINV-9 and
    TINV-11 both read them.
    """

    __tablename__ = "threat_components"
    __table_args__ = (
        CheckConstraint(
            "component_type IN " + str(COMPONENT_TYPES), name="ck_threat_components_type"
        ),
    )

    threat_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("threat_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    component_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # -- what it handles --------------------------------------------------
    data_classification: Mapped[str | None] = mapped_column(String(48))
    data_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # -- where it sits ----------------------------------------------------
    trust_zone: Mapped[str | None] = mapped_column(String(48))
    exposure: Mapped[str | None] = mapped_column(String(48))
    # A component may live on an asset other than the model's primary one, which
    # is exactly where cross-boundary flows get interesting.
    attack_surface_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("attack_surfaces.id", ondelete="SET NULL")
    )
    # For Data_Flow components: which zones it bridges.
    source_component_id: Mapped[str | None] = mapped_column(String(36))
    target_component_id: Mapped[str | None] = mapped_column(String(36))

    model: Mapped[ThreatModel] = relationship(back_populates="components")
    surface = relationship("AttackSurface", lazy="selectin")

    @property
    def is_sensitive(self) -> bool:
        """At or above the configured classification threshold."""
        return governance.is_sensitive(self.data_classification)

    @property
    def trust_level(self) -> int | None:
        return governance.trust_levels.get(self.trust_zone or "")

    @property
    def crosses_boundary(self) -> bool:
        """A flow between zones of differing trust is a boundary crossing."""
        return self.component_type in ("Data_Flow", "Trust_Boundary")


class ThreatScenario(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "threat_scenarios"
    __table_args__ = (
        CheckConstraint("status IN " + str(SCENARIO_STATES), name="ck_threat_scenarios_status"),
        CheckConstraint(
            "inherent_severity IN " + str(SEVERITIES), name="ck_threat_scenarios_severity"
        ),
        CheckConstraint(
            "category IN " + str(STRIDE_CATEGORIES), name="ck_threat_scenarios_category"
        ),
        # TINV-3 at the schema layer: nothing above Low is accepted locally.
        CheckConstraint(
            "status <> 'Accepted' OR inherent_severity = 'Low'",
            name="ck_threat_scenarios_no_local_acceptance_above_low",
        ),
        # TINV-5: a Low acceptance always carries an expiry.
        CheckConstraint(
            "status <> 'Accepted' OR acceptance_expiry IS NOT NULL",
            name="ck_threat_scenarios_acceptance_time_bound",
        ),
        # A promotion always names the risk it produced.
        CheckConstraint(
            "status <> 'Promoted_To_Risk' OR promoted_risk_id IS NOT NULL",
            name="ck_threat_scenarios_promotion_linked",
        ),
    )

    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    threat_model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("threat_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("threat_components.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    inherent_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Identified")

    remediation_target_date: Mapped[date | None] = mapped_column(Date)
    acceptance_expiry: Mapped[date | None] = mapped_column(Date)
    acceptance_rationale: Mapped[str | None] = mapped_column(Text)
    promoted_risk_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("risks.id", ondelete="SET NULL")
    )
    reopened_reason: Mapped[str | None] = mapped_column(Text)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(36))

    # Rationale for the most recent status change. A status change is a decision,
    # and a decision without a reason is not auditable (TINV-10).
    status_rationale: Mapped[str | None] = mapped_column(Text)

    model: Mapped[ThreatModel] = relationship(back_populates="scenarios")
    component: Mapped[ThreatComponent] = relationship(lazy="selectin")
    mitigations: Mapped[list["ThreatMitigationLink"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", lazy="selectin"
    )
    comments: Mapped[list["ThreatScenarioComment"]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ThreatScenarioComment.created_at",
    )
    evidence: Mapped[list["ThreatScenarioEvidence"]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ThreatScenarioEvidence.created_at.desc()",
    )
    risk_links: Mapped[list["ThreatScenarioRiskLink"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def severity_rank(self) -> int:
        return SEVERITY_ORDER.get(self.inherent_severity, 0)

    @property
    def has_partial_mitigation(self) -> bool:
        """TM-PARTIAL: any link asserting only partial coverage.

        A scenario with a partial link is not mitigated. The UI may derive a
        "Partially Mitigated" display state from the link table, but it is not a
        status value: partial coverage is an open threat with work in progress.
        """
        return any(
            link.effectiveness_assurance == "Partially_Mitigated"
            for link in self.mitigations
        )

    @property
    def fully_mitigated(self) -> bool:
        """Mitigated requires at least one link and no partial ones (TM-PARTIAL)."""
        return bool(self.mitigations) and not self.has_partial_mitigation

    @property
    def carried_by_register(self) -> bool:
        """The risk register demonstrably holds this exposure.

        True when the scenario was promoted, or when it references an existing
        risk under a link type configured as resolving. A threat that maps onto
        an exposure the register already carries is governed; minting a second
        record for it would corrupt the register rather than improve it.
        """
        if self.status == "Promoted_To_Risk" or self.promoted_risk_id:
            return True
        resolving = governance.scenario_resolving_link_types
        return any(link.link_type in resolving for link in self.risk_links)

    @property
    def is_resolved(self) -> bool:
        """TINV-1: has this scenario reached a permitted end state?"""
        if self.status in ("Mitigated", "Accepted"):
            return True
        return self.carried_by_register

    @property
    def requires_promotion(self) -> bool:
        """TINV-3: at or above the promotion threshold, local acceptance is not a
        legal end state, so the register is the only remaining one."""
        return self.severity_rank >= governance.minimum_promotable_severity_rank


class ThreatMitigationLink(Base, UUIDPrimaryKey):
    """Maps a scenario to the deployed control that mitigates it (TINV-4). The
    link is to a deployment, not an objective, because a control only mitigates a
    threat where it actually runs."""

    __tablename__ = "threat_mitigation_links"
    __table_args__ = (
        UniqueConstraint("scenario_id", "deployment_id", name="uq_threat_mitigation"),
        CheckConstraint(
            "effectiveness_assurance IN " + str(ASSURANCE_LEVELS),
            name="ck_threat_mitigation_assurance",
        ),
    )

    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("threat_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deployment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_deployments.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    effectiveness_assurance: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Fully_Mitigated"
    )
    linked_by: Mapped[str | None] = mapped_column(String(36))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scenario: Mapped[ThreatScenario] = relationship(back_populates="mitigations")
    deployment = relationship("ControlDeployment", lazy="selectin")


class ThreatScenarioComment(Base, UUIDPrimaryKey, Timestamped):
    """Threaded discussion on a scenario. Threat modelling is a conversation
    between AppSec, engineering and risk; the conversation is part of the record."""

    __tablename__ = "threat_scenario_comments"

    scenario_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threat_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_comment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("threat_scenario_comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))

    scenario: Mapped["ThreatScenario"] = relationship(back_populates="comments")


class ThreatScenarioEvidence(Base, UUIDPrimaryKey):
    """Immutable evidence attached to a scenario (TINV-10).

    Append-only, enforced by database trigger, for the same reason control test
    history is: evidence that can be edited after the fact is not evidence.
    Superseding an entry creates a new record referencing the original.
    """

    __tablename__ = "threat_scenario_evidence"

    scenario_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threat_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # A reference rather than a blob: a scan result, a design doc, a test report,
    # a ticket. Storage of the artefact itself is the organisation's concern.
    evidence_ref: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str | None] = mapped_column(String(48))
    notes: Mapped[str | None] = mapped_column(Text)
    # What this evidence was offered in support of, so an auditor can see whether
    # the claim and the proof match.
    supports: Mapped[str | None] = mapped_column(String(48))
    supersedes_id: Mapped[str | None] = mapped_column(String(36))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scenario: Mapped["ThreatScenario"] = relationship(back_populates="evidence")


class ThreatScenarioRiskLink(Base, UUIDPrimaryKey):
    """Scenario to existing risk record.

    Most threats on a mature system map to risks that already exist. Minting a
    new register entry for each one corrupts the register, so linking and
    promoting are distinct operations: exactly one link type creates a risk, and
    the rest reference one (TINV-8).
    """

    __tablename__ = "threat_scenario_risk_links"
    __table_args__ = (
        UniqueConstraint("scenario_id", "risk_id", name="uq_threat_scenario_risk"),
    )

    scenario_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threat_scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_type: Mapped[str] = mapped_column(String(48), nullable=False, default="Represents")
    rationale: Mapped[str | None] = mapped_column(Text)
    linked_by: Mapped[str | None] = mapped_column(String(36))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scenario: Mapped["ThreatScenario"] = relationship(back_populates="risk_links")
    risk = relationship("Risk", lazy="selectin")
