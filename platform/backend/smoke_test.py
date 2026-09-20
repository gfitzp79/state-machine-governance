"""End-to-end smoke test.

Runs against a live API. Walks the behaviour the platform exists to demonstrate:
gates that refuse, invariants that refuse, and a cascade that crosses three
lifecycles in one transaction.

    docker compose down -v && docker compose up -d
    docker compose exec api python smoke_test.py

It mutates state deliberately (failing a control test is the point), so it must
run against a freshly seeded database. It refuses to start otherwise.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api"
PASSWORD = "changeme123"

PASSED: list[str] = []
FAILED: list[str] = []


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw.decode(errors="replace")}


def login(email):
    status, body = call("POST", "/auth/login", {"email": email, "password": PASSWORD})
    assert status == 200, (email, status, body)
    return body["token"]


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("  PASS  " + name)
    else:
        FAILED.append(name + (" :: " + str(detail) if detail else ""))
        print("  FAIL  " + name + ("  ->  " + str(detail) if detail else ""))


def section(title):
    print("\n" + title)
    print("-" * len(title))


def find(rows, reference):
    return next(r for r in rows if r["reference"] == reference)


def main() -> int:
    analyst = login("analyst@example.com")
    ciso = login("ciso@example.com")
    control_owner = login("control@example.com")
    appsec = login("appsec@example.com")
    grc = login("grc@example.com")

    section("Seed integrity")
    _, risks = call("GET", "/risks", token=analyst)
    if len(risks) != 5:
        print("")
        print("This test mutates state (it fails a control test and promotes a threat")
        print("scenario), so it needs a pristine seeded database.")
        print("Reset first:  docker compose down -v && docker compose up -d")
        print("")
        return 2
    check("5 risks seeded", len(risks) == 5, len(risks))
    _, controls = call("GET", "/controls", token=analyst)
    check("5 control objectives seeded", len(controls) == 5, len(controls))
    _, models = call("GET", "/threat-models", token=analyst)
    check("1 threat model seeded", len(models) == 1, len(models))

    risk1 = find(risks, "RISK-001")
    risk2 = find(risks, "RISK-002")
    risk3 = find(risks, "RISK-003")
    risk4 = find(risks, "RISK-004")
    risk5 = find(risks, "RISK-005")

    section("RINV-1: residual is locked until the gate releases it")
    status, body = call(
        "POST",
        "/risks/" + risk2["id"] + "/score/residual",
        {"residual_impact": 2, "residual_likelihood": 1},
        analyst,
    )
    check("residual write refused while locked", status == 409, (status, body.get("code")))
    check(
        "refusal names RINV-1",
        "RINV-1" in str(body.get("message", "")),
        body.get("message"),
    )
    check(
        "refusal returns the five conditions",
        isinstance(body.get("detail"), dict) and len(body["detail"]) == 5,
        body.get("detail"),
    )

    section("RINV-5: a Critical risk cannot be accepted")
    status, body = call(
        "POST",
        "/risks/" + risk3["id"] + "/treatment-decision",
        {
            "treatment_strategy": "Accept",
            "acceptance_expiry_date": "2027-01-01",
            "acceptance_rationale": "business has decided to carry this",
        },
        analyst,
    )
    check("accept refused on Critical", status == 409, (status, body.get("code")))
    check("refusal names RINV-5", "RINV-5" in str(body.get("message", "")), body.get("message"))

    section("RINV-4: acceptance windows are capped by rating")
    status, body = call(
        "POST",
        "/risks/" + risk3["id"] + "/treatment-decision",
        {"treatment_strategy": "Mitigate", "control_framework_mapping": "ISO 27001 A.8.24"},
        analyst,
    )
    check("mitigate accepted on Critical", status == 200, (status, body.get("message")))

    section("Acceptance requires approval at the configured seniority")
    _, all_users = call("GET", "/users", token=ciso)
    vp = next(u for u in all_users if u["seniority"] == "VP")
    manager = next(u for u in all_users if u["seniority"] == "Manager")

    # RISK-002 is Moderate, which the shipped config requires a VP or above to accept.
    status, body = call(
        "POST",
        "/risks/" + risk2["id"] + "/treatment-decision",
        {
            "treatment_strategy": "Accept",
            "acceptance_expiry_date": "2026-11-01",
            "acceptance_rationale": "compensating detection in place pending TRT-002",
        },
        analyst,
    )
    check("acceptance with no named approver is refused", status == 409, status)
    check(
        "the refusal names the required seniority",
        "VP" in str(body.get("message", "")),
        body.get("message"),
    )

    status, body = call(
        "POST",
        "/risks/" + risk2["id"] + "/treatment-decision",
        {
            "treatment_strategy": "Accept",
            "acceptance_expiry_date": "2026-11-01",
            "acceptance_rationale": "compensating detection in place pending TRT-002",
            "acceptance_approved_by": manager["id"],
        },
        analyst,
    )
    check("approval below the required seniority is refused", status == 409, status)
    check(
        "the refusal names the actual seniority",
        "Manager" in str(body.get("message", "")),
        body.get("message"),
    )

    section("A time-bound acceptance commits and is audited")
    status, body = call(
        "POST",
        "/risks/" + risk2["id"] + "/treatment-decision",
        {
            "treatment_strategy": "Accept",
            "acceptance_expiry_date": "2026-11-01",
            "acceptance_rationale": "compensating detection in place pending TRT-002",
            "acceptance_approved_by": vp["id"],
        },
        analyst,
    )
    check("a Moderate risk can be accepted at VP", status == 200, (status, body.get("message")))
    check(
        "the expiry is recorded",
        body.get("acceptance_expiry_date") == "2026-11-01",
        body.get("acceptance_expiry_date"),
    )
    status, entries = call(
        "GET", "/audit?entity_type=risk&entity_id=" + risk2["id"], token=analyst
    )
    decisions = [e for e in entries if e["action"] == "TREATMENT_DECISION"]
    check("the decision was audited", len(decisions) >= 1, len(decisions))
    check(
        "the date survived the JSONB write",
        any(
            d["changed_fields"].get("acceptance_expiry_date", {}).get("to") == "2026-11-01"
            for d in decisions
        ),
        decisions[:1],
    )
    # Put it back so the residual-gate checks below read a Mitigate decision.
    call(
        "POST",
        "/risks/" + risk2["id"] + "/treatment-decision",
        {"treatment_strategy": "Mitigate", "control_framework_mapping": "ISO 27001 A.8.15"},
        analyst,
    )

    section("Configured taxonomy is enforced at the service layer")
    status, body = call(
        "POST",
        "/risks",
        {"title": "Taxonomy probe", "tier": "Tier_9", "intake_source": "Assessment"},
        analyst,
    )
    check("an unconfigured tier is refused", status == 409, status)
    check(
        "the refusal names the configuration file",
        "governance.yml" in str(body.get("message", "")),
        body.get("message"),
    )
    status, body = call(
        "POST",
        "/controls",
        {"title": "Taxonomy probe control", "family": "Interpretive_Dance"},
        analyst,
    )
    check("an unconfigured control family is refused", status == 409, status)

    section("The configured model is served, and split by audience")
    # Branding is anonymous: the sign-in page needs the organisation name.
    status, public = call("GET", "/config")
    check("public config responds anonymously", status == 200, status)
    check("it carries the organisation name", bool(public.get("organisation", {}).get("name")))
    check(
        "it carries nothing else",
        set(public.keys()) == {"organisation"},
        sorted(public.keys()),
    )

    # The operating model is not public: it describes the separation of duties.
    status, _ = call("GET", "/config/governance")
    check("the governance model is not anonymously readable", status == 403, status)

    status, cfg = call("GET", "/config/governance", token=analyst)
    check("an authenticated caller gets the full model", status == 200, status)
    check("it carries five rating bands", len(cfg.get("rating_bands", [])) == 5)
    check(
        "it carries the configured control families",
        len(cfg.get("controls", {}).get("families", [])) > 0,
    )
    check(
        "Critical is marked unacceptable",
        cfg["acceptance_rules"]["Critical"]["acceptable"] is False,
    )

    section("Machine definitions are not anonymously readable")
    # StateMachine.describe() carries the roles permitted to fire every gate,
    # which is the separation-of-duties design.
    for path in (
        "/engine/machines",
        "/engine/invariants",
        "/engine/cascades",
        "/engine/scoring",
        "/risks/machine",
        "/controls/machines",
        "/policies/machine",
        "/threat-models/machine",
        "/treatments/machine",
        "/roles",
    ):
        status, _ = call("GET", path)
        check("anonymous " + path + " is refused", status == 403, status)
    status, machines = call("GET", "/engine/machines", token=analyst)
    check("authenticated callers still get them", status == 200, status)

    section("RINV-8: scoring is refused before the preconditions gate")
    status, body = call(
        "POST",
        "/risks/" + risk5["id"] + "/score/inherent",
        {"impact": 4, "likelihood": 3, "impact_justification": "x"},
        analyst,
    )
    check("scoring refused at Intake", status == 409, (status, body.get("code")))
    check("refusal names RINV-8", "RINV-8" in str(body.get("message", "")), body.get("message"))

    section("OUT-5: inherent scores freeze once the risk leaves Phase 3")
    status, body = call(
        "POST",
        "/risks/" + risk1["id"] + "/score/inherent",
        {"impact": 1, "likelihood": 1},
        analyst,
    )
    check("re-scoring refused after Phase 3", status == 409, (status, body.get("code")))
    check("refusal names OUT-5", "OUT-5" in str(body.get("message", "")), body.get("message"))

    section("Gate evaluation is reported, not just enforced")
    status, gates = call("GET", "/risks/" + risk2["id"] + "/gates", token=analyst)
    monitoring = next(g for g in gates if g["target"] == "Monitoring")
    failing = [c["id"] for c in monitoring["checks"] if not c["passed"]]
    check("Phase 6 gate is blocked", monitoring["passed"] is False)
    check(
        "gate reports 7 named conditions",
        len(monitoring["checks"]) == 7,
        len(monitoring["checks"]),
    )
    check(
        "blocked conditions are identified by rule",
        "RESIDUAL.1" in failing and "RESIDUAL.2" in failing and "RINV-1" in failing,
        failing,
    )
    status, body = call(
        "POST", "/risks/" + risk2["id"] + "/transition", {"target": "Monitoring"}, analyst
    )
    check("transition refused by the gate", status == 409, status)
    check("refusal is gate_blocked", body.get("code") == "gate_blocked", body.get("code"))

    section("Role enforcement on transitions")
    status, body = call(
        "POST", "/risks/" + risk4["id"] + "/transition", {"target": "Treatment"}, control_owner
    )
    check("control owner cannot advance a risk", status == 409, status)

    section("CE resolution is traceable")
    status, ce = call("GET", "/risks/" + risk1["id"] + "/ce-resolution", token=analyst)
    check("worst-case CE resolved", ce["effective_ce"] == "CE-Medium", ce["effective_ce"])
    check(
        "CE-Medium permits one level of reduction",
        ce["max_likelihood_reduction"] == 1,
        ce["max_likelihood_reduction"],
    )
    check("both deployments contribute", len(ce["contributing"]) == 2, len(ce["contributing"]))

    status, ce4 = call("GET", "/risks/" + risk4["id"] + "/ce-resolution", token=analyst)
    check(
        "a non-Operating control is excluded",
        ce4["effective_ce"] == "CE-Unvalidated" and len(ce4["excluded"]) >= 1,
        ce4,
    )
    check(
        "exclusion names the rule",
        "CE-5" in str(ce4["excluded"][0]["reason"]),
        ce4["excluded"][0]["reason"],
    )

    section("RINV-3 / SEP-3: a control owner cannot own a risk scored by their control")
    _, ctl2 = call("GET", "/controls", token=analyst)
    ctl_encryption = find(ctl2, "CTL-002")
    status, body = call(
        "POST",
        "/risks/" + risk1["id"] + "/controls",
        {"id": ctl_encryption["id"]},
        analyst,
    )
    check("unrelated control links cleanly", status == 200, (status, body.get("message")))

    section("CINV-1: a CE rating above Unvalidated requires evidence")
    status, detail = call("GET", "/controls/" + find(controls, "CTL-001")["id"], token=analyst)
    dep2 = next(
        d
        for a in detail["activities"]
        for d in a["deployments"]
        if d["reference"] == "DEP-002"
    )
    status, body = call(
        "POST",
        "/controls/deployments/" + dep2["id"] + "/ce",
        {"ce_rating": "CE-High", "ce_evidence_ref": ""},
        control_owner,
    )
    check("CE without evidence refused", status == 409, status)
    check("refusal names CINV-1", "CINV-1" in str(body.get("message", "")), body.get("message"))

    section("THE CASCADE: one failing control test crosses three lifecycles")
    _, before_risk = call("GET", "/risks/" + risk1["id"], token=analyst)
    _, before_model = call("GET", "/threat-models/" + models[0]["id"], token=analyst)
    thr1_before = next(s for s in before_model["scenarios"] if s["reference"] == "THR-001")
    check("RISK-001 residual is unlocked before", before_risk["residual_score_locked"] is False)
    check(
        "RISK-001 reports its validated residual",
        before_risk["reported_score"] == 15,
        before_risk["reported_score"],
    )
    check("THR-001 is mitigated before", thr1_before["status"] == "Mitigated")
    check("TM-001 is Active before", before_model["lifecycle_state"] == "Active")
    check("TM-001 is fully signed off before", before_model["fully_signed_off"] is True)

    status, body = call(
        "POST",
        "/controls/deployments/" + dep2["id"] + "/tests",
        {
            "result": "Fail",
            "evidence_ref": "Q4 test: 3 privileged roles found without MFA enforcement.",
            "notes": "Conditional access policy scope regression.",
        },
        control_owner,
    )
    check("failing test recorded", status == 201, (status, body.get("message")))

    _, after_risk = call("GET", "/risks/" + risk1["id"], token=analyst)
    _, after_control = call("GET", "/controls/" + find(controls, "CTL-001")["id"], token=analyst)
    _, after_model = call("GET", "/threat-models/" + models[0]["id"], token=analyst)
    thr1_after = next(s for s in after_model["scenarios"] if s["reference"] == "THR-001")

    check(
        "deployment moved to Failed",
        next(
            d
            for a in after_control["activities"]
            for d in a["deployments"]
            if d["reference"] == "DEP-002"
        )["deployment_status"]
        == "Failed",
    )
    check(
        "objective propagated to Failure (DL-1)",
        after_control["lifecycle_state"] == "Failure",
        after_control["lifecycle_state"],
    )
    check(
        "linked risk residual re-locked (CINV-5)",
        after_risk["residual_score_locked"] is True,
    )
    check(
        "linked risk reverts to reporting inherent (RES-2)",
        after_risk["reported_score"] == 20 and after_risk["reported_rating"] == "Critical",
        (after_risk["reported_score"], after_risk["reported_rating"]),
    )
    check(
        "risk carries the control-failure flag",
        after_risk["control_change_flag"] == "Control_Failure",
        after_risk["control_change_flag"],
    )
    check(
        "threat scenario re-opened (TINV-4)",
        thr1_after["status"] == "Identified",
        thr1_after["status"],
    )
    check(
        "threat model returned to Review (TINV-2)",
        after_model["lifecycle_state"] == "Review",
        after_model["lifecycle_state"],
    )
    check(
        "both sign-offs stripped",
        after_model["appsec_signoff_by"] is None and after_model["owner_signoff_by"] is None,
    )

    section("TINV-3: a Medium-or-above scenario cannot be accepted locally")
    thr4 = next(s for s in after_model["scenarios"] if s["reference"] == "THR-004")
    status, body = call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/scenarios/" + thr4["id"] + "/accept",
        {"acceptance_expiry": "2027-01-01", "acceptance_rationale": "accepted by the team"},
        appsec,
    )
    check("local acceptance refused above Low", status == 409, status)
    check("refusal names TINV-3", "TINV-3" in str(body.get("message", "")), body.get("message"))

    section("Threat modelling consults the GRC environment")
    _, ctx = call("GET", "/threat-models/" + models[0]["id"] + "/context", token=appsec)
    check("context endpoint responds", ctx.get("enabled") is True, ctx.get("enabled"))
    check(
        "context declares itself informative",
        ctx.get("informative_only") is True,
        ctx.get("informative_only"),
    )
    check(
        "it reports the asset's control posture",
        ctx["control_posture"]["total_deployments"] > 0,
        ctx["control_posture"],
    )
    check(
        "coverage applies the same filters as the scoring engine",
        any(
            "CE-5" in d["reason"] or "CE-6" in d["reason"] or "CE-Low" in d["reason"]
            for d in ctx["control_posture"]["deployments"]
            if d["status"] != "effective"
        ),
        [d["reason"] for d in ctx["control_posture"]["deployments"]],
    )
    check(
        "it reports risks depending on controls here",
        len(ctx["risk_posture"]["risks"]) > 0,
        ctx["risk_posture"],
    )
    check(
        "it reports residual exposure already accepted",
        "residual_locked" in ctx["risk_posture"],
    )
    check(
        "it surfaces a control gap",
        len(ctx["gaps"]) > 0,
        ctx["gaps"],
    )
    check(
        "sensitive data in a low-trust zone is flagged",
        any(g["kind"] == "sensitive_data_in_low_trust_zone" for g in ctx["gaps"]),
        [g["kind"] for g in ctx["gaps"]],
    )

    section("TINV-7: context is informative, never determinative")
    _, tm_before = call("GET", "/threat-models/" + models[0]["id"], token=appsec)
    covered = {
        s["reference"]: s["status"]
        for s in tm_before["scenarios"]
    }
    # THR-004 is mitigated by DEP-005, which is Degraded with CE-Low. Ambient
    # coverage on the asset must not have resolved anything by itself.
    check(
        "no scenario was resolved by ambient control posture",
        all(
            s["status"] != "Mitigated" or len(s["mitigations"]) > 0
            for s in tm_before["scenarios"]
        ),
        covered,
    )
    # Removing the only mitigation link must return the scenario to Identified,
    # even though the control is still deployed on the asset.
    thr4 = next(s for s in tm_before["scenarios"] if s["reference"] == "THR-004")
    link_id = thr4["mitigations"][0]["link_id"]
    status, body = call(
        "DELETE",
        "/threat-models/" + models[0]["id"] + "/scenarios/" + thr4["id"]
        + "/mitigations/" + link_id,
        token=appsec,
    )
    check("mitigation link removed", status == 200, (status, body.get("message")))
    thr4_after = next(s for s in body["scenarios"] if s["reference"] == "THR-004")
    check(
        "the scenario reopened when its link was removed",
        thr4_after["status"] == "Identified",
        thr4_after["status"],
    )
    check(
        "the control is still deployed on the asset",
        body["context"]["control_posture"]["total_deployments"] > 0,
    )
    # Restore it so the later cascade section reads a mitigated scenario.
    call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/scenarios/" + thr4["id"] + "/mitigate",
        {"deployment_id": thr4["mitigations"][0]["deployment_id"]},
        appsec,
    )

    section("TINV-8: a scenario references an existing risk without duplicating it")
    _, risks_before = call("GET", "/risks", token=analyst)
    count_before = len(risks_before)
    _, tm_now = call("GET", "/threat-models/" + models[0]["id"], token=appsec)
    thr5 = next(s for s in tm_now["scenarios"] if s["reference"] == "THR-005")
    check(
        "THR-005 references an existing risk",
        len(thr5["risk_links"]) == 1 and thr5["risk_links"][0]["link_type"] == "Represents",
        thr5["risk_links"],
    )
    check("it counts as carried by the register", thr5["carried_by_register"] is True)
    check("it therefore satisfies TINV-1", thr5["is_resolved"] is True)
    check(
        "no duplicate risk record was created",
        count_before == 5,
        count_before,
    )
    status, body = call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/scenarios/" + thr5["id"] + "/risks",
        {"risk_id": risk1["id"], "link_type": "Promoted_From"},
        appsec,
    )
    check("linking with the promotion type is refused", status == 409, status)
    check("refusal names TINV-8", "TINV-8" in str(body.get("message", "")), body.get("message"))

    section("TINV-9: sensitive components declare where they sit")
    status, body = call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/components",
        {
            "name": "Unzoned secrets cache",
            "component_type": "Datastore",
            "data_classification": "Restricted",
            "data_types": ["Credentials"],
        },
        appsec,
    )
    check("a sensitive component without a zone is refused", status == 422, status)
    check("refusal names TINV-9", "TINV-9" in str(body.get("message", "")), body.get("message"))

    status, body = call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/components",
        {
            "name": "Unzoned secrets cache",
            "component_type": "Datastore",
            "data_classification": "Restricted",
            "trust_zone": "Atlantis",
        },
        appsec,
    )
    check("an unconfigured trust zone is refused", status == 409, status)
    check(
        "the refusal names the configuration file",
        "governance.yml" in str(body.get("message", "")),
        body.get("message"),
    )

    section("Scenarios are interactive: comments, evidence, status")
    status, body = call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/scenarios/" + thr5["id"] + "/comments",
        {"body": "Data platform confirmed the KMS policy is now scheduled for Q1."},
        analyst,
    )
    check("a comment can be added", status == 201, status)
    refreshed = next(s for s in body["scenarios"] if s["reference"] == "THR-005")
    check("the comment is on the scenario", len(refreshed["comments"]) == 3, len(refreshed["comments"]))

    status, body = call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/scenarios/" + thr5["id"] + "/evidence",
        {
            "title": "KMS remediation plan",
            "evidence_ref": "CHG-2026-118: customer-managed key rollout to the sandbox",
            "evidence_type": "Ticket",
            "supports": "Identified",
        },
        appsec,
    )
    check("evidence can be attached", status == 201, status)
    refreshed = next(s for s in body["scenarios"] if s["reference"] == "THR-005")
    check("the evidence is on the scenario", len(refreshed["evidence"]) == 2, len(refreshed["evidence"]))

    section("Threat evidence is immutable at the database layer")
    from sqlalchemy import text

    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        try:
            session.execute(text("UPDATE threat_scenario_evidence SET title = 'TAMPERED'"))
            session.commit()
            check("threat_scenario_evidence rejects UPDATE", False, "the update succeeded")
        except Exception as exc:
            session.rollback()
            check(
                "threat_scenario_evidence rejects UPDATE",
                "append-only" in str(exc),
                str(exc)[:120],
            )
    finally:
        session.close()

    section("Threat scenario promotion creates a real risk record")
    status, body = call(
        "POST",
        "/threat-models/" + models[0]["id"] + "/scenarios/" + thr1_after["id"] + "/promote",
        {"tier": "Tier_1"},
        appsec,
    )
    check("promotion succeeded", status == 200, (status, body.get("message")))
    check(
        "a risk record was created and linked",
        body.get("promoted_risk", {}).get("reference", "").startswith("RISK-"),
        body.get("promoted_risk"),
    )

    section("PINV-1: an Active policy keeps at least one linked control")
    _, policies = call("GET", "/policies", token=analyst)
    pol2 = find(policies, "POL-002")
    _, pol2_detail = call("GET", "/policies/" + pol2["id"], token=analyst)
    while len(pol2_detail["controls"]) > 1:
        link = pol2_detail["controls"][0]
        status, body = call(
            "DELETE", "/policies/" + pol2["id"] + "/controls/" + link["link_id"], token=ciso
        )
        check("surplus link removed cleanly", status == 200, (status, body))
        _, pol2_detail = call("GET", "/policies/" + pol2["id"], token=analyst)
        check(
            "removed link no longer listed",
            all(c["link_id"] != link["link_id"] for c in pol2_detail["controls"]),
        )
    status, body = call(
        "DELETE",
        "/policies/" + pol2["id"] + "/controls/" + pol2_detail["controls"][0]["link_id"],
        token=ciso,
    )
    check("removing the last control refused", status == 409, status)
    check("refusal names PINV-1", "PINV-1" in str(body.get("message", "")), body.get("message"))

    section("PINV-5: no self-approval, and CISO or above only")
    pol3 = find(policies, "POL-003")
    _, users = call("GET", "/users", token=ciso)
    policy_owner = next(u for u in users if u["email"] == "policy@example.com")
    status, body = call(
        "POST", "/policies/" + pol3["id"] + "/approve", {"approver_id": policy_owner["id"]}, ciso
    )
    check("self-approval refused", status == 409, status)
    check("refusal names PINV-5", "PINV-5" in str(body.get("message", "")), body.get("message"))

    section("RINV-12 / SEP-5: feasibility validation is independent of delivery")
    _, treatments = call("GET", "/treatments", token=analyst)
    trt3 = find(treatments, "TRT-003")
    status, body = call("POST", "/treatments/" + trt3["id"] + "/validate", {"notes": "feasible"}, ciso)
    check("GRC validation recorded", status == 200, (status, body.get("message")))
    status, body = call("POST", "/treatments/" + trt3["id"] + "/commit", {}, ciso)
    check("commitment refused from a non-owner", status == 409, status)

    section("Immutability is enforced at the database layer")
    from sqlalchemy import text

    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        try:
            session.execute(text("UPDATE audit_log SET action = 'TAMPERED'"))
            session.commit()
            check("audit_log rejects UPDATE", False, "the update succeeded")
        except Exception as exc:
            session.rollback()
            check("audit_log rejects UPDATE", "append-only" in str(exc), str(exc)[:120])
        try:
            session.execute(text("DELETE FROM policy_versions"))
            session.commit()
            check("policy_versions rejects DELETE", False, "the delete succeeded")
        except Exception as exc:
            session.rollback()
            check("policy_versions rejects DELETE", "append-only" in str(exc), str(exc)[:120])
        try:
            session.execute(text("UPDATE control_tests SET result = 'Pass'"))
            session.commit()
            check("control_tests rejects UPDATE", False, "the update succeeded")
        except Exception as exc:
            session.rollback()
            check("control_tests rejects UPDATE", "append-only" in str(exc), str(exc)[:120])
    finally:
        session.close()

    section("Schema-layer constraints back the service layer")
    session = SessionLocal()
    try:
        try:
            session.execute(
                text(
                    "UPDATE risks SET treatment_strategy = 'Accept', "
                    "acceptance_expiry_date = NULL WHERE reference = 'RISK-002'"
                )
            )
            session.commit()
            check("direct SQL cannot create an open-ended acceptance", False, "the write succeeded")
        except Exception as exc:
            session.rollback()
            check(
                "direct SQL cannot create an open-ended acceptance",
                "acceptance_time_bound" in str(exc),
                str(exc)[:120],
            )
        try:
            # Supply a valid expiry so the severity constraint is the one under test
            # rather than the time-bound constraint.
            session.execute(
                text(
                    "UPDATE threat_scenarios SET status = 'Accepted', "
                    "acceptance_expiry = CURRENT_DATE + 30 "
                    "WHERE inherent_severity = 'Critical'"
                )
            )
            session.commit()
            check("direct SQL cannot accept a Critical threat", False, "the write succeeded")
        except Exception as exc:
            session.rollback()
            check(
                "direct SQL cannot accept a Critical threat",
                "no_local_acceptance_above_low" in str(exc),
                str(exc)[:120],
            )
    finally:
        session.close()

    section("Scheduled jobs enforce the time-based invariants")
    status, jobs = call("POST", "/engine/jobs/run", {}, ciso)
    check("jobs ran", status == 200, status)
    check(
        "CINV-10 downgraded the expired CE on DEP-006",
        "DEP-006" in jobs.get("ce_expired", []),
        jobs.get("ce_expired"),
    )

    section("The compliance register holds requirements, not framework names")
    status, fw = call("GET", "/compliance/frameworks", token=analyst)
    frameworks = {f["framework_id"]: f for f in fw["frameworks"]}
    check(
        "NIST CSF 2.0 bundled in full",
        frameworks.get("NIST-CSF-2.0", {}).get("requirements") == 106,
        frameworks.get("NIST-CSF-2.0"),
    )
    check(
        "AINV-6: a licensed framework ships as a record with no content",
        frameworks.get("ISO-27001-2022", {}).get("requirements") == 0
        and frameworks.get("ISO-27001-2022", {}).get("redistributable") is False,
        frameworks.get("ISO-27001-2022"),
    )

    status, reqs = call(
        "GET", "/compliance/frameworks/NIST-CSF-2.0/requirements", token=analyst
    )
    rows = {r["ref"]: r for r in reqs["requirements"]}
    check(
        "AINV-1: an excluded requirement carries its justification",
        rows["PR.AA-06"]["state"] == "Not_Applicable" and bool(rows["PR.AA-06"]["rationale"]),
        rows["PR.AA-06"],
    )
    check(
        "AINV-3: a requirement on a Partial link only is not Covered",
        rows["PR.AA-05"]["state"] != "Covered"
        and all(not link["satisfies"] for link in rows["PR.AA-05"]["links"]),
        rows["PR.AA-05"],
    )

    section("AINV-2: coverage needs a live control inside the declared scope")
    target = rows["PR.PS-01"]
    call(
        "POST",
        "/compliance/requirements/" + target["id"] + "/assess",
        {"target": "Applicable"},
        token=grc,
    )
    status, body = call(
        "POST",
        "/compliance/requirements/" + target["id"] + "/assess",
        {"target": "Covered"},
        token=grc,
    )
    check("Covered refused with nothing linked", status >= 400, status)
    check("the refusal names AINV-2", "AINV-2" in json.dumps(body), body)

    status, controls = call("GET", "/controls", token=analyst)
    by_ref = {c["reference"]: c for c in controls}
    call(
        "POST",
        "/compliance/requirements/" + target["id"] + "/controls",
        {"objective_id": by_ref["CTL-003"]["id"], "coverage_level": "Full",
         "rationale": "Pipeline configuration baseline."},
        token=grc,
    )
    status, _ = call(
        "POST",
        "/compliance/requirements/" + target["id"] + "/assess",
        {"target": "Covered"},
        token=grc,
    )
    check(
        "still refused: an Implementation control with a Planned deployment covers nothing",
        status >= 400,
        (status, by_ref["CTL-003"]["lifecycle_state"]),
    )

    call(
        "POST",
        "/compliance/requirements/" + target["id"] + "/controls",
        {"objective_id": by_ref["CTL-002"]["id"], "coverage_level": "Full",
         "rationale": "Encryption baseline enforced on the data platform."},
        token=grc,
    )
    status, covered = call(
        "POST",
        "/compliance/requirements/" + target["id"] + "/assess",
        {"target": "Covered"},
        token=grc,
    )
    check("Covered once an Operating control runs inside scope", status == 200, covered)

    status, posture_before = call("GET", "/compliance/posture", token=analyst)
    csf_before = next(
        f for f in posture_before["frameworks"] if f["framework_id"] == "NIST-CSF-2.0"
    )
    check(
        "posture reports a percentage only over a declared scope",
        csf_before["coverage_pct"] is not None and csf_before["scope_declared"] is True,
        csf_before,
    )

    section("AINV-5: a failing control takes the compliance position with it")
    # Captured before the failure: the claim is that the cascade is targeted,
    # and earlier sections of this suite have already failed other controls.
    untouched_before = now_before = None
    status, snapshot = call(
        "GET", "/compliance/frameworks/NIST-CSF-2.0/requirements", token=analyst
    )
    untouched_before = {r["ref"]: r["state"] for r in snapshot["requirements"]}
    status, ctl2 = call("GET", "/controls/" + by_ref["CTL-002"]["id"], token=analyst)
    live_dep = [
        d
        for a in ctl2["activities"]
        for d in a["deployments"]
        if d["deployment_status"] in ("Active", "Degraded")
    ][0]
    status, fired = call(
        "POST",
        "/controls/deployments/" + live_dep["id"] + "/transition",
        {"target": "Failed", "reason": "Key policy drift detected on the warehouse."},
        token=control_owner,
    )
    check("the deployment failed", status == 200, status)
    effects = json.dumps(fired.get("transition", {}).get("cascades", []))
    check(
        "the transition response names the coverage revocation",
        "AINV-5" in effects or "lost coverage" in effects,
        effects[:300],
    )

    status, after = call(
        "GET", "/compliance/frameworks/NIST-CSF-2.0/requirements", token=analyst
    )
    now = {r["ref"]: r for r in after["requirements"]}
    check(
        "the requirement lost coverage with nobody touching it",
        now["PR.PS-01"]["state"] == "Gap",
        now["PR.PS-01"]["state"],
    )
    check(
        "the record says why it lost coverage",
        bool(now["PR.PS-01"]["gap_reason"]),
        now["PR.PS-01"]["gap_reason"],
    )
    # PR.PS-01 and PR.DS-01 are both carried by CTL-002, so both are expected
    # to move. Everything else must be untouched: the cascade walks the links of
    # the failed control, not the register.
    carried = {"PR.PS-01", "PR.DS-01"}
    collateral = [
        ref
        for ref, state in untouched_before.items()
        if ref not in carried and now[ref]["state"] != state
    ]
    check(
        "both requirements carried by that control lost coverage",
        all(now[ref]["state"] == "Gap" for ref in carried),
        {ref: now[ref]["state"] for ref in carried},
    )
    check(
        "the cascade is targeted: nothing else changed state",
        not collateral,
        collateral,
    )

    status, posture_after = call("GET", "/compliance/posture", token=analyst)
    csf_after = next(
        f for f in posture_after["frameworks"] if f["framework_id"] == "NIST-CSF-2.0"
    )
    check(
        "the coverage figure fell with the control",
        csf_after["counts"]["Covered"] < csf_before["counts"]["Covered"],
        {"before": csf_before["counts"], "after": csf_after["counts"]},
    )

    section("Asset-level coverage informs rather than blocks")
    status, gaps = call("GET", "/compliance/gaps", token=analyst)
    gap_rows = {g["ref"]: g for g in gaps["gaps"]}
    check(
        "a gap row reports which in-scope assets the control does not reach",
        gap_rows["PR.AA-05"]["asset_coverage"]["in_scope"] > 0,
        gap_rows["PR.AA-05"].get("asset_coverage"),
    )
    check(
        "an excluded requirement is not reported as a gap",
        "PR.AA-06" not in gap_rows,
    )

    section("CINV-11: automation level caps control effectiveness")
    # CTL-005 is Semi_Automated. Drop it to Manual, then try to claim the top
    # rating on its deployment: the ceiling has to refuse it.
    call(
        "PATCH",
        "/controls/" + by_ref["CTL-005"]["id"],
        {"automation_level": "Manual"},
        token=control_owner,
    )
    status, ctl5 = call("GET", "/controls/" + by_ref["CTL-005"]["id"], token=analyst)
    dep5 = [d for a in ctl5["activities"] for d in a["deployments"]][0]
    status, body = call(
        "POST",
        "/controls/deployments/" + dep5["id"] + "/ce",
        {
            "ce_rating": "CE-High",
            "ce_evidence_ref": "Quarterly recertification sign-off, Q3 2026.",
        },
        token=control_owner,
    )
    check("a Manual control cannot claim CE-High", status >= 400, status)
    check("the refusal names CINV-11", "CINV-11" in json.dumps(body), body)

    status, body = call(
        "POST",
        "/controls/deployments/" + dep5["id"] + "/ce",
        {
            "ce_rating": "CE-Medium",
            "ce_evidence_ref": "Quarterly recertification sign-off, Q3 2026.",
        },
        token=control_owner,
    )
    check("the same control may hold CE-Medium, which Manual permits", status == 200, body)

    section("Every route answers")
    # /api/controls/reference-data raised a NameError for three commits. Nothing
    # caught it: the typecheck is frontend-only, no test called the route, and
    # the UI swallows the failure with `.catch(() => undefined)`, so the control
    # create form simply had empty Family and Type dropdowns. A route that
    # raises on every request is the cheapest possible bug to detect and this is
    # the check that detects it.
    status, spec = call("GET", "/openapi.json", token=analyst)
    if status != 200:
        check("the OpenAPI schema is available to enumerate routes", False, status)
    else:
        parameterless = sorted(
            path
            for path, ops in spec.get("paths", {}).items()
            if "get" in ops and "{" not in path and path.startswith("/api/")
        )
        check("routes discovered to sweep", len(parameterless) >= 10, len(parameterless))
        broken = []
        for path in parameterless:
            code, body = call("GET", path[len("/api"):], token=analyst)
            if code >= 500:
                broken.append((path, code, str(body)[:120]))
        check("no GET route returns a server error", not broken, broken)

    section("Engine introspection")
    status, machines = call("GET", "/engine/machines", token=analyst)
    check("8 state machines exposed", len(machines) == 8, len(machines))
    total_transitions = sum(len(m["transitions"]) for m in machines.values())
    check("transitions declared", total_transitions >= 40, total_transitions)
    status, cat = call("GET", "/engine/invariants", token=analyst)
    check("invariant catalogue served", cat["total"] >= 46, cat["total"])
    status, casc = call("GET", "/engine/cascades", token=analyst)
    check("cascade events registered", len(casc["events"]) >= 24, len(casc["events"]))
    check(
        "the mitigation-success cascade is registered (codified-rules 20.3)",
        any(e["event"] == "threat.scenario_mitigated" for e in casc["events"]),
        [e["event"] for e in casc["events"]],
    )

    section("Audit trail captured the whole run")
    status, audit = call("GET", "/audit?limit=500", token=ciso)
    actions = {a["action"] for a in audit}
    check("state transitions audited", "STATE_TRANSITION" in actions, actions)
    check("CE assessments audited", "CONTROL_TEST" in actions, actions)
    transition_entries = [a for a in audit if a["action"] == "STATE_TRANSITION"]
    check(
        "gate evaluation recorded with each transition",
        any("gate_evaluation" in a["changed_fields"] for a in transition_entries),
    )
    check(
        "cascade effects recorded with each transition",
        any(a["changed_fields"].get("cascades") for a in transition_entries),
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
