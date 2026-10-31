from pydantic import BaseModel, Field
from typing import List, Optional

class ClaimFact(BaseModel):
    category: str = Field(description="Category, e.g. date_time, location, impact_direction, parties, speed, injuries, events")
    fact: str = Field(description="Normalized structured statement of fact")
    sentence_citation: str = Field(description="Direct quotation of the exact sentence from the claimant's narrative")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

class NarrativeAnalysis(BaseModel):
    incident_date: Optional[str] = Field(default=None, description="Stated incident date (YYYY-MM-DD)")
    incident_time: Optional[str] = Field(default=None, description="Stated incident time (HH:MM or approximate)")
    incident_location: Optional[str] = Field(default=None, description="Stated location or intersection")
    impact_direction: Optional[str] = Field(default=None, description="Stated direction of impact: rear-ended, head-on, side-impact, etc.")
    other_parties: Optional[str] = Field(default=None, description="Other vehicles/drivers mentioned")
    speed_mph: Optional[str] = Field(default=None, description="Claimed vehicle speed")
    injuries: Optional[str] = Field(default=None, description="Claimed physical injuries")
    claimed_sequence_of_events: List[str] = Field(default_factory=list, description="Step-by-step chronology stated by claimant")
    structured_facts: List[ClaimFact] = Field(default_factory=list, description="Extracted atomic facts with sentence citations")
    weather_claimed: Optional[str] = Field(default=None, description="Any weather conditions claimed in the narrative")

