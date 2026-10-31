from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.claims_history import ClaimsHistory
from backend.models.user import User
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/history", tags=["history"])

@router.get("")
def list_claims_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(ClaimsHistory).all()

def seed_default_claims_history(db: Session):
    if db.query(ClaimsHistory).count() == 0:
        samples = [
            ClaimsHistory(
                policyholder_id="Sarah Jenkins",
                claimant_name="Sarah Jenkins",
                vehicle_vin="1HGCR2F83HA001294",
                vehicle_plate="7ABC12",
                incident_date="2026-02-14",
                claim_type="Collision",
                damage_zone="right",
                payout_amount=4250.00,
                garage_name="Metro Precision Collision",
                status="Settled",
                notes="Right quarter panel crease and door respray after parking lot collision."
            ),
            ClaimsHistory(
                policyholder_id="Robert Chen",
                claimant_name="Robert Chen",
                vehicle_vin="4T1B11HK5JU109432",
                vehicle_plate="5KLM99",
                incident_date="2025-11-20",
                claim_type="Comprehensive",
                damage_zone="glass",
                payout_amount=650.00,
                garage_name="Apex Auto Glass",
                status="Settled",
                notes="Windshield rock chip replacement."
            )
        ]
        db.add_all(samples)
        db.commit()
