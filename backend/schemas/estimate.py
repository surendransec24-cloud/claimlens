from pydantic import BaseModel, Field
from typing import List, Optional

class EstimateLineItem(BaseModel):
    item_number: int
    description: str
    zone: str = Field(description="front, rear, left, right, roof, glass, mechanical")
    part_cost: float = 0.0
    labor_hours: float = 0.0
    labor_rate: float = 0.0
    labor_cost: float = 0.0
    total_cost: float = 0.0
    matches_vision_damage: bool = True
    discrepancy_note: Optional[str] = None

class EstimateAnalysis(BaseModel):
    line_items: List[EstimateLineItem] = Field(default_factory=list)
    total_parts: float = 0.0
    total_labor: float = 0.0
    grand_total: float = 0.0
    computed_sum: float = 0.0
    arithmetic_valid: bool = True
    arithmetic_discrepancy_amount: float = 0.0
    phantom_line_items: List[EstimateLineItem] = Field(default_factory=list, description="Items with no matching physical damage in photos")
    labor_outliers: List[str] = Field(default_factory=list)
    parts_outliers: List[str] = Field(default_factory=list)
    approved_total: float = 0.0
    flagged_total: float = 0.0

