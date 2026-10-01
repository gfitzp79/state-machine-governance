"""S5 policy, S6 compliance, S7 the WAF fails and recovers."""
from lib import call, days, idof, msg, sql, state_of, TODAY


def s5_policy(r, ctx):
    r.section("S5  A policy from Draft to Active, revised, with exceptions")
    s, pol = r.do("policy", "POST", "/policies", {
        "title": "Web Application Security Standard", "policy_type": "Information_Security",
        "scope": "All customer-facing web applications and their APIs.",
        "purpose": "Set minimum protections for internet-facing applications.",
        "body": "1. All customer-facing applications sit behind a managed WAF in blocking mode. "
                "2. Customer authentication requires a second factor.",
        "review_cycle": "Annual", "compliance_mappings": ["NIST-CSF"],
        "policy_owner_id": r.uid("policy"),
    }, step="Policy owner drafts the standard")
    ctx["pol"] = pid = idof(pol)
    pp = f"/policies/{pid}"
    r.check("Policy starts in Draft", state_of(pol) == "Draft", str(state_of(pol)))
    r.transition("policy", pp, "Under_Review", step="Draft -> Under_Review")

    # Who can put an approval on the record?
    s, b = call("POST", pp + "/approve", {"approver_id": r.uid("policy")}, r.tokens["policy"])
    r.check("Policy owner cannot approve their own policy (PINV-5)", s in (409, 422), f"{s} {msg(b)}")
    s, b = call("POST", pp + "/approve", {"approver_id": r.uid("ciso")}, r.tokens["policy"])
    if s == 200:
        r.record("FAIL", "The policy owner recorded the CISO's approval without the CISO doing anything",
                 "POST /approve takes approver_id from the body and checks that person's role, not the "
                 "caller's. Any user can put a CISO's name on an approval.")
    else:
        r.check("Only the approver can record their own approval", True)
        r.do("ciso", "POST", pp + "/approve", {}, step="CISO approves in person")
    r.transition("ciso", pp, "Approved", step="Under_Review -> Approved (CISO)")

    r.refused("policy", "POST", pp + "/transition", {"target": "Active"},
              "Activation refused with no linked control (PINV-1)", "PINV-1")
    r.do("policy", "POST", pp + "/controls", {"id": ctx["waf"]}, step="WAF linked to the policy")
    r.do("policy", "POST", pp + "/controls", {"id": ctx["mfa"]}, step="MFA linked to the policy")
    r.do("policy", "PATCH", pp, {"effective_date": TODAY.isoformat()}, step="Effective date set to today")
    r.transition("policy", pp, "Active", step="Approved -> Active")

    ctl = r.get("control", f"/controls/{ctx['waf']}")
    pol_links = ctl.get("linked_policies")
    r.check("The control shows the policy it implements", bool(pol_links), "keys: " + ",".join(sorted(ctl))[:300])

    # Revision
    s, b = call("POST", pp + "/transition", {"target": "Under_Revision"}, r.tokens["policy"])
    if s != 200:
        r.note("Revision without a trigger", f"{s} {msg(b)}")
        r.transition("policy", pp, "Under_Revision", step="Active -> Under_Revision with trigger",
                     reason="Audit finding: bot management not referenced.")
    r.do("policy", "PATCH", pp, {"body": "1. WAF in blocking mode with bot management. 2. MFA for customers.",
                                 "version": "1.1", "change_summary": "Added bot management after audit finding."},
         step="Body revised, version 1.1, change summary")
    pol_now = r.get("policy", pp)
    stale = pol_now.get("approved_by") == r.uid("ciso") or pol_now.get("approved_by") == r.uid("policy")
    s, b = call("POST", pp + "/transition", {"target": "Approved"}, r.tokens["ciso"])
    if s == 200 and stale:
        r.gap("A revision is approved on the strength of the previous version's approval record",
              "approved_by from v1.0 still satisfies PINV-5 for v1.1; nobody re-approves the new text "
              "except by firing the transition.")
    else:
        r.note("Revision approval", f"{s} {msg(b)}")
    r.transition("policy", pp, "Active", step="Revision back to Active")
    pol_now = r.get("policy", pp)
    versions = pol_now.get("versions") or []
    r.check("Each approved version is kept", len(versions) >= 2, f"{len(versions)} version rows")

    # Exceptions
    s, exc = r.do("sysowner", "POST", "/exceptions", {
        "policy_id": pid, "title": "Legacy marketing microsite outside the WAF",
        "business_justification": "Vendor-hosted microsite; migration scheduled for Q2.",
        "risk_statement": "Unfiltered traffic to a site with no customer data.",
        "compensating_controls": "IP allowlisting on the admin path; weekly scan.",
        "expiry_date": days(120)}, step="System owner requests a 120-day exception")
    ctx["exc"] = eid = idof(exc)
    r.check("Exception starts Requested", state_of(exc) == "Requested", str(state_of(exc)))
    r.transition("policy", f"/exceptions/{eid}", "Approved", step="Policy owner approves it")
    ex = r.get("policy", f"/exceptions/{eid}")
    r.check("Approval records who approved", ex.get("approved_by") == r.uid("policy"), str(ex.get("approved_by")))
    s, b = call("PATCH", f"/exceptions/{eid}", {"approved_by": r.uid("ciso")}, r.tokens["sysowner"])
    if s == 200:
        r.record("FAIL", "The requester can write any approver's id onto their own exception",
                 "PATCH /exceptions/{id} accepts approved_by from the requester.")

    s, long = r.do("sysowner", "POST", "/exceptions", {
        "policy_id": pid, "title": "Partner API without MFA", "business_justification": "Partner contract.",
        "risk_statement": "Partner credentials are a single factor.", "expiry_date": days(500)},
        step="A 500-day exception requested, with no compensating controls")
    lid = idof(long)
    r.refused("policy", "POST", f"/exceptions/{lid}/transition", {"target": "Approved"},
              "Policy owner cannot approve beyond 365 days (PE-1)", "PE-1")
    s, b = call("POST", f"/exceptions/{lid}/transition", {"target": "Approved"}, r.tokens["ciso"])
    r.check("CISO can approve up to 730 days", s == 200, f"{s} {msg(b)}")
    notes = r.get("sysowner", "/notifications")
    lref = r.get("policy", f"/exceptions/{lid}").get("reference")
    if not any(lref and lref in (n.get("title") or "") for n in notes):
        r.gap("An exception with no compensating controls is approved with no escalation (PE-2)",
              "codified-rules PE-2: without compensating controls -> auto-escalate for risk promotion. "
              "No risk was created and no notification mentions it.")
    else:
        r.check("An uncompensated exception escalates toward the register (PE-2)", True)

    # Time passes: the 120-day exception expires.
    sql(f"UPDATE policy_exceptions SET expiry_date = CURRENT_DATE - 1 WHERE id = '{eid}'")
    r.do("admin", "POST", "/engine/jobs/run", None, step="Scheduled jobs run")
    ex = r.get("policy", f"/exceptions/{eid}")
    r.check("The lapsed exception is Expired", state_of(ex) == "Expired", str(state_of(ex)))
    notes = r.get("ciso", "/notifications")
    r.check("The CISO is told about the expiry (PE-5)",
            any("expir" in ((n.get("title") or "") + (n.get("body") or "")).lower() for n in notes),
            f"{len(notes)} notifications for the CISO")


def s6_compliance(r, ctx):
    r.section("S6  The WAF evidences a NIST CSF requirement")
    fw = next(f for f in r.get("analyst", "/compliance/frameworks")["frameworks"]
              if f["framework_id"] == "NIST-CSF-2.0")
    reqs = r.get("analyst", f"/compliance/frameworks/{fw['id']}/requirements")
    rows = reqs if isinstance(reqs, list) else reqs.get("requirements", [])
    req = next((q for q in rows if str(q.get("ref") or q.get("requirement_id") or "").startswith("PR.IR-01")), None) \
        or next((q for q in rows if "PR.IR" in str(q)), rows[0])
    ctx["req"] = qid = req["id"]
    ref = req.get("ref") or req.get("requirement_id")
    r.note("Requirement used", f"{ref}: {(req.get('title') or req.get('text') or '')[:80]}")
    qp = f"/compliance/requirements/{qid}"

    r.refused("grc", "POST", qp + "/assess", {"target": "Not_Applicable"},
              "Exclusion without justification refused (AINV-1)", "AINV-1")
    r.do("grc", "POST", qp + "/assess", {"target": "Applicable", "rationale": "Portal is internet-facing.",
                                         "owner_id": r.uid("control")}, step="Requirement marked Applicable")
    r.do("grc", "POST", qp + "/controls", {"objective_id": ctx["waf"], "coverage_level": "Partial",
                                           "rationale": "WAF covers application traffic only."},
         step="WAF linked as Partial coverage")
    r.refused("grc", "POST", qp + "/assess", {"target": "Covered"},
              "A Partial link alone does not cover (AINV-3)", None)
    s, links = call("GET", f"/compliance/controls/{ctx['waf']}/requirements", None, r.tokens["grc"])
    link_id = next((row["link_id"] for row in (links or {}).get("requirements", [])
                    if row.get("ref") == ref), None)
    r.do("grc", "PATCH", f"/compliance/links/{link_id}", {"coverage_level": "Full"}, step="Link upgraded to Full")
    r.do("grc", "POST", qp + "/assess", {"target": "Covered"}, step="Requirement Covered by the live WAF")
    posture = r.get("analyst", "/compliance/posture")
    r.note("Posture after coverage", str(posture)[:300])


def s7_failure_cascade(r, ctx):
    r.section("S7  The WAF fails its quarterly test, and is repaired")
    rid = ctx["risk_stuffing"]
    before_risk = r.get("analyst", f"/risks/{rid}")
    r.do("control", "POST", f"/controls/deployments/{ctx['waf_dep']}/tests", {
        "result": "Fail", "evidence_ref": "TEST-WAF-Q1-FAIL",
        "notes": "Rule set reverted to detect-only after a vendor update."}, step="WAF test recorded as Fail")

    dep = r.get("control", f"/controls/deployments/{ctx['waf_dep']}")
    obj = r.get("control", f"/controls/{ctx['waf']}")
    r.check("Deployment is Failed", state_of(dep) == "Failed", str(state_of(dep)))
    r.check("Objective is in Failure (DL-1)", state_of(obj) == "Failure", str(state_of(obj)))

    risk = r.get("analyst", f"/risks/{rid}")
    r.note("The Monitoring risk after its linked control fails",
           str({k: risk.get(k) for k in ("lifecycle_state", "residual_score_locked", "escalation_flag",
                                         "escalation_reason", "reported_score", "reported_rating")}))
    ce = r.get("analyst", f"/risks/{rid}/ce-resolution")
    r.note("CE resolution after the failure", f"effective {ce.get('effective_ce')}, "
           f"contributing {len(ce.get('contributing', []))}, excluded {len(ce.get('excluded', []))}")
    if risk.get("reported_score") == before_risk.get("reported_score") and not risk.get("residual_score_locked"):
        r.gap("The reported residual does not move when the control behind it fails",
              f"Reported score stays {risk.get('reported_score')} ({risk.get('reported_rating')}) while the WAF "
              "is Failed and resolved CE has changed. The risk keeps claiming a reduction the controls no longer earn.")

    tmd = r.get("appsec", f"/threat-models/{ctx['tm']}")
    sqli = next(s for s in tmd["scenarios"] if s["id"] == ctx["scen"]["sqli"])
    r.check("The injection scenario mitigated by the WAF is reopened (TINV-4)",
            sqli["status"] != "Mitigated", sqli["status"])
    r.note("Threat model state after the failure", str(state_of(tmd)))

    s, assess = call("GET", f"/compliance/controls/{ctx['waf']}/requirements", None, r.tokens["grc"])
    state = [x.get("state") for x in (assess or {}).get("requirements", [])]
    r.check("The covered requirement falls to Gap (AINV-5)", state == ["Gap"], str(state))

    pol = r.get("policy", f"/policies/{ctx['pol']}")
    r.note("Policy after its control fails", str({k: pol.get(k) for k in ("lifecycle_state", "health", "control_health")}))
    for who in ("analyst", "sysowner", "control", "policy", "ciso", "appsec"):
        n = r.get(who, "/notifications")
        r.note(f"Notifications for {who}", str(len(n)) + ": " + "; ".join((x.get("title") or "")[:60] for x in n[:4]))

    # Remediation
    r.refused("control", "POST", f"/controls/deployments/{ctx['waf_dep']}/transition", {"target": "Active"},
              "Failed -> Active refused without fresh evidence (DL-4)", "DL-4")
    r.do("control", "POST", f"/controls/deployments/{ctx['waf_dep']}/ce", {
        "ce_rating": "CE-High", "ce_evidence_ref": "EVID-WAF-remediated", "ce_notes": "Blocking mode restored."},
        step="CE re-assessed after the fix")
    r.transition("control", f"/controls/deployments/{ctx['waf_dep']}", "Active", step="Deployment Failed -> Active")
    r.do("control", "PATCH", f"/controls/{ctx['waf']}", {"remediation_plan": "Pinned rule set; change alert on mode."},
         step="Remediation plan recorded")
    r.transition("control", f"/controls/{ctx['waf']}", "Operating", step="Objective Failure -> Operating")
    r.do("control", "POST", f"/controls/deployments/{ctx['waf_dep']}/tests", {
        "result": "Pass", "evidence_ref": "TEST-WAF-RETEST"}, step="Retest Pass")

    tmd = r.get("appsec", f"/threat-models/{ctx['tm']}")
    sqli = next(s for s in tmd["scenarios"] if s["id"] == ctx["scen"]["sqli"])
    r.note("Injection scenario after the repair", f"{sqli['status']}; model {state_of(tmd)}")
    if sqli["status"] != "Mitigated":
        r.note("Recovery is manual for the threat model",
               "The scenario stays reopened until AppSec re-links the mitigation; nothing restores it.")
    s, assess = call("GET", f"/compliance/controls/{ctx['waf']}/requirements", None, r.tokens["grc"])
    state = [x.get("state") for x in (assess or {}).get("requirements", [])]
    r.note("Requirement after the repair", str(state))
    risk = r.get("analyst", f"/risks/{ctx['risk_stuffing']}")
    r.note("Risk after the repair", str({k: risk.get(k) for k in ("lifecycle_state", "residual_score_locked", "reported_score", "reported_rating")}))
    if risk.get("residual_score_locked"):
        r.gap("After the control is repaired, the risk stays at its inherent score until someone re-traverses it",
              "The failure froze the residual (correct). Nothing tells the analyst the control is back, and "
              "the only route to re-score is Monitoring -> Preconditions, four gates from the residual.")
