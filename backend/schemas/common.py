from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class SourceRef(BaseModel):
    evidence_id: str = Field(description="Evidence identifier, e.g. E1, E2")
    location: str = Field(description="Specific location: page, clause, photo region, sentence number, line")
    snippet: Optional[str] = Field(default=None, description="Direct quote or specific snippet if text")

FindingSeverity = Literal["info", "review", "investigate"]

class FindingSchema(BaseModel):
    id: str = Field(description="Unique finding identifier, e.g. F-001")
    title: str = Field(description="Clear title of the discrepancy or insight")
    severity: FindingSeverity = Field(description="Severity: info, review, or investigate")
    inconsistency: str = Field(description="Exact conflict description citing at least two evidence sources")
    possible_explanations: List[str] = Field(
        min_length=2,
        description="At least two alternative explanations, explicitly including innocent/unintentional reasons"
    )
    missing_evidence: List[str] = Field(description="Specific items or records that would definitively resolve this")
    recommended_action: str = Field(description="One concrete next action for the claims adjuster")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    confidence_explanation: str = Field(description="Plain-language description of what remains unknown or uncertain")
    sources: List[SourceRef] = Field(min_length=1, description="List of source citations")

