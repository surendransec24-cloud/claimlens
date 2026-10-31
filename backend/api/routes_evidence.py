import os
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.evidence import EvidenceItem
from backend.models.case import Case
from backend.models.user import User
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

@router.get("/{evidence_id}/file")
def get_evidence_file(
    evidence_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = db.query(EvidenceItem).filter(EvidenceItem.id == evidence_id).first()
    if not item or not os.path.exists(item.file_path):
        raise HTTPException(status_code=404, detail="Evidence file not found")

    # Verify case ownership / authorization
    if current_user.role == "adjuster":
        case = db.query(Case).filter(Case.id == item.case_id).first()
        if case and case.creator_id and case.creator_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to access evidence for another adjuster's case."
            )

    content_type, _ = mimetypes.guess_type(item.file_path)
    content_type = content_type or item.mime_type or "application/octet-stream"

    return FileResponse(
        path=item.file_path,
        media_type=content_type,
        filename=item.file_name
    )
