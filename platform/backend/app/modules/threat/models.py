"""Domain 7: Threat Management.

STRIDE threat models bound bidirectionally to GRC state. The point of this module
is the feedback loop: a threat scenario is only "Mitigated" while the control that
mitigates it is genuinely operating. When that control fails, the scenario re-opens
and the model loses its sign-off.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.governance import SEVERITY_NAMES
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
        """TINV-1: every scenario must resolve to mitigation, a valid local Low
        acceptance, or promotion to the risk register."""
        return [s for s in self.scenarios if s.status == "Identified"]

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
    """A DFD element: process, datastore, external entity, flow, or boundary."""

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

    model: Mapped[ThreatModel] = relationship(back_populates="components")


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

    model: Mapped[ThreatModel] = relationship(back_populates="scenarios")
    component: Mapped[ThreatComponent] = relationship(lazy="selectin")
    mitigations: Mapped[list["ThreatMitigationLink"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def severity_rank(self) -> int:
        return SEVERITY_ORDER.get(self.inherent_severity, 0)

    @property
    def requires_promotion(self) -> bool:
        """TINV-3: Medium and above cannot be locally accepted, so an unmitigated
        scenario at that severity has only one legal resting place."""
        return self.severity_rank >= 1


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
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    scenario: Mapped[ThreatScenario] = relationship(back_populates="mitigations")
    deployment = relationship("ControlDeployment", lazy="selectin")
