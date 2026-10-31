from pydantic import BaseModel, Field
from typing import List, Optional

class StatementVerification(BaseModel):
    statement_id: str
    text_preview: str
    has_valid_citation: bool
    cited_evidence_ids: List[str]
    has_prohibited_terms: bool
    prohibited_terms_found: List[str] = Field(default_factory=list)
    sanitized_text: Optional[str] = None
    passed: bool

class VerifierResult(BaseModel):
    passed: bool
    citation_coverage_pct: float = Field(ge=0.0, le=100.0)
    prohibited_terms_detected: int = 0
    total_statements_checked: int = 0
    passed_statements_count: int = 0
    rejected_and_sanitized_count: int = 0
    verifier_log: List[str] = Field(default_factory=list)
    timestamp: str

