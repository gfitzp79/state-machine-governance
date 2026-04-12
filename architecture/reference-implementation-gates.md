# Reference Implementation: Threat Management Gates

**Version:** 1.0 | **Language:** Python (FastAPI / SQLAlchemy)
**Purpose:** This document provides concrete engineering reference code demonstrating how the theoretical gate preconditions and invariants specified in the Threat Management module must be enforced at the service layer.

---

## 1. State Transition Service (`threat_gates.py`)

This reference implements the API gate validation for the new `Abandoned` and `Returned_For_Rework` transitions, cleanly enforcing RBAC and state logic out-of-band of the REST router mapping.

```python
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.threat import ThreatModel, ThreatScenario, ThreatModelLifecycleState
from services.audit import audit_logger
from services.notification import notifier

class ThreatModelGateService:
    def __init__(self, db: Session):
        self.db = db

    def transition_to_abandoned(self, model_id: str, actor: dict, reason: str):
        """
        Transition a Threat Model from any state (except Active) to Abandoned.
        """
        # Precondition: Actor Role
        if actor.get("role") not in ["System_Owner", "GRC_Engineer"]:
            raise HTTPException(status_code=403, detail="Must be System_Owner or GRC_Engineer to abandon.")

        # Precondition: Reason length
        if not reason or len(reason.strip()) < 20:
            raise HTTPException(status_code=400, detail="Abandonment reasoning must be at least 20 characters.")

        model = self.db.query(ThreatModel).filter(ThreatModel.id == model_id).first()
        if not model:
            raise HTTPException(status_code=404, detail="Threat model not found")

        if model.lifecycle_state == ThreatModelLifecycleState.ACTIVE:
            raise HTTPException(status_code=400, detail="Cannot abandon an Active threat model.")

        # Precondition: All scenarios must be handled
        unhandled = self.db.query(ThreatScenario).filter(
            ThreatScenario.threat_model_id == model_id,
            ThreatScenario.status == "Identified"
        ).count()
        
        if unhandled > 0:
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
        notifier.send(model.system_owner_id, "Threat Model Abandoned", f"Model {model.tm_id} was abandoned. Reason: {reason}")
        
        return model

    def transition_returned_for_rework(self, model_id: str, actor: dict, reason: str):
        """
        Transition a Threat Model from Review back to Mitigation Design due to sign_off rejection.
        """
        if actor.get("role") not in ["AppSec_Lead", "AppSec_Engineer", "System_Owner"]:
            raise HTTPException(status_code=403, detail="Must be AppSec or System_Owner to return for rework.")

        if not reason or len(reason.strip()) < 20:
            raise HTTPException(status_code=400, detail="Rework reasoning must be at least 20 characters.")

        model = self.db.query(ThreatModel).filter(ThreatModel.id == model_id).first()
        if not model or model.lifecycle_state != ThreatModelLifecycleState.REVIEW:
            raise HTTPException(status_code=400, detail="Model is not in Review state.")

        # Transition execution
        # Lifecycle technically touches 'Returned_For_Rework' conceptually but persists as Mitigation_Design
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
```

---

## 2. Invariant Enforcement Service (`threat_scenarios.py`)

This demonstrates how absolute system invariants `TINV-5` and `TM-PARTIAL` are checked directly upon row mutations.

```python
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.threat import ThreatScenario, ThreatMitigationLink
from models.control import ControlDeployment

class ThreatScenarioGateService:
    def __init__(self, db: Session):
        self.db = db

    def update_scenario_status(self, scenario_id: str, payload: dict, actor: dict):
        scenario = self.db.query(ThreatScenario).filter(ThreatScenario.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        target_status = payload.get("status")

        # INVARIANT: TINV-5 (Local acceptance of low risks bounds)
        if target_status == "Accepted" and scenario.inherent_severity == "Low":
            acceptance_expiry = payload.get("acceptance_expiry")
            
            if not acceptance_expiry:
                raise HTTPException(status_code=400, detail="TINV-5: acceptance_expiry must be present when accepting a scenario.")
            
            # Ensure it is bounded to <= 365 days
            delta = acceptance_expiry - datetime.now(timezone.utc).date()
            if delta.days > 365 or delta.days <= 0:
                raise HTTPException(status_code=400, detail="TINV-5: acceptance_expiry must be a future date ≤ 365 days.")

        # INVARIANT: TM-PARTIAL (Mitigation validation via link table logic) & TINV-4
        if target_status == "Mitigated":
            links = self.db.query(ThreatMitigationLink).filter(
                ThreatMitigationLink.threat_scenario_id == scenario_id
            ).all()

            if not links:
                raise HTTPException(status_code=400, detail="TINV-4: Cannot mitigate a scenario with no linked controls.")

            # Validate partiality (TM-PARTIAL)
            for link in links:
                if link.effectiveness_assurance == "Partially_Mitigated":
                    raise HTTPException(
                        status_code=400, 
                        detail="TM-PARTIAL: Cannot set scenario to Mitigated while partially mitigating links persist."
                    )
                
                # Check control health directly against referenced structure (TINV-4)
                control = self.db.query(ControlDeployment).filter(
                    ControlDeployment.id == link.control_id
                ).first()
                if control.status != "Active":
                    raise HTTPException(
                        status_code=400, 
                        detail="TINV-4: Cannot mitigate scenario because linked control is not universally Active."
                    )

        # Update and save
        scenario.status = target_status
        if payload.get("acceptance_expiry"):
            scenario.acceptance_expiry = payload.get("acceptance_expiry")
        
        self.db.commit()
        audit_logger.record(scenario.id, "ThreatScenario", scenario.status, target_status, actor["id"], "Scenario status updated")
        
        return scenario
```
