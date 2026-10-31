from sqlalchemy import Column, String, Float, Text, DateTime, Integer, ForeignKey
from datetime import datetime
from backend.database import Base

class Finding(Base):
    __tablename__ = "findings"

    db_id = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String, index=True)  # F-001, F-002...
    case_id = Column(String, ForeignKey("cases.id"), index=True)
    title = Column(String)
    severity = Column(String)  # info, review, investigate
    inconsistency = Column(Text)
    possible_explanations_json = Column(Text)  # JSON array of >= 2 strings
    missing_evidence_json = Column(Text)        # JSON array of strings
    recommended_action = Column(Text)
    confidence = Column(Float)
    confidence_explanation = Column(Text)
    sources_json = Column(Text)                # JSON array of SourceRef objects
    created_at = Column(DateTime, default=datetime.utcnow)
