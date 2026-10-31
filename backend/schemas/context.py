from pydantic import BaseModel, Field
from typing import List, Optional

class WeatherData(BaseModel):
    temperature_c: float
    precipitation_mm: float
    weather_code: int
    condition_description: str
    wind_speed_kmh: float
    is_historical_recorded: bool = True
    contradicts_claim: bool = False
    details: str = Field(description="Comparison between claimed conditions and meteorological records")

class PriorClaimMatch(BaseModel):
    claim_id: int
    incident_date: str
    damage_zone: str
    payout_amount: float
    garage_name: str
    similarity_reason: str

class ContextAnalysis(BaseModel):
    weather: Optional[WeatherData] = None
    prior_claims: List[PriorClaimMatch] = Field(default_factory=list)
    days_since_policy_start: Optional[int] = None
    short_tenure_flag: bool = False
    repeat_claimant_flag: bool = False
    recurrent_damage_flag: bool = False
    notes: List[str] = Field(default_factory=list)

