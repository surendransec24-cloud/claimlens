from pydantic import BaseModel, Field
from typing import List

class AlternativeExplanation(BaseModel):
    explanation: str = Field(description="Plausible scenario explaining the discrepancy")
    is_innocent: bool = Field(description="True if scenario represents an innocent mistake, environmental effect, secondary impact, or clerical error")
    plausibility: str = Field(description="low, moderate, high")
    discriminating_evidence: str = Field(description="Specific evidence item or verification that would distinguish this explanation")

class DiscrepancyHypotheses(BaseModel):
    discrepancy_id: str
    title: str
    explanations: List[AlternativeExplanation] = Field(
        min_length=2,
        description="At least two explanations, including innocent ones"
    )

class HypothesisReport(BaseModel):
    items: List[DiscrepancyHypotheses] = Field(default_factory=list)

