from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
import uuid
from backend.database import Base

class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_number = Column(String, unique=True, index=True)
    policy_number = Column(String, index=True)
    claimant_name = Column(String)
    vehicle_vin = Column(String, nullable=True)
    vehicle_plate = Column(String, nullable=True)
    incident_date = Column(String, nullable=True)
    incident_location = Column(String, nullable=True)
    status = Column(String, default="Pending human review")  # Always pending human review by default
    adjuster_decision = Column(String, nullable=True)       # Approved / Request More Info / Escalated
    adjuster_reason = Column(Text, nullable=True)
    creator_id = Column(String, nullable=True, index=True)  # User who registered or initiated the case
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

