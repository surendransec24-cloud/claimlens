from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from datetime import datetime
from backend.database import Base

class PipelineState(Base):
    __tablename__ = "pipeline_states"

    case_id = Column(String, ForeignKey("cases.id"), primary_key=True)
    status = Column(String, default="idle")  # idle, running, completed, degraded
    agent_statuses_json = Column(Text, default="{}")  # status per agent
    matrix_json = Column(Text, nullable=True)
    reconstruction_json = Column(Text, nullable=True)
    policy_evaluation_json = Column(Text, nullable=True)
    decision_json = Column(Text, nullable=True)
    verifier_json = Column(Text, nullable=True)
    diff_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

