from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey
from datetime import datetime
from backend.database import Base

class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    db_id = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String, index=True)  # E1, E2, E3...
    case_id = Column(String, ForeignKey("cases.id"), index=True)
    file_name = Column(String)
    file_path = Column(String)
    file_type = Column(String)  # photo, policy, estimate, narrative, police_report, other
    mime_type = Column(String)
    file_hash = Column(String, nullable=True)
    extracted_text = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON string of EXIF, PDF metadata, page count, etc.
    analysis_json = Column(Text, nullable=True)  # JSON string of agent's analysis of this specific item
    created_at = Column(DateTime, default=datetime.utcnow)
