"""S8-S12: acceptance, expiry, closure, retirement and deprecation."""
from lib import call, days, idof, msg, sql, state_of, TODAY


def _find(rows, ref):
    return next((x for x in rows if x.get("reference") == ref), None)


def s8_acceptance(r, ctx):
    r.section("S8  A Moderate risk is accepted, and the acceptance expires")
    assets = r.get("analyst", "/assets")
    idp = next(a for a in assets if "Identity" in a["name"])
    ctl001 = _find(r.get("analyst", "/controls"), "CTL-001")
    s, risk = r.do("analyst", "POST", "/risks", {
        "title": "Admin console reachable from VPN without device posture checks",
        "cause": "the admin console trusts any authenticated VPN session",
        "threat_event": "a compromised contractor laptop reaches the admin console",
        "vulnerability": "no device posture or managed-device requirement on the console route",
        "impact_statement": "unauthorised configuration change affecting workforce access and payment operations",
        "intake_source": "Assessment", "identified_by": "Quarterly access review",
        "tier": "Tier_2", "tier_rationale": "Workforce access process across several systems.",
        "risk_owner_id": r.uid("owner"), "risk_stakeholder_id": r.uid("ciso"),
        "risk_analyst_id": r.uid("analyst"),
    }, step="Analyst raises a new risk with the full statement")
    ctx["risk_vpn"] = rid = idof(risk)
    rp = f"/risks/{rid}"
    r.transition("analyst", rp, "Preconditions", step="Intake -> Preconditions")
    r.do("analyst", "POST", rp + "/assets", {"id": idp["id"]}, step="Scope: Corporate Identity Provider")
    r.do("analyst", "POST", rp + "/controls", {"id": ctl001["id"]}, step="MFA control (CTL-001) linked")
    r.do("analyst", "PATCH", rp, {"pre_true_risk_confirmed": True}, step="Triage confirmed")
    r.transition("analyst", rp, "Scoring", step="Preconditions -> Scoring")
    r.do("analyst", "POST", rp + "/score/inherent", {
        "impact": 3, "likelihood": 4, "impact_justification": "Configuration change, recoverable within a day.",
        "likelihood_justification": "Contractor endpoints are unmanaged."}, step="Inherent 3 x 4 = 12")
    r.transition("analyst", rp, "Treatment", step="Scoring -> Treatment")

    r.refused("analyst", "POST", rp + "/treatment-decision", {
        "treatment_strategy": "Accept", "acceptance_expiry_date": days(300),
        "acceptance_rationale": "Contractor programme ends in Q3.", "acceptance_approved_by": r.uid("owner")},
        "Acceptance beyond 180 days refused at Moderate (RINV-4)", None)
    r.refused("analyst", "POST", rp + "/treatment-decision", {
        "treatment_strategy": "Accept", "acceptance_expiry_date": days(150),
        "acceptance_rationale": "Contractor programme ends in Q3.", "acceptance_approved_by": r.uid("sysowner")},
        "A Director cannot approve a Moderate acceptance (VP required)", None)
    s, b = call("POST", rp + "/treatment-decision", {
        "treatment_strategy": "Accept", "acceptance_expiry_date": days(150),
        "acceptance_rationale": "Contractor programme ends in Q3; console access logged and reviewed weekly.",
        "acceptance_approved_by": r.uid("owner")}, r.tokens["analyst"])
    if s == 200:
        r.gap("The analyst names the VP as the acceptance approver; the VP never acts",
              "acceptance_approved_by is a field in the analyst's request.")
    else:
        r.check("The analyst cannot record an acceptance in the VP's name", True)
        s, b = call("POST", rp + "/treatment-decision", {
            "treatment_strategy": "Accept", "acceptance_expiry_date": days(150),
            "acceptance_rationale": "Contractor programme ends in Q3; console access logged and reviewed weekly."},
            r.tokens["owner"])
        r.check("The VP records the acceptance in person", s == 200, f"{s} {msg(b)}")

    r.transition("analyst", rp, "Readout", step="Treatment -> Readout")
    r.do("owner", "PATCH", rp, {"readout_confirmed": True, "readout_conducted_at": TODAY.isoformat() + "T09:00:00Z"},
         step="Owner confirms readout")
    r.transition("owner", rp, "Evidence_Residual", step="Readout -> Evidence_Residual")
    r.do("analyst", "PATCH", rp, {
        "gate_mitigations_implemented": True, "gate_evidence_provided": True, "gate_effectiveness_confirmed": True,
        "gate_governance_approved": True, "gate_drift_tracked": True,
        "evidence_ref": "Acceptance memo ACC-2026-014"}, step="Residual gate conditions recorded for an acceptance")
    r.note("An Accepted risk walks the same five residual conditions as a Mitigated one",
           "Mitigations implemented, effectiveness confirmed and drift tracked have no meaning for an "
           "acceptance, but the analyst must tick them to reach Monitoring.")
    r.do("analyst", "POST", rp + "/residual/unlock", None, step="Residual unlocked")
    r.do("analyst", "POST", rp + "/score/residual", {
        "residual_impact": 3, "residual_likelihood": 4, "residual_impact_rationale": "Accepted as is.",
        "residual_likelihood_rationale": "No treatment."}, step="Residual equals inherent")
    r.transition("analyst", rp, "Monitoring", step="Evidence_Residual -> Monitoring")

    # The acceptance lapses.
    sql(f"UPDATE risks SET acceptance_expiry_date = CURRENT_DATE - 1 WHERE id = '{rid}'")
    s, out = r.do("admin", "POST", "/engine/jobs/run", None, step="Scheduled jobs run after the expiry")
    risk = r.get("analyst", rp)
    r.note("Risk after its acceptance lapses",
           str({k: risk.get(k) for k in ("lifecycle_state", "escalation_flag", "escalation_reason",
                                          "treatment_strategy", "acceptance_expiry_date")}))
    n = r.get("owner", "/notifications") + r.get("analyst", "/notifications")
    r.check("Someone is told the acceptance lapsed",
            any("accept" in ((x.get("title") or "") + (x.get("body") or "")).lower() for x in n),
            "; ".join((x.get("title") or "") for x in n)[:300])


def s9_closure(r, ctx):
    r.section("S9  Closing and reopening a risk")
    rp = f"/risks/{ctx['risk_vpn']}"
    risk = r.get("analyst", rp)
    r.refused("analyst", "POST", rp + "/transition", {"target": "Closed", "reason": "Done."},
              "An analyst cannot close a risk", None)
    s, b = call("POST", rp + "/transition", {"target": "Closed",
                "reason": "Contractor programme wound down early."}, r.tokens["owner"])
    if s != 200 and "GATE_CLOSURE.1" in msg(b):
        r.record("FAIL", "Closing with a reason in the request is refused for want of a closure rationale",
                 "_closable reads risk.closure_rationale; on_transition writes the request's reason there only "
                 "after the gate passes. Re-assessment and reopen read the reason from the request instead.")
        r.do("owner", "PATCH", rp, {"closure_rationale": "Contractor programme wound down early."},
             step="Workaround: closure rationale PATCHed first")
        s, b = call("POST", rp + "/transition", {"target": "Closed", "reason": "x"}, r.tokens["owner"])
    if s == 200 and risk.get("appetite") == "Above Appetite":
        r.gap("A risk above appetite can be closed with one sentence",
              f"Closed at {risk.get('reported_score')} ({risk.get('reported_rating')}, {risk.get('appetite')}) "
              "with an expired acceptance. GATE_CLOSURE checks only that a rationale and a treatment decision exist.")
    else:
        r.check("Owner closes the risk", s == 200, f"{s} {msg(b)}")
    r.refused("owner", "POST", rp + "/transition", {"target": "Preconditions", "reason": "x"},
              "Only the CISO can reopen a closed risk", None)
    s, b = call("POST", rp + "/transition", {"target": "Preconditions",
                "reason": "Contractor access found still live."}, r.tokens["ciso"])
    if s != 200 and "RINV-8" in msg(b):
        r.record("FAIL", "A scored risk can never return to Preconditions: re-assessment and reopen are dead paths",
                 "RINV-8 requires impact and likelihood to be empty below phase 3, and nothing starts a new "
                 "scoring cycle on GATE_REASSESSMENT or GATE_REOPEN. Both transitions roll back.")
    else:
        r.check("CISO reopens it", s == 200, f"{s} {msg(b)}")
    risk = r.get("analyst", rp)
    r.note("Reopened risk", str({k: risk.get(k) for k in ("lifecycle_state", "inherent_risk_score",
                                                           "residual_score_locked", "treatment_strategy")}))
    s, b = call("POST", rp + "/score/inherent", {"impact": 4, "likelihood": 4,
                "impact_justification": "Wider than thought.", "likelihood_justification": "Access live."},
                r.tokens["analyst"])
    r.note("Re-scoring inherent after a reopen, from Preconditions", f"{s} {msg(b)}")


def s10_control_retirement(r, ctx):
    r.section("S10  Retiring controls")
    wp = f"/controls/{ctx['waf']}"
    r.refused("control", "POST", wp + "/transition", {"target": "Deprecated", "reason": "Replacing vendor."},
              "WAF cannot retire while it holds up an above-appetite Mitigate risk (CINV-8)", "CINV-8")

    s, obj = r.do("control", "POST", "/controls", {
        "title": "Quarterly manual review of WAF exclusions", "family": "Application_Security",
        "control_type": "Detective", "control_owner_id": r.uid("control"), "automation_level": "Manual",
        "implementation_type": "Administrative", "operating_frequency": "Quarterly",
        "assurance_method": "Inspection", "is_key_control": False}, step="A small detective control created")
    cid = idof(obj)
    s, act = r.do("control", "POST", "/controls/activities", {"objective_id": cid, "title": "Review exclusions"},
                  step="Its activity")
    aid = idof(act)
    r.transition("control", f"/controls/activities/{aid}", "Active", step="Activity active")
    s, dep = r.do("control", "POST", "/controls/deployments", {"activity_id": aid, "attack_surface_id": ctx["portal"],
                                                                "test_frequency": "Annual"}, step="Deployed on the portal")
    did = idof(dep)
    r.transition("control", f"/controls/{cid}", "Implementation", step="-> Implementation")
    r.transition("control", f"/controls/deployments/{did}", "Active", step="Deployment active")
    s, b = call("POST", f"/controls/deployments/{did}/ce", {"ce_rating": "CE-High", "ce_evidence_ref": "x"},
                r.tokens["control"])
    r.check("A Manual control cannot claim CE-High (CINV-11)", s in (409, 422), f"{s} {msg(b)}")
    r.do("control", "POST", f"/controls/deployments/{did}/ce", {"ce_rating": "CE-Medium", "ce_evidence_ref": "REV-Q4"},
         step="CE-Medium with evidence")
    r.transition("control", f"/controls/{cid}", "Operating", step="-> Operating")

    r.refused("control", "POST", f"/controls/activities/{aid}/transition", {"target": "Retired"},
              "Activity cannot retire while a deployment is live (AL-1)", "AL-1")
    r.refused("control", "POST", f"/controls/deployments/{did}/transition", {"target": "Decommissioned"},
              "Decommission needs a rationale (DL-3)", "DL-3")
    r.do("control", "PATCH", f"/controls/deployments/{did}", {"decommission_rationale": "Folded into WAF tuning."},
         step="Decommission rationale")
    r.transition("control", f"/controls/deployments/{did}", "Decommissioned", step="Deployment decommissioned")
    s, b = call("POST", f"/controls/deployments/{did}/ce", {"ce_rating": "CE-Low", "ce_evidence_ref": "late"},
                r.tokens["control"])
    r.check("A decommissioned deployment is read-only (CINV-4)", s in (409, 422), f"{s} {msg(b)}")
    r.transition("control", f"/controls/activities/{aid}", "Retired", step="Activity retired")
    r.do("control", "PATCH", f"/controls/{cid}", {"deprecation_rationale": "Superseded by WAF rule review."},
         step="Retirement rationale")
    r.transition("control", f"/controls/{cid}", "Deprecated", step="Control deprecated")
    obj = r.get("control", f"/controls/{cid}")
    r.note("A control objective, once Deprecated, can go no further", str(state_of(obj)))


def s11_policy_deprecation(r, ctx):
    r.section("S11  Deprecating a policy")
    pp = f"/policies/{ctx['pol']}"
    r.do("analyst", "POST", f"/risks/{ctx['risk_stuffing']}/policies", {"id": ctx["pol"]},
         step="Credential-stuffing risk linked to the policy")
    s, b = call("POST", pp + "/transition", {"target": "Deprecated", "reason": "Merged into AppSec standard."},
                r.tokens["ciso"])
    r.note("Deprecation with a High-inherent risk linked whose treatment is Complete", f"{s} {msg(b)}")
    if s != 200:
        r.do("ciso", "PATCH", pp, {"change_summary": "Controls re-mapped to POL-001 within 60 days."},
             step="Re-mapping plan recorded (PC-2)")
        s, b = call("POST", pp + "/transition", {"target": "Deprecated", "reason": "Merged."}, r.tokens["ciso"])
        r.note("Deprecation after the plan", f"{s} {msg(b)}")
    pol = r.get("policy", pp)
    if state_of(pol) == "Deprecated":
        n = r.get("control", "/notifications")
        r.check("Control owners are told to re-map (PC-2)",
                any("map" in ((x.get("title") or "") + (x.get("body") or "")).lower() for x in n),
                "; ".join((x.get("title") or "")[:50] for x in n[-5:]))
        r.transition("ciso", pp, "Under_Review", step="CISO reinstates it for review")


def s12_threat_model_end(r, ctx):
    r.section("S12  Re-signing, deprecating and abandoning threat models")
    tmp = f"/threat-models/{ctx['tm']}"
    s, b = call("POST", f"{tmp}/scenarios/{ctx['scen']['sqli']}/mitigate",
                {"deployment_id": ctx["waf_dep"], "effectiveness_assurance": "Fully_Mitigated"}, r.tokens["appsec"])
    if s != 200:
        r.gap("A scenario reopened by a control failure cannot simply be re-confirmed once the control is back",
              f"mitigate -> {s} {msg(b)}. The old link survives the failure, so AppSec must delete the "
              "mitigation and create it again to return the scenario to Mitigated.")
        tmd = r.get("appsec", tmp)
        sc = next(x for x in tmd["scenarios"] if x["id"] == ctx["scen"]["sqli"])
        for m in sc.get("mitigations", []):
            lid = m.get("link_id") or m.get("id")
            r.do("appsec", "DELETE", f"{tmp}/scenarios/{ctx['scen']['sqli']}/mitigations/{lid}",
                 step="Workaround: delete the surviving mitigation link")
        r.do("appsec", "POST", f"{tmp}/scenarios/{ctx['scen']['sqli']}/mitigate",
             {"deployment_id": ctx["waf_dep"], "effectiveness_assurance": "Fully_Mitigated"},
             step="...and create it again")
    r.do("appsec", "PATCH", f"{tmp}/scenarios/{ctx['scen']['sqli']}",
         {"status_rationale": "WAF repaired; blocking mode pinned."}, step="Rationale")
    call("POST", tmp + "/signoff", {"as_role": "appsec"}, r.tokens["appsec"])
    call("POST", tmp + "/signoff", {"as_role": "owner"}, r.tokens["sysowner"])
    r.transition("appsec", tmp, "Active", step="Model back to Active")
    r.refused("appsec", "POST", tmp + "/transition", {"target": "Deprecated"},
              "Deprecation needs a reason (TM-5)", "TM-5")
    r.transition("sysowner", tmp, "Deprecated", step="System owner deprecates the model",
                 reason="Portal replaced by the new customer app.")
    risk = r.get("analyst", f"/risks/{ctx['risk_stuffing']}")
    r.note("The promoted risk after its threat model is deprecated", str(risk.get("lifecycle_state")))

    s, tm2 = r.do("appsec", "POST", "/threat-models", {
        "title": "Partner API (abandoned)", "attack_surface_id": ctx["portal"],
        "system_owner_id": r.uid("sysowner"), "methodology": "STRIDE"}, step="A second model opened")
    t2 = f"/threat-models/{idof(tm2)}"
    r.refused("appsec", "POST", t2 + "/transition", {"target": "Abandoned"}, "Abandon needs a reason (TM-7)", "TM-7")
    r.transition("appsec", t2, "Abandoned", step="Abandoned before analysis", reason="Partner deal cancelled.")
