from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import json

# ==========================================
# MOCK DEPENDENCIES (For Reference Architecture)
# ==========================================

class ThreatModelLifecycleState:
    SCOPE = "Scope"
    DECOMPOSITION = "Decomposition"
    THREAT_ANALYSIS = "Threat_Analysis"
    MITIGATION_DESIGN = "Mitigation_Design"
    REVIEW = "Review"
    ACTIVE = "Active"
    DEPRECATED = "Deprecated"
    ABANDONED = "Abandoned"
    RETURNED_FOR_REWORK = "Returned_For_Rework"

class DummyAuditLogger:
    def record(self, entity_id, entity_type, previous_state, new_state, actor_id, reason):
        print(f"AUDIT LOG: {entity_type} {entity_id} transitioned {previous_state} -> {new_state} by {actor_id}. Reason: {reason}")

class DummyNotifier:
    def send(self, user_id, title, message):
        print(f"NOTIFICATION to {user_id}: {title} - {message}")

class DummyDB:
    # A mocked database wrapper holding objects
    def query(self, model):
        pass
    def commit(self):
        pass

audit_logger = DummyAuditLogger()
notifier = DummyNotifier()

# ==========================================
# SERVICE LAYER ENFORCEMENT logic
# ==========================================

class ThreatModelGateService:
    def __init__(self, db):
        self.db = db

    def transition_to_abandoned(self, model, actor: dict, reason: str, linked_scenarios: list):
        """
        Transition a Threat Model from any state (except Active) to Abandoned.
        """
        # Precondition: Actor Role
        if actor.get("role") not in ["System_Owner", "GRC_Engineer"]:
            raise HTTPException(status_code=403, detail="Must be System_Owner or GRC_Engineer to abandon.")

        # Precondition: Reason length
        if not reason or len(reason.strip()) < 20:
            raise HTTPException(status_code=400, detail="Abandonment reasoning must be at least 20 characters.")

        if model.lifecycle_state == ThreatModelLifecycleState.ACTIVE:
            raise HTTPException(status_code=400, detail="Cannot abandon an Active threat model.")

        # Precondition: All scenarios must be handled
        unhandled = [s for s in linked_scenarios if s.status == "Identified"]
        if unhandled:
            raise HTTPException(
                status_code=400, 
                detail="Cannot abandon model. All identified scenarios must be explicitly closed, mitigated, or transferred."
            )

        # Transition execution
        old_state = model.lifecycle_state
        model.lifecycle_state = ThreatModelLifecycleState.ABANDONED
        
        # Auditing & Cascade
        self.db.commit()
        audit_logger.record(model.id, "ThreatModel", old_state, "Abandoned", actor["id"], reason)
        notifier.send(model.system_owner_id, "Threat Model Abandoned", f"Model {model.id} was abandoned. Reason: {reason}")
        
        return model

    def transition_returned_for_rework(self, model, actor: dict, reason: str):
        """
        Transition a Threat Model from Review back to Mitigation Design due to sign_off rejection.
        """
        if actor.get("role") not in ["AppSec_Lead", "AppSec_Engineer", "System_Owner"]:
            raise HTTPException(status_code=403, detail="Must be AppSec or System_Owner to return for rework.")

        if not reason or len(reason.strip()) < 20:
            raise HTTPException(status_code=400, detail="Rework reasoning must be at least 20 characters.")

        if model.lifecycle_state != ThreatModelLifecycleState.REVIEW:
            raise HTTPException(status_code=400, detail="Model is not in Review state.")

        # Transition execution
        model.lifecycle_state = ThreatModelLifecycleState.MITIGATION_DESIGN
        
        # Clear any existing partial sign_offs
        model.signoff_at = None
        model.signoff_by = None
        
        # Auditing & Cascade
        self.db.commit()
        audit_logger.record(model.id, "ThreatModel", "Review", "Returned_For_Rework", actor["id"], reason)
        notifier.send(model.system_owner_id, "Threat Model Requires Rework", f"Reason: {reason}")
        if model.created_by != model.system_owner_id:
            notifier.send(model.created_by, "Threat Model Requires Rework", f"Reason: {reason}")

        return model

class ThreatScenarioGateService:
    def __init__(self, db):
        self.db = db

    def update_scenario_status(self, scenario, target_status: str, acceptance_expiry: Optional[datetime], linked_mitigations: list, actor: dict):
        # INVARIANT: TINV-5
        if target_status == "Accepted" and scenario.inherent_severity == "Low":
            if not acceptance_expiry:
                audit_logger.record(scenario.id, "ThreatScenario", scenario.status, target_status, actor["id"], "VIOLATION ATTEMPT: TINV-5 blocked. Missing expiry.")
                raise HTTPException(status_code=400, detail="TINV-5: acceptance_expiry must be present when accepting a Low severity scenario.")
            
            delta = acceptance_expiry.date() - datetime.now(timezone.utc).date()
            if delta.days > 365 or delta.days <= 0:
                audit_logger.record(scenario.id, "ThreatScenario", scenario.status, target_status, actor["id"], "VIOLATION ATTEMPT: TINV-5 blocked. Expiry out of bounds.")
                raise HTTPException(status_code=400, detail="TINV-5: acceptance_expiry must be a future date <= 365 days.")

        # INVARIANT: TM-PARTIAL & TINV-4
        if target_status == "Mitigated":
            if not linked_mitigations:
                audit_logger.record(scenario.id, "ThreatScenario", scenario.status, target_status, actor["id"], "VIOLATION ATTEMPT: TINV-4 blocked. No links.")
                raise HTTPException(status_code=400, detail="TINV-4: Cannot mitigate a scenario with no linked controls.")

            for link in linked_mitigations:
                if link.effectiveness_assurance == "Partially_Mitigated":
                    audit_logger.record(scenario.id, "ThreatScenario", scenario.status, target_status, actor["id"], "VIOLATION ATTEMPT: TM-PARTIAL blocked.")
                    raise HTTPException(status_code=400, detail="TM-PARTIAL: Cannot set scenario to Mitigated while partially mitigating links persist.")
                
                # Check control status (TINV-4 requirement)
                if getattr(link, 'control_status', None) != "Active":
                    audit_logger.record(scenario.id, "ThreatScenario", scenario.status, target_status, actor["id"], "VIOLATION ATTEMPT: TINV-4 blocked. Linked control not Active.")
                    raise HTTPException(status_code=400, detail="TINV-4: Cannot mitigate scenario because a linked control is not universally Active.")

        # Valid transition
        old_status = scenario.status
        scenario.status = target_status
        if acceptance_expiry:
            scenario.acceptance_expiry = acceptance_expiry

        self.db.commit()
        audit_logger.record(scenario.id, "ThreatScenario", old_status, target_status, actor["id"], "Scenario status updated")
        return scenario
