from pydantic import BaseModel, Field
from typing import List, Optional, Literal

PolicyEvaluationStatus = Literal["covered", "excluded", "unclear"]

class CoverageType(BaseModel):
    name: str = Field(description="e.g. Collision, Comprehensive, Liability")
    limit: float = Field(description="Maximum policy coverage limit in dollars")
    deductible: float = Field(description="Applicable deductible in dollars")
    clause_ref: str = Field(description="Policy clause reference, e.g. Section 2.1")

class PolicyExclusion(BaseModel):
    name: str = Field(description="Exclusion name, e.g. Commercial Use, Unlicensed Driver")
    description: str = Field(description="Exclusion condition summary")
    clause_ref: str = Field(description="Clause reference, e.g. Section 4.2")

class PolicyCondition(BaseModel):
    name: str
    requirement: str
    clause_ref: str

class PolicyRuleSet(BaseModel):
    policy_number: str
    policyholder_name: str
    vehicle_vin: Optional[str] = None
    policy_period_start: str
    policy_period_end: str
    coverages: List[CoverageType] = Field(default_factory=list)
    exclusions: List[PolicyExclusion] = Field(default_factory=list)
    conditions: List[PolicyCondition] = Field(default_factory=list)

class PolicyEvaluationItem(BaseModel):
    aspect: str = Field(description="e.g. Policy Active Period, Collision Coverage, Commercial Use Exclusion")
    status: PolicyEvaluationStatus = Field(description="covered, excluded, or unclear")
    rationale: str = Field(description="Detailed legal/contractual reasoning applied to claim facts")
    clause_cited: str = Field(description="Exact policy section/clause reference, e.g. Section 4.2")

class PolicyAnalysis(BaseModel):
    rules: PolicyRuleSet
    evaluations: List[PolicyEvaluationItem] = Field(default_factory=list)
    applicable_deductible: float = Field(default=500.0)
    applicable_limit: float = Field(default=50000.0)
    overall_coverage_status: PolicyEvaluationStatus = Field(default="covered")
    summary: str = Field(default="")

