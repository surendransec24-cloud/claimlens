from pydantic import BaseModel, Field
from typing import List, Optional

class TimelineEvent(BaseModel):
    step_number: int
    timestamp_or_phase: str
    description: str
    source_evidence_ids: List[str]
    citation: str
    confidence: float = 1.0

class ImpactVector(BaseModel):
    impact_direction: str = Field(description="e.g. 12 o'clock (head-on), 6 o'clock (rear), 9 o'clock (driver side)")
    relative_speed_estimate: str
    primary_damage_point: str
    secondary_damage_points: List[str] = Field(default_factory=list)
    rebound_trajectory: Optional[str] = None

class ReconstructionAnalysis(BaseModel):
    timeline: List[TimelineEvent] = Field(default_factory=list)
    impact_model: ImpactVector
    physical_damage_compatibility_score: float = Field(ge=0.0, le=1.0)
    is_damage_consistent_with_narrative: bool
    compatibility_explanation: str
    reconstruction_diagram_notes: str = ""

