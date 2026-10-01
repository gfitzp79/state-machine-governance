"""S3 and S4: the promoted risk from Intake to Monitoring, with its treatment."""
from lib import call, days, idof, msg, state_of, TODAY


def s3_risk_lifecycle(r, ctx):
    r.section("S3  The promoted risk, Intake to Monitoring, with a treatment that builds a control")
    rid = ctx["risk_stuffing"]
    rp = f"/risks/{rid}"
    risk = r.get("analyst", rp)
    r.check("Promoted risk lands in Intake", risk.get("lifecycle_state") == "Intake", str(risk.get("lifecycle_state")))
    r.check("Intake source is Threat_Model", risk.get("intake_source") == "Threat_Model", str(risk.get("intake_source")))
    r.check("Risk owner defaulted to the system owner (holds Risk_Owner)",
            risk.get("risk_owner_id") == r.uid("sysowner"), str(risk.get("risk_owner_id")))
    r.check("Analyst left empty: the promoter (AppSec) is not a Risk_Analyst",
            not risk.get("risk_analyst_id"), str(risk.get("risk_analyst_id")))
    filled = {k: bool(risk.get(k)) for k in ("cause", "threat_event", "vulnerability", "impact_statement")}
    r.note("Risk statement fields filled by promotion", str(filled))
    ctx["risk_keys"] = sorted(risk.keys())
    links = None
    for k in ("threat_links", "threat_scenarios", "threats", "source_scenarios"):
        if k in risk:
            links = risk[k]
    if links is None:
        r.gap("Risk detail does not show which threat scenario it came from",
              "No threat link on the risk payload; the scenario points at the risk but not the reverse.")
    else:
        r.check("Risk detail links back to its threat scenario", bool(links), str(links)[:200])

    s, b = call("POST", rp + "/transition", {"target": "Preconditions"}, r.tokens["analyst"])
    if s != 200:
        r.note("Intake gate after promotion", f"{s} {msg(b)}")
        r.do("analyst", "PATCH", rp, {
            "cause": "customers reuse passwords breached elsewhere and the portal accepts password-only login",
            "threat_event": "an attacker replays breached credentials at scale against the login endpoint",
            "vulnerability": "no multi-factor authentication or adaptive rate limiting on customer login",
        }, step="Analyst completes the structured risk statement")
        r.transition("analyst", rp, "Preconditions", step="Intake -> Preconditions")
    else:
        r.check("Intake -> Preconditions", True)

    r.do("analyst", "POST", rp + "/assets", {"id": ctx["portal"]}, step="Scope declared: the portal")
    r.do("analyst", "PATCH", rp, {
        "pre_true_risk_confirmed": True, "tier": "Tier_3",
        "tier_rationale": "Scoped to the portal and the customer accounts it fronts.",
        "risk_stakeholder_id": r.uid("ciso"), "risk_analyst_id": r.uid("analyst"),
    }, step="Triage, tier, stakeholder and analyst recorded")

    s, b = call("POST", rp + "/transition", {"target": "Scoring"}, r.tokens["analyst"])
    r.check("Scoring refused with no control linked (RINV-8.4)", s == 409 and "RINV-8.4" in msg(b), f"{s} {msg(b)}")
    r.gap("A risk that exists because a control is missing cannot be scored until some control is linked",
          "RINV-8.4 needs an Operating control with evidence before inherent scoring, but inherent "
          "scoring ignores CE by design (LKH-3). For credential stuffing the honest answer is 'no "
          "relevant control yet', so the analyst links an adjacent control (the WAF) to get past the gate.")

    r.do("analyst", "POST", rp + "/controls", {"id": ctx["waf"]}, step="WAF linked (bot management is adjacent)")
    r.transition("analyst", rp, "Scoring", step="Preconditions -> Scoring")

    s, b = call("POST", rp + "/score/inherent", {"impact": 4, "likelihood": 4}, r.tokens["analyst"])
    r.note("Inherent score accepted without justification; IMP-2 is enforced at the Scoring gate instead",
           f"{s}")
    r.do("analyst", "POST", rp + "/score/inherent", {
        "impact": 4, "likelihood": 4,
        "impact_justification": "Account takeover enables fraudulent payments for affected customers.",
        "likelihood_justification": "Credential stuffing against consumer logins is continuous and automated.",
    }, step="Inherent 4 x 4 scored with justification")
    risk = r.get("analyst", rp)
    r.check("Inherent rating derived as High (16)", risk.get("inherent_rating") == "High"
            and risk.get("inherent_risk_score") == 16,
            f"{risk.get('inherent_risk_score')} {risk.get('inherent_rating')}")
    r.transition("analyst", rp, "Treatment", step="Scoring -> Treatment")
    r.refused("analyst", "POST", rp + "/score/inherent", {
        "impact": 2, "likelihood": 2, "impact_justification": "x", "likelihood_justification": "x"},
        "Inherent score frozen once the risk leaves Scoring")

    # -- treatment: the two lifecycles interleave in practice ---------------
    s, trt = r.do("analyst", "POST", "/treatments", {
        "title": "Customer MFA and adaptive rate limiting on the portal",
        "description": "Roll out passkey or TOTP MFA for customers and per-account velocity limits.",
        "treatment_type": "Mitigate", "treatment_owner_id": r.uid("delivery"),
        "target_date": days(60), "loe": "M", "check_in_frequency": "Fortnightly",
        "expected_impact_delta": 0, "expected_likelihood_delta": -1,
        "loe_implementation_hours": 320, "cost_implementation": 45000,
    }, step="Analyst proposes a treatment owned by delivery")
    ctx["trt"] = idof(trt)
    tp = f"/treatments/{ctx['trt']}"
    r.check("Treatment starts Proposed", state_of(trt) == "Proposed", str(state_of(trt)))
    r.do("analyst", "POST", rp + "/treatments", {"id": ctx["trt"], "is_primary": True},
         step="Treatment linked to the risk")

    r.refused("delivery", "POST", tp + "/validate", {"notes": "self"},
              "Treatment owner cannot validate their own treatment (SEP-5)")
    r.do("grc", "POST", tp + "/validate", {"notes": "IdP supports customer MFA; rate limiting via WAF rules."},
         step="GRC engineer validates feasibility")
    r.do("delivery", "POST", tp + "/commit", None, step="Treatment owner commits")

    r.do("analyst", "POST", rp + "/treatment-decision", {
        "treatment_strategy": "Mitigate",
        "control_framework_mapping": "NIST CSF PR.AA-03 (authentication); new control: customer MFA.",
    }, step="Treatment decision: Mitigate")
    r.transition("analyst", rp, "Readout", step="Treatment -> Readout")

    r.refused("analyst", "POST", rp + "/transition", {"target": "Evidence_Residual"},
              "Readout cannot complete without the owner's confirmation (RINV-6)", "RINV-6")
    r.do("sysowner", "PATCH", rp, {"readout_confirmed": True,
                                   "readout_conducted_at": TODAY.isoformat() + "T10:00:00Z"},
         step="Risk owner confirms the readout")
    r.transition("sysowner", rp, "Evidence_Residual", step="Readout -> Evidence_Residual (by the owner)")

    # Phase 6 attestation probe.
    s, b = call("PATCH", rp, {"gate_mitigations_implemented": True}, r.tokens["analyst"])
    gates = r.get("analyst", rp + "/gates")
    res1 = None
    for g in (gates if isinstance(gates, list) else gates.get("gates", [])):
        for c in g.get("checks", []):
            if c.get("id") == "RESIDUAL.1":
                res1 = c.get("passed")
    if res1:
        r.record("FAIL", "RESIDUAL.1 ('every linked treatment Complete') satisfied by a tick while the treatment is not Complete",
                 "PATCH gate_mitigations_implemented=true -> " + str(s) + "; gate check reports passed")
    else:
        r.check("RESIDUAL.1 is read from the treatments, not from a tick", True)

    # The unlock endpoint is a second door to the same score. Does it read the same records?
    call("PATCH", rp, {"gate_evidence_provided": True, "gate_effectiveness_confirmed": True,
                       "gate_governance_approved": True, "gate_drift_tracked": True,
                       "evidence_ref": "pending"}, r.tokens["analyst"])
    s_unlock, b = call("POST", rp + "/residual/unlock", None, r.tokens["analyst"])
    s_score, b2 = call("POST", rp + "/score/residual", {
        "residual_impact": 4, "residual_likelihood": 3,
        "residual_impact_rationale": "x", "residual_likelihood_rationale": "x"}, r.tokens["analyst"])
    early = r.get("analyst", rp)
    if s_unlock == 200 and s_score == 200:
        r.record("FAIL", "Five ticks unlock the residual and a reduced score is reported before any treatment is complete",
                 f"unlock {s_unlock}, residual score {s_score}; reported now "
                 f"{early.get('reported_score')} {early.get('reported_rating')} with the treatment still "
                 f"{state_of(r.get('analyst', tp))}. The Monitoring gate derives RESIDUAL.1 from the "
                 "treatments; release_residual_lock reads only the five booleans.")
    else:
        r.check("Residual stays locked until the treatments are complete", True)

    tr = r.get("analyst", tp)
    r.note("Treatment state after validate and commit", str(state_of(tr)))
    # Abuse first: can the treatment owner approve a request assigned to the risk owner?
    s, det = r.do("analyst", "POST", tp + "/approvals",
                  {"approval_type": "treatment_approval", "assigned_to": r.uid("sysowner")},
                  step="Approval requested from the risk owner")
    if not (det or {}).get("approvals"):
        r.note("POST /approvals returns the treatment with an empty approvals list",
               "The response is built before the new row is loaded; the caller must re-read to find it.")
    det = r.get("analyst", tp)
    aid = (det.get("approvals") or [{}])[-1].get("id")
    s, b = call("POST", f"{tp}/approvals/{aid}/decide", {"decision": "Approved", "notes": "self"},
                r.tokens["delivery"])
    if s == 200:
        r.record("FAIL", "The treatment owner approved their own treatment (request was assigned to the risk owner)",
                 "decide_approval checks only that the decider is not the requester: no assigned_to "
                 "check, no role check. A deadline extension can be self-approved the same way.")
    else:
        r.check("Only the assigned approver can decide", True)
    s, b = call("POST", f"{tp}/approvals/{aid}/decide", {"decision": "Approved", "notes": "Go."},
                r.tokens["sysowner"])
    r.check("Risk owner approves", s == 200, f"{s} {msg(b)}")
    s, b = call("POST", f"{tp}/approvals/{aid}/decide", {"decision": "Rejected", "notes": "changed my mind"},
                r.tokens["ciso"])
    if s == 200:
        r.record("FAIL", "A recorded approval decision can be overwritten",
                 "Second decide on the same request returned 200.")
    else:
        r.check("A recorded decision cannot be overwritten", True)
    tr = r.get("analyst", tp)
    if state_of(tr) == "Proposed":
        r.transition("grc", tp, "Validated", step="Treatment Proposed -> Validated")
    r.transition("sysowner", tp, "Approved", step="Treatment Validated -> Approved")
    r.transition("delivery", tp, "In_Progress", step="Treatment Approved -> In_Progress")

    r.refused("delivery", "POST", tp + "/transition", {"target": "Complete"},
              "Complete refused with no evidence or check-in")
    r.do("delivery", "POST", tp + "/checkins",
         {"status": "On_Track", "notes": "MFA enrolment live for 40% of customers."},
         step="Fortnightly check-in")

    # The treatment builds a new control.
    s, obj = r.do("control", "POST", "/controls", {
        "title": "Customer multi-factor authentication", "family": "Identity_Management",
        "control_type": "Preventive", "control_owner_id": r.uid("control"),
        "objective_statement": "Customer logins require a second factor.",
        "automation_level": "Semi_Automated", "implementation_type": "Technical",
        "operating_frequency": "Continuous", "assurance_method": "Inspection", "is_key_control": True,
    }, step="Control owner creates the customer MFA control")
    ctx["mfa"] = idof(obj)
    s, act = r.do("control", "POST", "/controls/activities", {
        "objective_id": ctx["mfa"], "title": "Enforce MFA at customer login",
        "control_operator_id": r.uid("control"), "automation_level": "Semi_Automated"},
        step="MFA activity")
    ctx["mfa_act"] = idof(act)
    r.transition("control", f"/controls/activities/{ctx['mfa_act']}", "Active", step="MFA activity active")
    s, dep = r.do("control", "POST", "/controls/deployments", {
        "activity_id": ctx["mfa_act"], "attack_surface_id": ctx["portal"], "test_frequency": "Quarterly"},
        step="MFA deployment planned on the portal")
    ctx["mfa_dep"] = idof(dep)
    r.transition("control", f"/controls/{ctx['mfa']}", "Implementation", step="MFA objective -> Implementation")
    r.transition("control", f"/controls/deployments/{ctx['mfa_dep']}", "Active", step="MFA deployment -> Active")
    r.do("control", "POST", f"/controls/deployments/{ctx['mfa_dep']}/ce", {
        "ce_rating": "CE-Medium", "ce_evidence_ref": "EVID-MFA-rollout-dashboard",
        "ce_notes": "Enrolment incomplete; step-up not yet on all flows."}, step="MFA assessed CE-Medium")
    r.transition("control", f"/controls/{ctx['mfa']}", "Operating", step="MFA objective -> Operating")
    r.do("analyst", "POST", rp + "/controls", {"id": ctx["mfa"]}, step="MFA control linked to the risk")

    r.do("delivery", "PATCH", tp, {"evidence_ref": "CHG-4411 rollout report"},
         step="Implementation evidence recorded")
    r.transition("delivery", tp, "Complete", step="Treatment In_Progress -> Complete")

    r.do("analyst", "PATCH", rp, {
        "gate_mitigations_implemented": True, "gate_evidence_provided": True,
        "gate_effectiveness_confirmed": True, "gate_governance_approved": True,
        "gate_drift_tracked": True, "evidence_ref": "CHG-4411; EVID-MFA-rollout-dashboard",
    }, step="Analyst records the five residual gate conditions")
    r.do("analyst", "POST", rp + "/residual/unlock", None, step="Residual unlocked")
    ce = r.get("analyst", rp + "/ce-resolution")
    r.check("Effective CE is the worst in scope: CE-Medium", ce.get("effective_ce") == "CE-Medium",
            str(ce.get("effective_ce")))
    r.refused("analyst", "POST", rp + "/score/residual", {
        "residual_impact": 4, "residual_likelihood": 2,
        "residual_impact_rationale": "Impact unchanged.", "residual_likelihood_rationale": "MFA."},
        "Two levels of reduction refused under CE-Medium (RINV-9, reported as LKH-1)", "LKH-1")
    r.do("analyst", "POST", rp + "/score/residual", {
        "residual_impact": 4, "residual_likelihood": 3,
        "residual_impact_rationale": "Controls reduce likelihood, not consequence (IMP-4).",
        "residual_likelihood_rationale": "CE-Medium across the in-scope deployments permits one level.",
    }, step="Residual 4 x 3 = 12 recorded")
    r.transition("analyst", rp, "Monitoring", step="Evidence_Residual -> Monitoring")
    risk = r.get("analyst", rp)
    r.check("Residual rating Moderate (12)", risk.get("residual_rating") == "Moderate",
            str(risk.get("residual_rating")))
    r.check("Next review date set from the Moderate cadence (60 days)",
            risk.get("next_review_date") == days(60), str(risk.get("next_review_date")))
    r.note("Appetite fields after treatment",
           str({k: risk.get(k) for k in risk if "appetite" in k or k.startswith("reported")}))
