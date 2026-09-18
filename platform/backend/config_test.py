"""Governance configuration tests.

A misconfigured operating model is a governance defect. These tests prove the
loader refuses one at boot rather than scoring risks against a broken model, and
that a valid change actually takes effect end to end.

    docker compose exec api python config_test.py
"""

from __future__ import annotations

import copy
import sys

import yaml

from app.core.governance import ConfigError, GovernanceConfig, load_governance

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: object = "") -> None:
    if condition:
        PASSED.append(name)
        print("  PASS  " + name)
    else:
        FAILED.append(name)
        print("  FAIL  " + name + ("  ->  " + str(detail) if detail else ""))


def section(title: str) -> None:
    print("\n" + title)
    print("-" * len(title))


def build(mutate) -> tuple[GovernanceConfig | None, str]:
    """Apply a mutation to the shipped config and try to construct it."""
    raw = copy.deepcopy(load_governance().raw)
    mutate(raw)
    try:
        return GovernanceConfig(raw, "test"), ""
    except ConfigError as exc:
        return None, str(exc)


def rejects(name: str, mutate, expected_fragment: str) -> None:
    config, message = build(mutate)
    if config is not None:
        check(name, False, "the invalid configuration was accepted")
        return
    check(name, expected_fragment.lower() in message.lower(), message.splitlines()[:3])


def accepts(name: str, mutate, assertion=None) -> None:
    config, message = build(mutate)
    if config is None:
        check(name, False, message.splitlines()[:3])
        return
    check(name, assertion(config) if assertion else True)


def main() -> int:
    section("The shipped configuration is valid")
    base = load_governance()
    check("config/governance.yml loads", base is not None)
    check("five rating bands", len(base.rating_bands) == 5, len(base.rating_bands))
    check("bands cover 1-25", base.rating_bands[-1][0] == 1 and base.rating_bands[0][1] == 25)
    check("Critical is not acceptable", not base.acceptance_rules["Critical"]["acceptable"])

    section("Invalid appetite models are refused at boot")

    def gap(raw):
        raw["scoring"]["rating_bands"][2]["min"] = 11  # leaves score 10 unrated

    rejects("a gap in the bands is refused", gap, "leaves these scores unrated")

    def overlap(raw):
        raw["scoring"]["rating_bands"][1]["min"] = 10  # High now overlaps Moderate

    rejects("overlapping bands are refused", overlap, "more than one band")

    def renamed(raw):
        raw["scoring"]["rating_bands"][0]["rating"] = "Catastrophic"

    rejects("renaming a band is refused", renamed, "band names are not")

    def acceptable_but_zero(raw):
        raw["acceptance"]["High"]["max_days"] = 0

    rejects(
        "an acceptable band with no window is refused",
        acceptable_but_zero,
        "give it a positive window",
    )

    section("Invalid control effectiveness models are refused")

    def unvalidated_buys_reduction(raw):
        raw["control_effectiveness"]["likelihood_reduction"]["CE-Unvalidated"] = 1

    rejects(
        "CE-Unvalidated cannot buy a reduction",
        unvalidated_buys_reduction,
        "must be 0",
    )

    def reduction_too_large(raw):
        raw["control_effectiveness"]["likelihood_reduction"]["CE-High"] = 9

    rejects("an out-of-scale reduction is refused", reduction_too_large, "between 0 and 4")

    def unknown_ce(raw):
        raw["control_effectiveness"]["likelihood_reduction"]["CE-Perfect"] = 3

    rejects("an unknown CE rating is refused", unknown_ce, "unknown rating")

    def missing_expiry(raw):
        del raw["control_effectiveness"]["expiry_months"]["Quarterly"]

    rejects(
        "a test frequency with no expiry window is refused",
        missing_expiry,
        "expiry_months is missing",
    )

    section("Broken cross-references are refused")

    def dangling_framework(raw):
        raw["policy"]["annual_audit_frameworks"].append("MADE-UP-STANDARD")

    rejects(
        "an annual-audit framework not in the framework list is refused",
        dangling_framework,
        "not in policy.compliance_frameworks",
    )

    def dangling_seniority(raw):
        raw["roles"]["ownership_by_severity"]["Critical"] = "Supreme_Overlord"

    rejects(
        "an ownership level outside the ladder is refused",
        dangling_seniority,
        "not in roles.seniority_ladder",
    )

    def no_ciso(raw):
        raw["roles"]["definitions"] = [
            r for r in raw["roles"]["definitions"] if r["id"] != "CISO"
        ]

    rejects("removing CISO is refused", no_ciso, "must include CISO")

    def demoted_ciso(raw):
        for role in raw["roles"]["definitions"]:
            if role["id"] == "CISO":
                role["level"] = 1

    rejects(
        "demoting CISO below other roles is refused",
        demoted_ciso,
        "highest level of any",
    )

    def empty_families(raw):
        raw["controls"]["families"] = []

    rejects("an empty control taxonomy is refused", empty_families, "cannot be empty")

    def missing_key(raw):
        del raw["scoring"]["review_cadence_days"]

    rejects("a missing required key is named", missing_key, "review_cadence_days")

    section("Valid changes take effect")

    def tighten_appetite(raw):
        # Move the Critical boundary down: 16-25 becomes Critical.
        raw["scoring"]["rating_bands"][0]["min"] = 16
        raw["scoring"]["rating_bands"][1]["min"] = 12
        raw["scoring"]["rating_bands"][1]["max"] = 15
        raw["scoring"]["rating_bands"][2]["max"] = 11

    accepts(
        "a tightened appetite is accepted",
        tighten_appetite,
        lambda c: c.rating_bands[0] == (16, 25, "Critical"),
    )

    def refuse_high_acceptance(raw):
        raw["acceptance"]["High"]["acceptable"] = False
        raw["acceptance"]["High"]["max_days"] = 0

    accepts(
        "refusing acceptance at High is accepted",
        refuse_high_acceptance,
        lambda c: not c.acceptance_rules["High"]["acceptable"],
    )

    def own_families(raw):
        raw["controls"]["families"] = ["CC", "AC", "CM", "SC"]

    accepts(
        "a replacement control taxonomy is accepted",
        own_families,
        lambda c: c.control_families == ("CC", "AC", "CM", "SC"),
    )

    def own_roles(raw):
        raw["roles"]["definitions"].append(
            {"id": "Data_Protection_Officer", "level": 4, "description": "DPO"}
        )

    accepts(
        "an additional role is accepted",
        own_roles,
        lambda c: "Data_Protection_Officer" in c.roles,
    )

    def shorter_exceptions(raw):
        raw["policy"]["exceptions"]["max_days"] = 90
        raw["policy"]["exceptions"]["extended_max_days"] = 180

    accepts(
        "a shorter exception window is accepted",
        shorter_exceptions,
        lambda c: c.exception_max_days == 90,
    )

    def stricter_threats(raw):
        raw["threat"]["minimum_promotable_severity"] = "Low"

    accepts(
        "promoting every threat severity is accepted",
        stricter_threats,
        lambda c: c.minimum_promotable_severity_rank == 0,
    )

    section("The scoring engine reflects the configuration")
    from app.engine.scoring import ScoringEngine

    check("score 20 is Critical under the shipped bands", ScoringEngine.rating_for(20) == "Critical")
    check("score 12 is Moderate", ScoringEngine.rating_for(12) == "Moderate")
    check("Critical cannot be accepted", not ScoringEngine.acceptance_permitted("Critical"))
    check("High can be accepted", ScoringEngine.acceptance_permitted("High"))
    check(
        "CE-Medium permits one level of reduction",
        ScoringEngine.max_residual_likelihood_reduction(
            type("R", (), {"max_likelihood_reduction": base.ce_likelihood_reduction["CE-Medium"]})()
        )
        == 1,
    )

    section("Audit entries survive non-primitive values")
    from datetime import date, datetime
    from decimal import Decimal

    from app.engine import AuditTrail

    coerced = AuditTrail.diff(
        {"expiry": None, "cost": None},
        {"expiry": date(2026, 11, 1), "cost": Decimal("1250.50")},
    )
    check(
        "a date is coerced for the JSONB column",
        coerced["expiry"]["to"] == "2026-11-01",
        coerced,
    )
    check("a decimal is coerced", coerced["cost"]["to"] == 1250.5, coerced)
    check(
        "nested structures are coerced",
        AuditTrail.jsonable({"a": [date(2026, 1, 1), {"b": datetime(2026, 1, 1)}]})
        == {"a": ["2026-01-01", {"b": "2026-01-01T00:00:00"}]},
    )

    print("\n" + "=" * 62)
    print("passed: " + str(len(PASSED)) + "   failed: " + str(len(FAILED)))
    if FAILED:
        print("\nfailures:")
        for f in FAILED:
            print("  - " + f)
    print("=" * 62)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
