"""Deterministic risk scoring engine.

Implements the 5x5 model from the scoring specification. Given the same inputs it
produces the same output every time; there is no discretionary override and no
path by which a score can be set other than through this module.

Key rules enforced here:
  IMP-4  Impact is never adjusted by control effectiveness.
  LKH-3  Inherent likelihood is scored without CE adjustment.
  CE-4   Worst-case CE across deployments feeds scoring. Never average, never best.
  CE-5   Only Operating controls with non-expired CE contribute.
  CALC-3 CE resolves before residual likelihood. No circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from app.core.governance import CE_RATING_NAMES, RATING_NAMES, governance

# -- ratings ---------------------------------------------------------------
#
# Every threshold below comes from config/governance.yml. The engine holds the
# model; the configuration holds one organisation's expression of it.

RATING_BANDS: tuple[tuple[int, int, str], ...] = governance.rating_bands

RATING_ORDER = RATING_NAMES

APPETITE: dict[str, str] = governance.appetite

# Maximum acceptance window per rating, and the minimum approval level.
ACCEPTANCE_RULES: dict[str, dict[str, Any]] = governance.acceptance_rules

# Re-evaluation cadence in days, by rating.
REVIEW_CADENCE_DAYS: dict[str, int] = governance.review_cadence_days

# Cascade response SLA in business days when a linked control degrades.
CE_DEGRADATION_SLA_DAYS: dict[str, int] = governance.ce_degradation_sla_days

# -- control effectiveness -------------------------------------------------
#
# The CE vocabulary is fixed: it is the framework, not an organisational
# preference. What each rating buys you, and how long its evidence lasts, is
# configuration.

CE_UNVALIDATED = "CE-Unvalidated"
CE_LOW = "CE-Low"
CE_MEDIUM = "CE-Medium"
CE_HIGH = "CE-High"

CE_RATINGS = CE_RATING_NAMES

# Ordered weakest to strongest. Worst-case selection is a min over this order.
CE_STRENGTH = {CE_UNVALIDATED: 0, CE_LOW: 0, CE_MEDIUM: 1, CE_HIGH: 2}

# Maximum likelihood reduction permitted per CE rating (LKH-1).
CE_MAX_LIKELIHOOD_REDUCTION: dict[str, int] = governance.ce_likelihood_reduction

# CE expiry window by control test frequency (CE-6).
CE_EXPIRY_MONTHS: dict[str, int] = governance.ce_expiry_months

# Lifecycle states in which a control contributes CE to scoring (CE-5 / CINV-2).
CONTRIBUTING_LIFECYCLE_STATES = ("Operating",)


@dataclass(frozen=True)
class Score:
    impact: int
    likelihood: int
    score: int
    rating: str
    appetite: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "impact": self.impact,
            "likelihood": self.likelihood,
            "score": self.score,
            "rating": self.rating,
            "appetite": self.appetite,
        }


@dataclass(frozen=True)
class CEResolution:
    """Traceable output of CE resolution: the rating used, why, and which
    controls were considered versus excluded."""

    effective_ce: str
    max_likelihood_reduction: int
    contributing: tuple[dict[str, Any], ...]
    excluded: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "effective_ce": self.effective_ce,
            "max_likelihood_reduction": self.max_likelihood_reduction,
            "contributing": list(self.contributing),
            "excluded": list(self.excluded),
        }


class ScoringEngine:
    """Stateless. All methods are pure functions of their arguments."""

    # -- ratings ----------------------------------------------------------

    @staticmethod
    def rating_for(score: int) -> str:
        for low, high, rating in RATING_BANDS:
            if low <= score <= high:
                return rating
        raise ValueError("score out of range 1-25: " + str(score))

    @staticmethod
    def appetite_for(rating: str) -> str:
        return APPETITE.get(rating, "Unknown")

    @staticmethod
    def is_above_appetite(rating: str | None) -> bool:
        return APPETITE.get(rating or "", "") == "Above Appetite"

    # -- core calculation -------------------------------------------------

    @classmethod
    def compute(cls, impact: int | None, likelihood: int | None) -> Score | None:
        """CALC-1 / CALC-2. Returns None when either input is absent, so a
        partially scored risk never reports a rating."""
        if impact is None or likelihood is None:
            return None
        if not (1 <= impact <= 5) or not (1 <= likelihood <= 5):
            raise ValueError("impact and likelihood must each be 1-5")
        score = impact * likelihood
        rating = cls.rating_for(score)
        return Score(impact, likelihood, score, rating, cls.appetite_for(rating))

    @classmethod
    def inherent(cls, impact: int | None, likelihood: int | None) -> Score | None:
        """LKH-3: inherent likelihood carries no CE adjustment. The caller is
        responsible for scoring likelihood as if no controls were in place."""
        return cls.compute(impact, likelihood)

    @classmethod
    def residual(cls, impact: int | None, likelihood: int | None) -> Score | None:
        return cls.compute(impact, likelihood)

    # -- control effectiveness --------------------------------------------

    @staticmethod
    def ce_expired(
        assessed_at: date | None, frequency: str | None, today: date | None = None
    ) -> bool:
        """CE-6. No assessment date means expired by definition."""
        if assessed_at is None:
            return True
        months = CE_EXPIRY_MONTHS.get(frequency or "Annual", 24)
        today = today or date.today()
        # Approximate a month as 30 days; deterministic and adequate for expiry.
        return assessed_at + timedelta(days=months * 30) < today

    @classmethod
    def resolve_ce(
        cls,
        objectives: Iterable[Any],
        today: date | None = None,
        scope: set[str] | None = None,
    ) -> CEResolution:
        """STEP 1 of the CE resolution order.

        Walks each linked control objective down to its deployments, discards
        every deployment that does not qualify, then takes the worst case across
        whatever survives (CE-4 / CINV-6). Never averages, never takes best case.

        `scope` is the set of attack surface ids the risk concerns. When it is
        given and non-empty, a deployment on an asset outside it is discarded:
        a control that runs somewhere else does not reduce this exposure
        (RINV-14). When it is empty or None the filter does not apply, because
        an organisation-level risk legitimately names no single asset.

        Everything discarded is returned in `excluded` with the rule that
        discarded it, so an analyst can see why a control they expected to reduce
        the score did not.
        """
        today = today or date.today()
        scope = scope or None
        contributing: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []

        for objective in objectives:
            obj_entry = {
                "objective_id": str(getattr(objective, "id", "")),
                "reference": getattr(objective, "reference", None),
                "title": getattr(objective, "title", None),
                "lifecycle_state": getattr(objective, "lifecycle_state", None),
            }

            # CE-5 / CINV-2: only Operating objectives contribute at all.
            if getattr(objective, "lifecycle_state", None) not in CONTRIBUTING_LIFECYCLE_STATES:
                excluded.append(
                    {
                        **obj_entry,
                        "ce_rating": CE_UNVALIDATED,
                        "reason": "CE-5 / RINV-9: objective is "
                        + str(getattr(objective, "lifecycle_state", "unknown"))
                        + ", not Operating",
                    }
                )
                continue

            deployments = list(getattr(objective, "deployments", ()) or ())
            if not deployments:
                excluded.append(
                    {**obj_entry, "ce_rating": CE_UNVALIDATED, "reason": "no deployments"}
                )
                continue

            for dep in deployments:
                entry = {
                    **obj_entry,
                    "deployment_id": str(getattr(dep, "id", "")),
                    "deployment_reference": getattr(dep, "reference", None),
                    "deployment_status": getattr(dep, "deployment_status", None),
                    "ce_rating": getattr(dep, "ce_rating", CE_UNVALIDATED),
                    "asset": getattr(getattr(dep, "surface", None), "name", None),
                }
                # RINV-14: location before quality. A control that does not
                # run where the risk lives cannot reduce it, however good its
                # evidence is.
                if scope is not None:
                    dep_asset = getattr(dep, "attack_surface_id", None)
                    if dep_asset not in scope:
                        excluded.append(
                            {
                                **entry,
                                "reason": "RINV-14: deployed on "
                                + str(entry.get("asset") or "an asset")
                                + ", which is outside this risk's declared scope",
                            }
                        )
                        continue

                status = getattr(dep, "deployment_status", None)
                if status not in ("Active", "Degraded"):
                    excluded.append(
                        {**entry, "reason": "deployment status " + str(status) + " does not carry valid CE"}
                    )
                    continue
                if not getattr(dep, "ce_evidence_ref", None):
                    excluded.append({**entry, "reason": "CINV-1: no CE evidence reference"})
                    continue
                if cls.ce_expired(
                    getattr(dep, "ce_assessed_at", None),
                    getattr(dep, "test_frequency", None),
                    today,
                ):
                    excluded.append(
                        {
                            **entry,
                            "reason": "CE-6: evidence expired; auto-downgraded to CE-Unvalidated",
                        }
                    )
                    continue
                contributing.append(entry)

        if not contributing:
            return CEResolution(CE_UNVALIDATED, 0, (), tuple(excluded))

        effective = min(
            (c["ce_rating"] for c in contributing),
            key=lambda r: CE_STRENGTH.get(r, 0),
        )
        return CEResolution(
            effective,
            CE_MAX_LIKELIHOOD_REDUCTION.get(effective, 0),
            tuple(contributing),
            tuple(excluded),
        )

    @classmethod
    def max_residual_likelihood_reduction(cls, resolution: CEResolution) -> int:
        """STEP 2. The ceiling on how far residual likelihood may fall below
        inherent likelihood, given the resolved CE."""
        return resolution.max_likelihood_reduction

    @classmethod
    def validate_residual_likelihood(
        cls, inherent_likelihood: int, residual_likelihood: int, resolution: CEResolution
    ) -> tuple[bool, str]:
        """RES-4. A residual likelihood lower than the CE ceiling permits is
        rejected: the reduction must be earned by evidence, not asserted."""
        reduction = inherent_likelihood - residual_likelihood
        ceiling = resolution.max_likelihood_reduction
        if reduction < 0:
            return True, "residual likelihood exceeds inherent; permitted (risk has worsened)"
        if reduction > ceiling:
            return False, (
                "LKH-1: resolved control effectiveness is "
                + resolution.effective_ce
                + ", which permits a likelihood reduction of at most "
                + str(ceiling)
                + "; requested reduction is "
                + str(reduction)
            )
        return True, ""

    # -- downstream derivations -------------------------------------------

    @classmethod
    def next_review_date(cls, rating: str | None, from_date: date | None = None) -> date | None:
        if not rating:
            return None
        days = REVIEW_CADENCE_DAYS.get(rating)
        if days is None:
            return None
        return (from_date or date.today()) + timedelta(days=days)

    @classmethod
    def max_acceptance_expiry(cls, rating: str, from_date: date | None = None) -> date | None:
        """RINV-5 / acceptance rules. Critical returns None: not acceptable."""
        rule = ACCEPTANCE_RULES.get(rating)
        if rule is None or not rule["acceptable"]:
            return None
        return (from_date or date.today()) + timedelta(days=int(rule["max_days"]))

    @classmethod
    def acceptance_permitted(cls, rating: str | None) -> bool:
        if not rating:
            return False
        return bool(ACCEPTANCE_RULES.get(rating, {}).get("acceptable", False))

    @classmethod
    def required_approver(cls, rating: str | None) -> str | None:
        """Minimum organisational seniority permitted to accept at this rating."""
        if not rating:
            return None
        rule = ACCEPTANCE_RULES.get(rating)
        return rule["approver"] if rule else None

    @classmethod
    def max_renewals(cls, rating: str | None) -> int:
        """How many times an acceptance may be extended before the risk must be
        treated rather than carried again (codified-rules section 5.5)."""
        if not rating:
            return 0
        return int(ACCEPTANCE_RULES.get(rating, {}).get("max_renewals", 0))

    @classmethod
    def matrix(cls) -> list[dict[str, Any]]:
        """The 5x5 grid, generated rather than transcribed, for the UI heatmap."""
        cells = []
        for likelihood in range(5, 0, -1):
            for impact in range(1, 6):
                score = impact * likelihood
                cells.append(
                    {
                        "impact": impact,
                        "likelihood": likelihood,
                        "score": score,
                        "rating": cls.rating_for(score),
                    }
                )
        return cells
