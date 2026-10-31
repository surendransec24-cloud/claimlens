from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any

CellAlignment = Literal["supports", "contradicts", "silent", "unclear"]

class ConsistencyCell(BaseModel):
    fact_id: str
    fact_statement: str
    evidence_id: str
    alignment: CellAlignment
    confidence: float = Field(ge=0.0, le=1.0)
    citation: str = Field(description="Evidence citation reference or quote")
    reasoning: str

class DiscrepancyPair(BaseModel):
    id: str
    title: str
    fact_id: str
    fact_statement: str
    contradicting_evidence_id: str
    evidence_citation: str
    severity: Literal["info", "review", "investigate"]
    description: str

class ConsistencyMatrix(BaseModel):
    facts: List[Dict[str, str]] = Field(default_factory=list, description="[{id: 'FACT-1', statement: '...'}]")
    evidence_ids: List[str] = Field(default_factory=list, description="['E1', 'E2', 'E3']")
    cells: List[ConsistencyCell] = Field(default_factory=list)
    discrepancies: List[DiscrepancyPair] = Field(default_factory=list)
    discrepancy_count: int = 0
    support_count: int = 0
    silent_count: int = 0
    unclear_count: int = 0

