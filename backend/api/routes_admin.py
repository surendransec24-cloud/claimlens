from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.models.audit_log import AuditLog
from backend.api.deps import require_role, verify_csrf

router = APIRouter(prefix="/api/admin", tags=["admin"])

class UserStatusUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    unlock_account: Optional[bool] = None
    role: Optional[str] = None


@router.get("/users")
def list_all_users(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Admin-only: Retrieve list of all staff accounts."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "failed_attempts": u.failed_attempts,
            "is_locked": bool(u.locked_until and u.locked_until > u.created_at),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None
        }
        for u in users
    ]


@router.patch("/users/{user_id}/status", dependencies=[Depends(verify_csrf)])
def update_user_status(
    user_id: str,
    req: UserStatusUpdateRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Admin-only: Deactivate/activate an account or unlock a locked user."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.id == current_user.id and req.is_active is False:
        raise HTTPException(status_code=400, detail="Admins cannot deactivate their own account.")

    if req.is_active is not None:
        target_user.is_active = req.is_active

    if req.unlock_account:
        target_user.locked_until = None
        target_user.failed_attempts = 0

    if req.role and req.role in ["adjuster", "supervisor", "admin"]:
        target_user.role = req.role

    db.commit()

    # Log to audit log
    log = AuditLog(
        event_type="user_status_updated",
        user_id=current_user.id,
        user_role=current_user.role,
        input_summary=f"Admin updated user {target_user.email}",
        output_summary=f"Active: {target_user.is_active}, Role: {target_user.role}"
    )
    db.add(log)
    db.commit()

    return {
        "status": "success",
        "user": {
            "id": target_user.id,
            "email": target_user.email,
            "is_active": target_user.is_active,
            "role": target_user.role
        }
    }


@router.get("/audit")
def view_system_audit_log(
    limit: int = 50,
    event_type: Optional[str] = None,
    current_user: User = Depends(require_role(["admin", "supervisor"])),
    db: Session = Depends(get_db)
):
    """Admin and Supervisor: View immutable system-wide audit entries."""
    query = db.query(AuditLog)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    return [
        {
            "id": a.id,
            "case_id": a.case_id,
            "event_type": a.event_type,
            "agent_name": a.agent_name,
            "prompt_version": a.prompt_version,
            "model_name": a.model_name,
            "input_summary": a.input_summary,
            "output_summary": a.output_summary,
            "decision": a.decision,
            "reason": a.reason,
            "user_id": a.user_id,
            "user_role": a.user_role,
            "timestamp": a.timestamp.isoformat() if a.timestamp else None
        }
        for a in logs
    ]

