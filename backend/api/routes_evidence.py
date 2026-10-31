import os
import mimetypes
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.evidence import EvidenceItem

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

@router.get("/{evidence_id}/file")
def get_evidence_file(evidence_id: str, db: Session = Depends(get_db)):
    item = db.query(EvidenceItem).filter(EvidenceItem.id == evidence_id).first()
    if not item or not os.path.exists(item.file_path):
        raise HTTPException(status_code=404, detail="Evidence file not found")

    content_type, _ = mimetypes.guess_type(item.file_path)
    content_type = content_type or item.mime_type or "application/octet-stream"

    return FileResponse(
        path=item.file_path,
        media_type=content_type,
        filename=item.file_name
    )

