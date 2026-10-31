from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from backend.schemas.common import FindingSchema
from backend.schemas.vision import PhotoAnalysis
from backend.schemas.narrative import NarrativeAnalysis
from backend.schemas.policy import PolicyAnalysis
from backend.schemas.context import ContextAnalysis
from backend.schemas.estimate import EstimateAnalysis
from backend.schemas.consistency import ConsistencyMatrix
from backend.schemas.reconstruction import ReconstructionAnalysis
from backend.schemas.hypothesis import HypothesisReport
from backend.schemas.decision import DecisionSupportOutput
from backend.schemas.verifier import VerifierResult

class AgentExecutionStatus(BaseModel):
    agent_name: str
    status: str = "pending"  # pending, running, completed, degraded, failed
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: Optional[str] = None

class CaseState(BaseModel):
    case_id: str
    claim_number: str
    evidence_ids: List[str] = Field(default_factory=list)
    agent_statuses: Dict[str, AgentExecutionStatus] = Field(default_factory=dict)
    
    # Independent Agent Outputs
    photo_analyses: Dict[str, PhotoAnalysis] = Field(default_factory=dict)  # evidence_id -> PhotoAnalysis
    narrative_analysis: Optional[NarrativeAnalysis] = None
    policy_analysis: Optional[PolicyAnalysis] = None
    context_analysis: Optional[ContextAnalysis] = None
    estimate_analysis: Optional[EstimateAnalysis] = None
    
    # Synthesis Outputs
    consistency_matrix: Optional[ConsistencyMatrix] = None
    reconstruction_analysis: Optional[ReconstructionAnalysis] = None
    hypothesis_report: Optional[HypothesisReport] = None
    decision_support: Optional[DecisionSupportOutput] = None
    findings: List[FindingSchema] = Field(default_factory=list)
    verifier_result: Optional[VerifierResult] = None
    
    # Re-reasoning & Diff
    previous_findings: Optional[List[FindingSchema]] = None
    findings_diff: Optional[Dict[str, Any]] = None
    
    overall_status: str = "idle"  # idle, running, completed, degraded

