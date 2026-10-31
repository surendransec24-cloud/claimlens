from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

DamageZone = Literal["front", "rear", "left", "right", "roof", "glass"]
SeverityLevel = Literal["minor", "moderate", "severe"]

class DamagedZoneDetail(BaseModel):
    zone: DamageZone
    severity: SeverityLevel
    description: str
    bounding_box: Optional[List[float]] = Field(default=None, description="[ymin, xmin, ymax, xmax] normalized coordinates")

class PhotoAnalysis(BaseModel):
    evidence_id: str
    file_name: str
    damaged_zones: List[DamagedZoneDetail] = Field(default_factory=list)
    visible_vehicle_details: Dict[str, Any] = Field(default_factory=dict, description="Color, make/model clues, plate if visible")
    image_quality_issues: List[str] = Field(default_factory=list, description="Blur, glare, resolution, low light")
    tampering_or_inconsistency_notes: List[str] = Field(default_factory=list, description="Signs of editing, compression artifacts, unexpected lighting")
    exif_timestamp: Optional[str] = None
    exif_gps: Optional[Dict[str, float]] = None
    stated_timestamp_match: Optional[bool] = None
    stated_location_match: Optional[bool] = None
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    summary: str = Field(default="")

