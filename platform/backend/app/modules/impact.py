"""Control test impact: what a test result changed, and where it stopped.

Codified-rules section 25.4. A test result is evidence about one asset. Its
consequences depend on where that asset sits: inside a risk's declared scope or
outside it, inside a framework's scope or outside it, and, for a framework,
under which coverage rule. This module answers the question an owner asks after
a test, "what did that do to MY risk and MY framework?", by taking the state of
everything the control carries before the test, again after the cascade has
run, and describing the difference.

It is read-only. It writes nothing to a risk or a requirement: the cascade does
that, under the rules. What it returns is kept with the test row, which is
append-only, so the answer survives as lineage rather than being re-derived
later from a register that has since moved on.

Like cascades.py and jobs.py it sits at the modules level because it reads
across domains. Unlike them it never writes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.governance import governance
from app.engine.scoring import ScoringEngine


def snapshot(session: Session, objective) -> dict[str, Any]:
    """Plain values, copied, so a later mutation cannot rewrite the 'before'."""
    from app.modules.compliance.machine import coverage_meets_rule, live_reach
    from app.modules.compliance.models import ControlRequirementLink
    from app.modules.compliance.service import ComplianceService
    from app.modules.risk.models import Risk, RiskControlLink

    risks: dict[str, dict[str, Any]] = {}
    risk_ids = [
        link.risk_id
        for link in session.execute(
            select(RiskControlLink).where(RiskControlLink.objective_id == objective.id)
        ).scalars()
    ]
    if risk_ids:
        for risk in session.execute(
            select(Risk).where(Risk.id.in_(risk_ids), Risk.lifecycle_state != "Closed")
        ).scalars():
            objectives = [l.objective for l in risk.control_links if l.objective is not None]
            resolution = ScoringEngine.resolve_ce(objectives, scope=risk.scope_asset_ids)
            proposal = ScoringEngine.proposed_residual(
                risk.impact,
                risk.likelihood,
                risk.residual_impact,
                risk.residual_likelihood,
                resolution,
            )
            risks[risk.id] = {
                "id": risk.id,
                "reference": risk.reference,
                "title": risk.title,
                "risk_owner_id": risk.risk_owner_id,
                "risk_analyst_id": risk.risk_analyst_id,
                "scope_asset_ids": sorted(risk.scope_asset_ids),
                "scope_asset_names": sorted(
                    getattr(l.surface, "name", "") for l in risk.asset_links
                ),
                "effective_ce": resolution.effective_ce,
                "ceiling": resolution.max_likelihood_reduction,
                "inherent_score": risk.inherent_risk_score,
                "inherent_rating": risk.inherent_rating,
                "residual_score": risk.residual_risk_score,
                "residual_rating": risk.residual_rating,
                "residual_locked": risk.residual_score_locked,
                "reported_score": risk.reported_score,
                "reported_rating": risk.reported_rating,
                "proposed": proposal,
            }

    compliance = ComplianceService(session, None)
    requirements: dict[str, dict[str, Any]] = {}
    frameworks: dict[str, dict[str, Any]] = {}
    for link in session.execute(
        select(ControlRequirementLink).where(ControlRequirementLink.objective_id == objective.id)
    ).scalars():
        requirement = link.requirement
        if requirement is None:
            continue
        framework = requirement.framework
        if not framework.adopted:
            continue
        scoped, reached = live_reach(requirement, session)
        assessment = requirement.assessment
        requirements[requirement.id] = {
            "framework_id": framework.framework_id,
            "ref": requirement.ref,
            "title": requirement.title,
            "satisfies": link.satisfies,
            "state": assessment.lifecycle_state if assessment else "Not_Assessed",
            "gap_reason": assessment.gap_reason if assessment else None,
            "owner_id": assessment.owner_id if assessment else None,
            "scoped": sorted(scoped),
            "reached_in_scope": sorted(reached & scoped) if scoped else sorted(reached),
            "rule_met": coverage_meets_rule(requirement, session),
        }
        if framework.framework_id not in frameworks:
            posture = compliance.posture(framework.framework_id)["frameworks"][0]
            frameworks[framework.framework_id] = {
                "framework_id": framework.framework_id,
                "name": framework.name,
                "rule": governance.coverage_rule(framework.framework_id),
                "scoped_asset_ids": sorted(scoped),
                "scoped_asset_names": [a["name"] for a in posture["scoped_assets"]],
                "coverage_pct": posture["coverage_pct"],
                "satisfied": posture["satisfied"],
                "in_scope": posture["in_scope"],
            }

    deployments = {
        d.id: {
            "reference": d.reference,
            "asset_id": d.attack_surface_id,
            "asset": d.surface.name if d.surface else None,
            "status": d.deployment_status,
            "ce_rating": d.ce_rating,
        }
        for d in objective.deployments
    }

    return {
        "objective": {
            "id": objective.id,
            "reference": objective.reference,
            "lifecycle_state": objective.lifecycle_state,
        },
        "deployments": deployments,
        "risks": risks,
        "requirements": requirements,
        "frameworks": frameworks,
    }


def describe(
    before: dict[str, Any],
    after: dict[str, Any],
    tested_asset_ids: set[str],
    *,
    failure_type: str | None = None,
) -> dict[str, Any]:
    """The difference between two snapshots, per framework and per risk."""
    design = before["objective"]["lifecycle_state"] != after["objective"]["lifecycle_state"]
    tested_names = sorted(
        {
            d["asset"]
            for d in after["deployments"].values()
            if d["asset_id"] in tested_asset_ids and d["asset"]
        }
    )

    frameworks: list[dict[str, Any]] = []
    for framework_id, fa in sorted(after["frameworks"].items()):
        fb = before["frameworks"].get(framework_id, fa)
        in_scope = bool(tested_asset_ids & set(fa["scoped_asset_ids"]))
        rows = []
        for req_id, ra in after["requirements"].items():
            if ra["framework_id"] != framework_id:
                continue
            rb = before["requirements"].get(req_id, ra)
            lost = rb["state"] in ("Covered", "Compensating") and ra["state"] == "Gap"
            rows.append(
                {
                    "ref": ra["ref"],
                    "title": ra["title"],
                    "before": rb["state"],
                    "after": ra["state"],
                    "lost": lost,
                    "restorable": rb["state"] == "Gap"
                    and ra["state"] == "Gap"
                    and len(ra["reached_in_scope"]) > len(rb["reached_in_scope"]),
                    "reason": ra["gap_reason"] if lost else None,
                    "owner_id": ra["owner_id"],
                    "in_scope_assets": len(ra["scoped"]),
                    "reached_before": len(rb["reached_in_scope"]),
                    "reached_after": len(ra["reached_in_scope"]),
                }
            )
        rows.sort(key=lambda r: r["ref"])
        lost = [r for r in rows if r["lost"]]
        if lost:
            verdict = "requirements_lost"
            summary = (
                ", ".join(r["ref"] for r in lost) + " lost coverage"
                + (
                    ": design failure, so the control failed everywhere"
                    if design
                    else " under " + fa["rule"]
                )
            )
        elif not in_scope and not design:
            verdict = "out_of_scope"
            summary = (
                "Tested asset is outside the " + framework_id + " scope: no effect"
            )
        elif any(r["reached_after"] < r["reached_before"] for r in rows):
            verdict = "still_covered"
            weakest = min(rows, key=lambda r: r["reached_after"])
            summary = (
                "Still covered under " + fa["rule"] + ": " + str(weakest["reached_after"])
                + " of " + str(weakest["in_scope_assets"]) + " in-scope assets still "
                "carry the control"
            )
        elif any(r["restorable"] for r in rows):
            verdict = "restorable"
            summary = "Coverage can be re-asserted; the gate re-checks it"
        else:
            verdict = "no_change"
            summary = "No change to coverage"
        frameworks.append(
            {
                "framework_id": framework_id,
                "name": fa["name"],
                "rule": fa["rule"],
                "asset_in_scope": in_scope,
                "scoped_asset_names": fa["scoped_asset_names"],
                "coverage_pct_before": fb["coverage_pct"],
                "coverage_pct_after": fa["coverage_pct"],
                "requirements": rows,
                "verdict": verdict,
                "summary": summary,
            }
        )

    risks: list[dict[str, Any]] = []
    for risk_id, ra in sorted(after["risks"].items(), key=lambda kv: kv[1]["reference"]):
        rb = before["risks"].get(risk_id, ra)
        declared = bool(ra["scope_asset_ids"])
        in_scope = not declared or bool(tested_asset_ids & set(ra["scope_asset_ids"]))
        affected = (
            ra["effective_ce"] != rb["effective_ce"]
            or ra["ceiling"] != rb["ceiling"]
            or ra["residual_locked"] != rb["residual_locked"]
        )
        proposal = ra["proposed"]
        ce_moved = ra["effective_ce"] != rb["effective_ce"] or ra["ceiling"] != rb["ceiling"]
        if affected and not ce_moved:
            # Frozen without its CE moving: the failed control was not the
            # weakest one this risk relies on, so the worst case is unchanged.
            summary = (
                "Residual frozen by the control failure; the worst case across the "
                "remaining controls is still " + ra["effective_ce"]
                + (", so the recorded residual still fits" if proposal and not proposal["changed"] else "")
            )
        elif affected:
            summary = (
                "CE " + rb["effective_ce"] + " to " + ra["effective_ce"]
                + ", likelihood reduction ceiling " + str(rb["ceiling"]) + " to "
                + str(ra["ceiling"])
            )
            if proposal and proposal["changed"]:
                summary += (
                    "; proposed residual " + str(proposal["score"]) + " "
                    + proposal["rating"]
                    + (" (above appetite)" if proposal["above_appetite"] else "")
                )
            elif proposal:
                summary += "; recorded residual still fits"
        elif not in_scope:
            summary = (
                "Tested asset is outside this risk's scope ("
                + ", ".join(ra["scope_asset_names"]) + "): no effect (RINV-14)"
            )
        else:
            summary = "No change to control effectiveness"
        risks.append(
            {
                "id": risk_id,
                "reference": ra["reference"],
                "title": ra["title"],
                "risk_owner_id": ra["risk_owner_id"],
                "risk_analyst_id": ra["risk_analyst_id"],
                "scope_declared": declared,
                "scope_asset_names": ra["scope_asset_names"],
                "asset_in_scope": in_scope,
                "affected": affected,
                "ce_before": rb["effective_ce"],
                "ce_after": ra["effective_ce"],
                "ceiling_before": rb["ceiling"],
                "ceiling_after": ra["ceiling"],
                "residual_before": {
                    "score": rb["residual_score"],
                    "rating": rb["residual_rating"],
                },
                "reported_after": {
                    "score": ra["reported_score"],
                    "rating": ra["reported_rating"],
                },
                "proposed": proposal,
                "summary": summary,
            }
        )

    return {
        "failure_type": failure_type,
        "design_failure": design,
        "objective": after["objective"],
        "tested_assets": tested_names,
        "frameworks": frameworks,
        "risks": risks,
        "totals": {
            "frameworks_affected": sum(
                1 for f in frameworks if f["verdict"] in ("requirements_lost", "still_covered")
            ),
            "requirements_lost": sum(
                1 for f in frameworks for r in f["requirements"] if r["lost"]
            ),
            "risks_affected": sum(1 for r in risks if r["affected"]),
            "risks_proposed_above_appetite": sum(
                1
                for r in risks
                if r["affected"]
                and r["proposed"]
                and r["proposed"]["changed"]
                and r["proposed"]["above_appetite"]
            ),
        },
    }


def population(session: Session, objective, results: dict[str, str]) -> list[dict[str, Any]]:
    """A campaign's results read against each framework's scope.

    `results` maps deployment id to result. For every framework the control
    carries: which in-scope assets were tested, which failed, which run the
    control but were not tested, and which do not run it at all. The untested
    ones are the finding a pass rate hides.
    """
    from app.modules.compliance.models import ControlRequirementLink
    from app.modules.control.models import AttackSurface

    by_asset: dict[str, Any] = {}
    for deployment in objective.deployments:
        by_asset.setdefault(deployment.attack_surface_id, []).append(deployment)

    framework_ids = sorted(
        {
            link.requirement.framework.framework_id
            for link in session.execute(
                select(ControlRequirementLink).where(
                    ControlRequirementLink.objective_id == objective.id
                )
            ).scalars()
            if link.requirement is not None and link.requirement.framework.adopted
        }
    )
    assets = session.execute(select(AttackSurface)).scalars().all()

    rows = []
    for framework_id in framework_ids:
        scoped = sorted(
            (a for a in assets if framework_id in (a.compliance_scopes or [])),
            key=lambda a: a.name,
        )
        tested, failed, untested, not_deployed = [], [], [], []
        for asset in scoped:
            deployments = by_asset.get(asset.id, [])
            if not deployments:
                not_deployed.append(asset.name)
                continue
            outcomes = [results[d.id] for d in deployments if d.id in results]
            if not outcomes:
                untested.append(asset.name)
                continue
            tested.append(asset.name)
            if "Fail" in outcomes:
                failed.append(asset.name)
        rows.append(
            {
                "framework_id": framework_id,
                "in_scope": len(scoped),
                "tested": tested,
                "failed": failed,
                "untested": untested,
                "not_deployed": not_deployed,
                "tested_pct": round(100 * len(tested) / len(scoped)) if scoped else None,
            }
        )
    return rows
