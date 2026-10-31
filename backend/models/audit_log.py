from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey
from datetime import datetime
from backend.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String, ForeignKey("cases.id"), index=True)
    event_type = Column(String)  # agent_run, verifier_check, adjuster_decision, evidence_uploaded
    agent_name = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    decision = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    user_id = Column(String, default="adjuster_1")
    user_role = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

