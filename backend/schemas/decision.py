from pydantic import BaseModel, Field
from typing import List, Dict, Any

class SettlementBreakdown(BaseModel):
    total_claimed_estimate: float = 0.0
    deductible: float = 0.0
    policy_limit: float = 50000.0
    undisputed_amount: float = 0.0
    disputed_or_flagged_amount: float = 0.0
    coverage_status: str = "covered"
    settlement_minimum: float = 0.0
    settlement_maximum: float = 0.0
    formula_applied: str

class DecisionSupportOutput(BaseModel):
    settlement_range: SettlementBreakdown
    missing_evidence: List[str] = Field(default_factory=list)
    recommended_investigation_steps: List[str] = Field(default_factory=list)
    status_label: str = Field(default="AI recommendation, pending human review")
    summary: str

