"""A mid-sized payments company launches a customer self-service portal.

Everything below is created from nothing, by the person whose job it would be,
and driven through its full lifecycle. The point is not to re-test each
invariant (smoke_test.py does that against seed data) but to see whether the
objects work together the way a real governance team would need them to.
"""
from __future__ import annotations

import sys

from lib import Run, call, days, idof, msg, sql, state_of, TODAY
import stage3
import stage4
import stage5

r = Run()
ctx: dict = {}


def scenario_id(model, description):
    return next((s["id"] for s in (model or {}).get("scenarios", [])
                 if s["description"] == description), None)


# ===========================================================================
def s1_asset_and_control():
    r.section("S1  A new asset and a control taken from Design to Operating")

    s, asset = r.do("sysowner", "POST", "/assets", {
        "name": "Customer Self-Service Portal", "tier": "Tier_1",
        "description": "Internet-facing portal where customers manage cards and payments.",
        "system_owner_id": r.uid("sysowner"),
    }, step="System owner registers the portal as a Tier 1 asset")
    ctx["portal"] = idof(asset)

    s, b = r.do("admin", "POST", f"/compliance/assets/{ctx['portal']}/scopes",
                {"compliance_scopes": ["NIST-CSF-2.0"]},
                step="Portal placed in NIST CSF scope")

    s, obj = r.do("control", "POST", "/controls", {
        "title": "Web application firewall on customer-facing applications",
        "description": "Managed WAF with OWASP core rule set and bot management.",
        "family": "Application_Security", "control_type": "Preventive",
        "control_owner_id": r.uid("control"),
        "objective_statement": "Malicious HTTP traffic is blocked before it reaches customer applications.",
        "automation_level": "Automated", "implementation_type": "Technical",
        "operating_frequency": "Continuous", "assurance_method": "Inspection",
        "is_key_control": True,
    }, step="Control owner creates the WAF control objective")
    ctx["waf"] = idof(obj)
    r.check("New objective starts in Design", state_of(obj) == "Design", str(state_of(obj)))

    r.refused("control", "POST", f"/controls/{ctx['waf']}/transition",
              {"target": "Implementation"},
              "Design -> Implementation refused with no activity or deployment plan", "OL-1")

    s, act = r.do("control", "POST", "/controls/activities", {
        "objective_id": ctx["waf"], "title": "Operate WAF policy on the portal edge",
        "control_operator_id": r.uid("control"), "automation_level": "Automated",
        "operating_frequency": "Continuous", "procedure_ref": "RUN-WAF-001",
        "tooling": "Cloud WAF", "evidence_type": "Configuration_Export",
    }, step="Activity defined")
    ctx["waf_act"] = idof(act)
    r.check("Activity starts in Draft", state_of(act) == "Draft", str(state_of(act)))

    s, dep = r.do("control", "POST", "/controls/deployments", {
        "activity_id": ctx["waf_act"], "attack_surface_id": ctx["portal"],
        "test_frequency": "Quarterly",
    }, step="Deployment planned on the portal")
    ctx["waf_dep"] = idof(dep)
    if s >= 400:
        r.note("Deployment against a Draft activity", msg(dep))
        r.transition("control", f"/controls/activities/{ctx['waf_act']}", "Active",
                     step="Activity activated first")
        s, dep = r.do("control", "POST", "/controls/deployments", {
            "activity_id": ctx["waf_act"], "attack_surface_id": ctx["portal"],
            "test_frequency": "Quarterly"}, step="Deployment planned after activation")
        ctx["waf_dep"] = idof(dep)
    else:
        r.transition("control", f"/controls/activities/{ctx['waf_act']}", "Active",
                     step="Activity Draft -> Active")

    r.check("Deployment starts Planned", state_of(dep) == "Planned", str(state_of(dep)))

    r.transition("control", f"/controls/{ctx['waf']}", "Implementation",
                 step="Objective Design -> Implementation")

    r.refused("control", "POST", f"/controls/{ctx['waf']}/transition", {"target": "Operating"},
              "Implementation -> Operating refused while no deployment is live", "OL-4")

    r.transition("control", f"/controls/deployments/{ctx['waf_dep']}", "Active",
                 step="Deployment Planned -> Active")

    r.refused("control", "POST", f"/controls/deployments/{ctx['waf_dep']}/ce",
              {"ce_rating": "CE-High"}, "CE-High without evidence is refused", "CINV-1")

    r.do("control", "POST", f"/controls/deployments/{ctx['waf_dep']}/ce", {
        "ce_rating": "CE-High", "ce_evidence_ref": "EVID-WAF-2026-Q4-config-export",
        "ce_notes": "Rule set and blocking mode verified in production.",
    }, step="CE-High assessed with evidence")

    r.transition("control", f"/controls/{ctx['waf']}", "Operating",
                 step="Objective Implementation -> Operating")

    s, t = r.do("control", "POST", f"/controls/deployments/{ctx['waf_dep']}/tests", {
        "result": "Pass", "evidence_ref": "TEST-WAF-Q4", "notes": "Quarterly test passed.",
    }, step="First quarterly test recorded as Pass")

    d = r.get("control", f"/controls/deployments/{ctx['waf_dep']}")
    r.check("Deployment shows next test due date after a Pass",
            bool(d.get("next_test_due")), str({k: d.get(k) for k in ("last_tested_date", "next_test_due")}))


# ===========================================================================
def s2_threat_model():
    r.section("S2  Threat modelling the portal, from Scope to Active")

    s, tm = r.do("appsec", "POST", "/threat-models", {
        "title": "Customer Self-Service Portal", "attack_surface_id": ctx["portal"],
        "system_owner_id": r.uid("sysowner"), "appsec_partner_id": r.uid("appsec"),
        "description": "Launch threat model.", "methodology": "STRIDE",
    }, step="AppSec opens a threat model on the portal")
    ctx["tm"] = idof(tm)
    r.check("Model starts in Scope", state_of(tm) == "Scope", str(state_of(tm)))
    tmp = f"/threat-models/{ctx['tm']}"

    r.transition("appsec", tmp, "Decomposition", step="Scope -> Decomposition")

    r.refused("appsec", "POST", tmp + "/transition", {"target": "Threat_Analysis"},
              "Analysis refused before any component exists", "TM-2")

    comps = {}
    for key, body in {
        "web": {"name": "Portal web front end", "component_type": "Process",
                "data_classification": "Confidential", "data_types": ["PII", "Credentials"],
                "trust_zone": "DMZ", "exposure": "Internet_Facing",
                "attack_surface_id": ctx["portal"]},
        "api": {"name": "Customer account API", "component_type": "Process",
                "data_classification": "Restricted", "data_types": ["PII", "Payment_Card"],
                "trust_zone": "Internal_Network", "exposure": "Internal_Only",
                "attack_surface_id": ctx["portal"]},
        "db": {"name": "Customer profile store", "component_type": "Datastore",
               "data_classification": "Restricted", "data_types": ["PII", "Payment_Card"],
               "trust_zone": "Restricted_Enclave", "exposure": "Isolated",
               "attack_surface_id": ctx["portal"]},
        "status": {"name": "Public status page", "component_type": "Process",
                   "data_classification": "Public", "data_types": ["Public_Content"],
                   "exposure": "Internet_Facing", "attack_surface_id": ctx["portal"]},
    }.items():
        s, m = r.do("appsec", "POST", tmp + "/components", body, step=f"Component: {body['name']}")
        comps[key] = next((c["id"] for c in (m or {}).get("components", []) if c["name"] == body["name"]), None)
    ctx["comps"] = comps

    r.transition("appsec", tmp, "Threat_Analysis", step="Decomposition -> Threat_Analysis")

    scen = {}
    for key, body in {
        "sqli": {"component_id": comps["api"], "category": "Tampering",
                 "description": "Injection through account update endpoints alters customer records.",
                 "inherent_severity": "High"},
        "stuffing": {"component_id": comps["web"], "category": "Spoofing",
                     "description": "Credential stuffing against customer login takes over accounts.",
                     "inherent_severity": "High"},
        "errors": {"component_id": comps["status"], "category": "Information_Disclosure",
                   "description": "Verbose errors on the status page reveal framework versions.",
                   "inherent_severity": "Low"},
    }.items():
        s, m = r.do("appsec", "POST", tmp + "/scenarios", body, step=f"Scenario: {key} ({body['inherent_severity']})")
        scen[key] = scenario_id(m, body["description"])
    ctx["scen"] = scen

    r.transition("appsec", tmp, "Mitigation_Design", step="Threat_Analysis -> Mitigation_Design")

    # TINV-11: the restricted datastore has no scenario yet.
    r.do("appsec", "POST", f"{tmp}/scenarios/{scen['sqli']}/mitigate", {
        "deployment_id": ctx["waf_dep"], "effectiveness_assurance": "Fully_Mitigated",
    }, step="Injection mitigated by the live WAF deployment")
    r.do("appsec", "PATCH", f"{tmp}/scenarios/{scen['sqli']}",
         {"status_rationale": "WAF in blocking mode with OWASP CRS; parameterised queries."},
         step="Mitigation rationale recorded")

    r.refused("appsec", "POST", f"{tmp}/scenarios/{scen['stuffing']}/accept",
              {"acceptance_expiry": days(90), "acceptance_rationale": "Low traffic at launch."},
              "A High scenario cannot be accepted locally", "TINV-3")

    s, promo = r.do("appsec", "POST", f"{tmp}/scenarios/{scen['stuffing']}/promote", {
        "tier": "Tier_3",
        "impact_statement": "customer account takeover leading to fraudulent payments, "
                            "customer harm and regulatory notification",
    }, step="Credential stuffing promoted to the risk register")
    ctx["risk_stuffing"] = ((promo or {}).get("promoted_risk") or {}).get("id")
    r.check("Promotion returns the new risk id", bool(ctx["risk_stuffing"]), str(promo)[:300])

    r.do("appsec", "POST", f"{tmp}/scenarios/{scen['errors']}/accept", {
        "acceptance_expiry": days(180),
        "acceptance_rationale": "Versions are public in our changelog; no secrets exposed.",
    }, step="Low scenario accepted locally with expiry and rationale")

    s, b = call("POST", tmp + "/transition", {"target": "Review"}, r.tokens["appsec"])
    r.check("Mitigation_Design -> Review", s == 200, f"{s} {msg(b)}")

    s, b = call("POST", tmp + "/signoff", {"as_role": "appsec"}, r.tokens["appsec"])
    r.check("AppSec sign-off", s == 200, f"{s} {msg(b)}")
    s, b = call("POST", tmp + "/signoff", {"as_role": "owner"}, r.tokens["sysowner"])
    r.check("System owner sign-off", s == 200, f"{s} {msg(b)}")

    s, b = call("POST", tmp + "/transition", {"target": "Active"}, r.tokens["appsec"])
    r.check("Active refused: the Restricted datastore has no scenario", s == 409 and "TINV-11" in msg(b),
            f"{s} {msg(b)}")

    s, sc = r.do("appsec", "POST", tmp + "/scenarios", {
        "component_id": comps["db"], "category": "Information_Disclosure",
        "description": "Backups of the profile store exfiltrated from object storage.",
        "inherent_severity": "Medium"}, step="Scenario added for the datastore")
    scen["backup"] = scenario_id(sc, "Backups of the profile store exfiltrated from object storage.")
    after = r.get("appsec", tmp)
    still_signed = bool(after.get("appsec_signoff_by")) and bool(after.get("owner_signoff_by"))
    if still_signed:
        r.gap("Adding a scenario after both sign-offs leaves the sign-offs standing",
              "The signatories approved a model that has since changed. "
              f"signoff_stripped_reason={after.get('signoff_stripped_reason')!r}")
    else:
        r.check("Adding a scenario after sign-off strips the sign-offs", True)
    s, b = call("POST", tmp + "/transition", {"target": "Active"}, r.tokens["appsec"])
    r.note("A new scenario during Review", f"Active attempt -> {s} {msg(b)}")

    # Link the Medium datastore scenario to the seed's unencrypted-PII risk.
    risks = r.get("analyst", "/risks")
    pii = next((x for x in risks if x["reference"] == "RISK-003"), None)
    if pii:
        s, b = r.do("appsec", "POST", f"{tmp}/scenarios/{scen['backup']}/risks", {
            "risk_id": pii["id"], "link_type": "Represents",
            "rationale": "The register already carries unencrypted PII exposure."},
            step="Medium scenario resolved by referencing an existing risk (TINV-8)")
    s, b = call("POST", tmp + "/transition", {"target": "Active"}, r.tokens["appsec"])
    if s != 200:
        r.note("Activation after adding a scenario in Review", f"{s} {msg(b)}")
        # sign-offs may have been invalidated by the change
        call("POST", tmp + "/signoff", {"as_role": "appsec"}, r.tokens["appsec"])
        call("POST", tmp + "/signoff", {"as_role": "owner"}, r.tokens["sysowner"])
        s, b = call("POST", tmp + "/transition", {"target": "Active"}, r.tokens["appsec"])
    r.check("Threat model reaches Active", s == 200, f"{s} {msg(b)}")
    tmd = r.get("appsec", tmp)
    ctx["tm_state"] = state_of(tmd)


# ===========================================================================
def main():
    r.login_all()
    stages = [s1_asset_and_control, s2_threat_model, lambda: stage3.s3_risk_lifecycle(r, ctx),
              lambda: stage4.s5_policy(r, ctx), lambda: stage4.s6_compliance(r, ctx),
              lambda: stage4.s7_failure_cascade(r, ctx),
              lambda: stage5.s8_acceptance(r, ctx), lambda: stage5.s9_closure(r, ctx),
              lambda: stage5.s10_control_retirement(r, ctx), lambda: stage5.s11_policy_deprecation(r, ctx),
              lambda: stage5.s12_threat_model_end(r, ctx)]
    upto = int(sys.argv[1]) if len(sys.argv) > 1 else len(stages)
    for fn in stages[:upto]:
        try:
            fn()
        except Exception as exc:  # a harness error is not a product finding
            r.record("HARN", f"{fn.__name__} crashed", repr(exc)[:400])
            break
    failures = r.summary(str(__import__("pathlib").Path(__file__).with_name("results.json")))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
