"""Governance configuration loader.

Reads `config/governance.yml` and exposes it as a validated object the engine and
modules consult instead of hardcoded constants. This is the seam between the
framework, which is code, and the operating model, which is configuration.

Validation is deliberately strict and runs at import time. A misconfigured
appetite band is a governance defect, not a runtime inconvenience, so the
application refuses to start rather than scoring risks against a broken model.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Band names are referenced by name in the invariants and in CHECK constraints
# (RINV-5 and ck_risks_critical_never_accepted, among others), so they are fixed.
# Boundaries are configurable; names are not.
RATING_NAMES = ("Low", "Moderate-Low", "Moderate", "High", "Critical")

# Likewise fixed: the scale, the CE vocabulary and the treatment decisions are
# the framework itself rather than an expression of one organisation's model.
SCALE_MIN, SCALE_MAX = 1, 5
CE_RATING_NAMES = ("CE-Unvalidated", "CE-Low", "CE-Medium", "CE-High")
TREATMENT_STRATEGIES = ("Accept", "Mitigate", "Transfer", "Avoid")
SEVERITY_NAMES = ("Low", "Medium", "High", "Critical")

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "governance.yml"


class ConfigError(Exception):
    """Raised at boot when the governance configuration is unusable."""


def _require(data: dict, path: str) -> Any:
    """Fetch a dotted path, failing with a message that names the missing key."""
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError("governance.yml is missing required key: " + path)
        node = node[part]
    return node


class GovernanceConfig:
    """Validated, read-only view of governance.yml."""

    def __init__(self, raw: dict[str, Any], source: str) -> None:
        self.raw = raw
        self.source = source
        self._validate()

    # -- organisation -----------------------------------------------------

    @property
    def organisation_name(self) -> str:
        return str(self.raw.get("organisation", {}).get("name", "Your Organisation"))

    @property
    def organisation_short_name(self) -> str:
        org = self.raw.get("organisation", {})
        return str(org.get("short_name") or org.get("name", "Org"))

    @property
    def organisation_tagline(self) -> str:
        return str(self.raw.get("organisation", {}).get("tagline", "Governance platform"))

    # -- scoring ----------------------------------------------------------

    @property
    def rating_bands(self) -> tuple[tuple[int, int, str], ...]:
        """Ordered high to low, as (min, max, rating)."""
        bands = _require(self.raw, "scoring.rating_bands")
        ordered = sorted(bands, key=lambda b: int(b["min"]), reverse=True)
        return tuple((int(b["min"]), int(b["max"]), str(b["rating"])) for b in ordered)

    @property
    def appetite(self) -> dict[str, str]:
        return {
            str(b["rating"]): str(b.get("appetite", "Unknown"))
            for b in _require(self.raw, "scoring.rating_bands")
        }

    @property
    def review_cadence_days(self) -> dict[str, int]:
        return {k: int(v) for k, v in _require(self.raw, "scoring.review_cadence_days").items()}

    # -- acceptance -------------------------------------------------------

    @property
    def acceptance_rules(self) -> dict[str, dict[str, Any]]:
        rules = _require(self.raw, "acceptance")
        return {
            rating: {
                "acceptable": bool(rule.get("acceptable", True)),
                "max_days": int(rule.get("max_days") or 0),
                "approver": rule.get("approver"),
            }
            for rating, rule in rules.items()
        }

    # -- control effectiveness --------------------------------------------

    @property
    def ce_likelihood_reduction(self) -> dict[str, int]:
        return {
            k: int(v)
            for k, v in _require(self.raw, "control_effectiveness.likelihood_reduction").items()
        }

    @property
    def ce_expiry_months(self) -> dict[str, int]:
        return {
            k: int(v) for k, v in _require(self.raw, "control_effectiveness.expiry_months").items()
        }

    @property
    def ce_degradation_sla_days(self) -> dict[str, int]:
        return {
            k: int(v)
            for k, v in _require(self.raw, "control_effectiveness.degradation_sla_days").items()
        }

    # -- taxonomy ---------------------------------------------------------

    @property
    def risk_tiers(self) -> tuple[str, ...]:
        return tuple(str(t["id"]) for t in _require(self.raw, "risk.tiers"))

    @property
    def risk_tier_detail(self) -> list[dict[str, Any]]:
        return [dict(t) for t in _require(self.raw, "risk.tiers")]

    @property
    def intake_sources(self) -> tuple[str, ...]:
        return tuple(str(s) for s in _require(self.raw, "risk.intake_sources"))

    @property
    def control_families(self) -> tuple[str, ...]:
        return tuple(str(f) for f in _require(self.raw, "controls.families"))

    @property
    def control_types(self) -> tuple[str, ...]:
        return tuple(str(t) for t in _require(self.raw, "controls.types"))

    @property
    def test_frequencies(self) -> tuple[str, ...]:
        return tuple(str(f) for f in _require(self.raw, "controls.test_frequencies"))

    @property
    def asset_tiers(self) -> tuple[str, ...]:
        return tuple(str(t) for t in _require(self.raw, "controls.asset_tiers"))

    @property
    def policy_types(self) -> tuple[str, ...]:
        return tuple(str(t) for t in _require(self.raw, "policy.types"))

    @property
    def review_cycles(self) -> tuple[str, ...]:
        return tuple(str(c) for c in _require(self.raw, "policy.review_cycles"))

    @property
    def compliance_frameworks(self) -> tuple[str, ...]:
        return tuple(str(f) for f in _require(self.raw, "policy.compliance_frameworks"))

    @property
    def annual_audit_frameworks(self) -> tuple[str, ...]:
        return tuple(str(f) for f in _require(self.raw, "policy.annual_audit_frameworks"))

    # -- windows ----------------------------------------------------------

    @property
    def exception_max_days(self) -> int:
        return int(_require(self.raw, "policy.exceptions.max_days"))

    @property
    def exception_extended_max_days(self) -> int:
        return int(_require(self.raw, "policy.exceptions.extended_max_days"))

    @property
    def exception_review_trigger_count(self) -> int:
        return int(_require(self.raw, "policy.exceptions.review_trigger_count"))

    @property
    def exception_expiry_warning_days(self) -> int:
        return int(_require(self.raw, "policy.exceptions.expiry_warning_days"))

    @property
    def threat_local_acceptance_max_days(self) -> int:
        return int(_require(self.raw, "threat.local_acceptance_max_days"))

    @property
    def minimum_promotable_severity(self) -> str:
        return str(_require(self.raw, "threat.minimum_promotable_severity"))

    @property
    def minimum_promotable_severity_rank(self) -> int:
        return SEVERITY_NAMES.index(self.minimum_promotable_severity)

    @property
    def threat_auto_promotion_days(self) -> int:
        return int(_require(self.raw, "threat.auto_promotion_days"))

    @property
    def control_failure_escalation_days(self) -> int:
        return int(_require(self.raw, "escalation.control_failure_escalation_days"))

    @property
    def policy_realignment_days(self) -> int:
        return int(_require(self.raw, "escalation.policy_realignment_days"))

    @property
    def policy_remapping_days(self) -> int:
        return int(_require(self.raw, "escalation.policy_remapping_days"))

    @property
    def control_retirement_reassessment_days(self) -> int:
        return int(_require(self.raw, "escalation.control_retirement_reassessment_days"))

    # -- roles ------------------------------------------------------------

    @property
    def role_definitions(self) -> list[dict[str, Any]]:
        return [dict(r) for r in _require(self.raw, "roles.definitions")]

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(str(r["id"]) for r in self.role_definitions)

    @property
    def role_levels(self) -> dict[str, int]:
        return {str(r["id"]): int(r["level"]) for r in self.role_definitions}

    @property
    def seniority_ladder(self) -> tuple[str, ...]:
        return tuple(str(s) for s in _require(self.raw, "roles.seniority_ladder"))

    @property
    def ownership_by_severity(self) -> dict[str, str]:
        return {
            k: str(v) for k, v in _require(self.raw, "roles.ownership_by_severity").items()
        }

    # -- treatment --------------------------------------------------------

    @property
    def loe_bands(self) -> tuple[str, ...]:
        return tuple(str(b) for b in _require(self.raw, "treatment.loe_bands"))

    @property
    def checkin_frequencies(self) -> tuple[str, ...]:
        return tuple(str(f) for f in _require(self.raw, "treatment.checkin_frequencies"))

    @property
    def checkin_statuses(self) -> tuple[str, ...]:
        return tuple(str(s) for s in _require(self.raw, "treatment.checkin_statuses"))

    # -- validation -------------------------------------------------------

    def _validate(self) -> None:
        errors: list[str] = []

        # Rating bands must use the reserved names and tile 1-25 exactly once.
        bands = self.rating_bands
        names = {b[2] for b in bands}
        if names != set(RATING_NAMES):
            errors.append(
                "scoring.rating_bands must define exactly these five bands: "
                + ", ".join(RATING_NAMES)
                + ". Found: "
                + ", ".join(sorted(names))
                + ". Band boundaries are configurable; band names are not, because "
                "the invariants and database constraints reference them by name."
            )
        else:
            covered: dict[int, int] = {}
            for low, high, rating in bands:
                if low > high:
                    errors.append(
                        "scoring.rating_bands: " + rating + " has min " + str(low)
                        + " above max " + str(high)
                    )
                    continue
                for score in range(low, high + 1):
                    covered[score] = covered.get(score, 0) + 1
            missing = [s for s in range(SCALE_MIN, SCALE_MAX * SCALE_MAX + 1) if s not in covered]
            overlapping = [s for s, n in covered.items() if n > 1]
            out_of_range = [s for s in covered if not 1 <= s <= 25]
            if missing:
                errors.append(
                    "scoring.rating_bands leaves these scores unrated: "
                    + ", ".join(str(s) for s in missing)
                    + ". Bands must cover 1-25 with no gaps."
                )
            if overlapping:
                errors.append(
                    "scoring.rating_bands assigns these scores to more than one band: "
                    + ", ".join(str(s) for s in sorted(overlapping))
                )
            if out_of_range:
                errors.append(
                    "scoring.rating_bands covers scores outside 1-25: "
                    + ", ".join(str(s) for s in sorted(out_of_range))
                )

        # Every band needs an acceptance rule and a review cadence.
        for rating in RATING_NAMES:
            if rating not in self.acceptance_rules:
                errors.append("acceptance is missing a rule for the " + rating + " band")
            if rating not in self.review_cadence_days:
                errors.append(
                    "scoring.review_cadence_days is missing an entry for the "
                    + rating
                    + " band"
                )

        # An acceptable band with a zero window would silently refuse everything.
        for rating, rule in self.acceptance_rules.items():
            if rule["acceptable"] and rule["max_days"] <= 0:
                errors.append(
                    "acceptance." + rating + " is marked acceptable but has a max_days of "
                    + str(rule["max_days"])
                    + ". Give it a positive window or set acceptable to false."
                )

        # CE vocabulary is fixed, and a reduction above 4 is meaningless on a
        # 1-5 scale.
        reduction = self.ce_likelihood_reduction
        for ce in CE_RATING_NAMES:
            if ce not in reduction:
                errors.append(
                    "control_effectiveness.likelihood_reduction is missing " + ce
                )
        for ce, value in reduction.items():
            if ce not in CE_RATING_NAMES:
                errors.append(
                    "control_effectiveness.likelihood_reduction has an unknown rating: "
                    + ce
                    + ". Valid ratings are " + ", ".join(CE_RATING_NAMES)
                )
            if not 0 <= value <= SCALE_MAX - 1:
                errors.append(
                    "control_effectiveness.likelihood_reduction." + ce + " is " + str(value)
                    + "; it must be between 0 and " + str(SCALE_MAX - 1)
                    + " on a 1-" + str(SCALE_MAX) + " scale."
                )
        if reduction.get("CE-Unvalidated", 0) != 0:
            errors.append(
                "control_effectiveness.likelihood_reduction.CE-Unvalidated must be 0. "
                "Unvalidated evidence cannot buy a likelihood reduction (RINV-9)."
            )

        # Every test frequency needs an expiry window, or CE-6 cannot be applied.
        for frequency in self.test_frequencies:
            if frequency not in self.ce_expiry_months:
                errors.append(
                    "control_effectiveness.expiry_months is missing an entry for the "
                    + frequency
                    + " test frequency"
                )

        # Non-empty taxonomies.
        for path, values in (
            ("controls.families", self.control_families),
            ("controls.types", self.control_types),
            ("controls.test_frequencies", self.test_frequencies),
            ("controls.asset_tiers", self.asset_tiers),
            ("risk.tiers", self.risk_tiers),
            ("risk.intake_sources", self.intake_sources),
            ("policy.types", self.policy_types),
            ("policy.review_cycles", self.review_cycles),
            ("policy.compliance_frameworks", self.compliance_frameworks),
            ("roles.definitions", self.roles),
            ("roles.seniority_ladder", self.seniority_ladder),
        ):
            if not values:
                errors.append(path + " cannot be empty")

        # Cross-references must resolve.
        for framework in self.annual_audit_frameworks:
            if framework not in self.compliance_frameworks:
                errors.append(
                    "policy.annual_audit_frameworks lists " + framework
                    + ", which is not in policy.compliance_frameworks"
                )
        for rating, seniority in self.ownership_by_severity.items():
            if rating not in RATING_NAMES:
                errors.append(
                    "roles.ownership_by_severity has an unknown rating: " + rating
                )
            if seniority not in self.seniority_ladder:
                errors.append(
                    "roles.ownership_by_severity." + rating + " requires " + seniority
                    + ", which is not in roles.seniority_ladder"
                )

        # Roles the platform itself depends on.
        for essential in ("Admin", "CISO"):
            if essential not in self.roles:
                errors.append(
                    "roles.definitions must include " + essential
                    + "; the platform's own authorisation depends on it"
                )
        if self.role_levels.get("CISO", 0) < max(
            (v for k, v in self.role_levels.items() if k != "Admin"), default=0
        ):
            errors.append(
                "roles.definitions: CISO must hold the highest level of any "
                "non-Admin role, because PINV-5 requires policy approval at "
                "CISO or above."
            )

        if self.minimum_promotable_severity not in SEVERITY_NAMES:
            errors.append(
                "threat.minimum_promotable_severity must be one of "
                + ", ".join(SEVERITY_NAMES)
            )

        if self.exception_extended_max_days < self.exception_max_days:
            errors.append(
                "policy.exceptions.extended_max_days must be at least max_days"
            )

        if errors:
            raise ConfigError(
                "governance configuration is invalid (" + self.source + "):\n  - "
                + "\n  - ".join(errors)
            )

    # -- serialisation ----------------------------------------------------

    def public(self) -> dict[str, Any]:
        """Served to the UI so the client renders your taxonomy, not a copy of
        the defaults baked into the bundle."""
        return {
            "organisation": {
                "name": self.organisation_name,
                "short_name": self.organisation_short_name,
                "tagline": self.organisation_tagline,
            },
            "ratings": list(RATING_NAMES),
            "rating_bands": [
                {"rating": r, "min": lo, "max": hi, "appetite": self.appetite.get(r)}
                for lo, hi, r in self.rating_bands
            ],
            "acceptance_rules": self.acceptance_rules,
            "review_cadence_days": self.review_cadence_days,
            "ce_ratings": list(CE_RATING_NAMES),
            "ce_likelihood_reduction": self.ce_likelihood_reduction,
            "ce_expiry_months": self.ce_expiry_months,
            "ce_degradation_sla_days": self.ce_degradation_sla_days,
            "treatment_strategies": list(TREATMENT_STRATEGIES),
            "risk": {
                "tiers": self.risk_tier_detail,
                "intake_sources": list(self.intake_sources),
            },
            "controls": {
                "families": list(self.control_families),
                "types": list(self.control_types),
                "test_frequencies": list(self.test_frequencies),
                "asset_tiers": list(self.asset_tiers),
            },
            "policy": {
                "types": list(self.policy_types),
                "review_cycles": list(self.review_cycles),
                "compliance_frameworks": list(self.compliance_frameworks),
                "annual_audit_frameworks": list(self.annual_audit_frameworks),
                "exception_max_days": self.exception_max_days,
                "exception_extended_max_days": self.exception_extended_max_days,
            },
            "threat": {
                "local_acceptance_max_days": self.threat_local_acceptance_max_days,
                "minimum_promotable_severity": self.minimum_promotable_severity,
                "severities": list(SEVERITY_NAMES),
            },
            "roles": {
                "definitions": self.role_definitions,
                "levels": self.role_levels,
                "seniority_ladder": list(self.seniority_ladder),
                "ownership_by_severity": self.ownership_by_severity,
            },
            "treatment": {
                "loe_bands": list(self.loe_bands),
                "checkin_frequencies": list(self.checkin_frequencies),
                "checkin_statuses": list(self.checkin_statuses),
            },
            "escalation": {
                "control_failure_escalation_days": self.control_failure_escalation_days,
                "policy_realignment_days": self.policy_realignment_days,
                "policy_remapping_days": self.policy_remapping_days,
                "control_retirement_reassessment_days": (
                    self.control_retirement_reassessment_days
                ),
            },
        }


@lru_cache
def load_governance() -> GovernanceConfig:
    path = Path(os.environ.get("GOVERNANCE_CONFIG", str(DEFAULT_CONFIG_PATH)))
    if not path.exists():
        raise ConfigError(
            "governance configuration not found at " + str(path) + ". "
            "Set GOVERNANCE_CONFIG or restore config/governance.yml."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError("could not parse " + str(path) + ": " + str(exc)) from exc
    if not isinstance(raw, dict):
        raise ConfigError(str(path) + " must contain a YAML mapping at the top level")
    return GovernanceConfig(raw, str(path))


governance = load_governance()
