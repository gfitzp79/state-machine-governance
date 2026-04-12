from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Assuming importing from local app structure
from services.threat_gates import ThreatModelGateService, ThreatScenarioGateService

router = APIRouter(prefix="/threat-models", tags=["threat-models"])
scenario_router = APIRouter(prefix="/threat-scenarios", tags=["threat-scenarios"])

# --- Mock schemas for request validation ---
class TransitionRequest(BaseModel):
    reason: str

class ScenarioUpdateRequest(BaseModel):
    status: str
    acceptance_expiry: Optional[datetime] = None

# --- Mock DB Dependency Dummy ---
def get_db():
    from services.threat_gates import DummyDB
    return DummyDB()

# --- Mock Current User Dummy ---
def get_current_user():
    return {"id": "user-uuid-1", "role": "System_Owner"}

# ==================================
# THREAT MODEL ENDPOINTS
# ==================================

@router.post("/{model_id}/transition/abandoned")
def transition_model_abandoned(
    model_id: str, 
    payload: TransitionRequest, 
    db=Depends(get_db), 
    current_user=Depends(get_current_user)
):
    """
    Executes the transition to Abandoned.
    """
    # ... mock DB lookup for model and scenarios ...
    class MockModel:
        id = model_id
        lifecycle_state = "Mitigation_Design"
        system_owner_id = "owner-uuid-0"
    
    mock_model = MockModel()
    mock_scenarios = [] # representing all identified correctly mitigated/accepted/closed
    
    service = ThreatModelGateService(db)
    updated_model = service.transition_to_abandoned(mock_model, current_user, payload.reason, mock_scenarios)
    return {"status": "success", "new_state": updated_model.lifecycle_state}


@router.post("/{model_id}/transition/returned-for-rework")
def transition_model_returned_for_rework(
    model_id: str, 
    payload: TransitionRequest, 
    db=Depends(get_db), 
    current_user=Depends(get_current_user)
):
    """
    Executes the transition explicitly returning a model for rework.
    """
    # ... mock DB lookup ...
    class MockModel:
        id = model_id
        lifecycle_state = "Review"
        system_owner_id = current_user["id"]
        created_by = "creator-uuid-0"
        signoff_at = datetime.now()
        signoff_by = "uuid-x"

    mock_model = MockModel()

    service = ThreatModelGateService(db)
    updated_model = service.transition_returned_for_rework(mock_model, current_user, payload.reason)
    return {"status": "success", "new_state": updated_model.lifecycle_state}


# ==================================
# THREAT SCENARIO ENDPOINTS
# ==================================

@scenario_router.patch("/{scenario_id}")
def update_threat_scenario(
    scenario_id: str, 
    payload: ScenarioUpdateRequest, 
    db=Depends(get_db), 
    current_user=Depends(get_current_user)
):
    """
    Update threat scenario, enforcing invariants TM-PARTIAL, TINV-4, and TINV-5.
    """
    # ... mock DB lookup ...
    class MockScenario:
        id = scenario_id
        status = "Identified"
        inherent_severity = "Low"
        acceptance_expiry = None

    class MockLink:
        effectiveness_assurance = "Fully_Mitigated"
        control_status = "Active"

    mock_scenario = MockScenario()
    mock_mitigation_links = [MockLink()]

    service = ThreatScenarioGateService(db)
    updated_scenario = service.update_scenario_status(
        mock_scenario, 
        payload.status, 
        payload.acceptance_expiry, 
        mock_mitigation_links, 
        current_user
    )
    
    return {"status": "success", "scenario_status": updated_scenario.status}
