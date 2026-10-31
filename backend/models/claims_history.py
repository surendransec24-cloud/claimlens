from sqlalchemy import Column, String, Float, Text, Integer
from backend.database import Base

class ClaimsHistory(Base):
    __tablename__ = "claims_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    policyholder_id = Column(String, index=True)
    claimant_name = Column(String, index=True)
    vehicle_vin = Column(String, index=True)
    vehicle_plate = Column(String, index=True, nullable=True)
    incident_date = Column(String)
    claim_type = Column(String)  # Collision, Comprehensive, Third Party
    damage_zone = Column(String)  # front, rear, left, right, roof, glass
    payout_amount = Column(Float)
    garage_name = Column(String, index=True)
    status = Column(String)  # Settled, Denied, Withdrawn
    notes = Column(Text, nullable=True)

