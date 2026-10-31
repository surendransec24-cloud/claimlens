import os
import hashlib
import mimetypes
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models.evidence import EvidenceItem
from backend.services.exif_service import ExifService
from backend.services.pdf_service import PDFService
import json

class IntakeAgent:
    """
    IntakeAgent:
    - Classifies uploaded files into: photo, policy, estimate, narrative, police_report, other
    - Extracts text and metadata (EXIF for photos, text & tables for PDFs)
    - Generates stable IDs (E1, E2, E3...)
    - Persists EvidenceItem records
    """
    PROMPT_VERSION = "v1.0"

    @staticmethod
    def _compute_hash(file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def classify_file(file_name: str, mime_type: str, sample_text: str = "") -> str:
        fn_lower = file_name.lower()
        txt_lower = sample_text.lower()

        # Image extensions or mime types
        if mime_type.startswith("image/") or any(fn_lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".heic"]):
            return "photo"

        # Check by content keywords first, then filename
        if "police" in fn_lower or "police" in txt_lower or "traffic collision report" in txt_lower or "officer" in txt_lower:
            return "police_report"
        if "policy" in fn_lower or "declaration" in fn_lower or "coverage schedule" in txt_lower or "insuring agreement" in txt_lower:
            return "policy"
        if "estimate" in fn_lower or "repair" in fn_lower or "parts" in txt_lower and "labor" in txt_lower or "body shop" in txt_lower:
            return "estimate"
        if "statement" in fn_lower or "narrative" in fn_lower or "claimant" in txt_lower or "incident description" in txt_lower:
            return "narrative"

        # Check mime type
        if mime_type == "application/pdf":
            if "estimate" in txt_lower or "part number" in txt_lower or "labor rate" in txt_lower:
                return "estimate"
            if "exclusion" in txt_lower or "deductible" in txt_lower or "policyholder" in txt_lower:
                return "policy"
            return "policy"

        if mime_type.startswith("text/"):
            return "narrative"

        return "other"

    def process_files(
        self,
        db: Session,
        case_id: str,
        file_entries: List[Dict[str, str]], # [{"file_path": ..., "file_name": ...}]
        start_index: int = 1
    ) -> List[EvidenceItem]:
        evidence_items: List[EvidenceItem] = []
        current_idx = start_index

        for entry in file_entries:
            file_path = entry["file_path"]
            file_name = entry["file_name"]

            if not os.path.exists(file_path):
                continue

            file_hash = self._compute_hash(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            mime_type = mime_type or "application/octet-stream"

            extracted_text = ""
            metadata: Dict[str, Any] = {
                "file_size_bytes": os.path.getsize(file_path),
                "file_hash": file_hash
            }

            # Extract based on file type
            if mime_type.startswith("image/"):
                exif_data = ExifService.extract_metadata(file_path)
                metadata["exif"] = exif_data
                extracted_text = f"Photo file: {file_name}. EXIF Date: {exif_data.get('timestamp')}. GPS: {exif_data.get('gps')}"
            elif mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
                pdf_data = PDFService.extract_text_and_tables(file_path)
                extracted_text = pdf_data.get("full_text", "")
                metadata["pdf"] = {
                    "page_count": pdf_data.get("page_count", 0),
                    "table_count": len(pdf_data.get("tables", []))
                }
            elif mime_type.startswith("text/") or file_name.lower().endswith((".txt", ".md", ".json")):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        extracted_text = f.read()
                except Exception:
                    extracted_text = ""

            file_type = self.classify_file(file_name, mime_type, extracted_text[:1000])

            evidence_id = f"E{current_idx}"
            current_idx += 1

            item = EvidenceItem(
                id=evidence_id,
                case_id=case_id,
                file_name=file_name,
                file_path=file_path,
                file_type=file_type,
                mime_type=mime_type,
                file_hash=file_hash,
                extracted_text=extracted_text,
                metadata_json=json.dumps(metadata)
            )
            db.add(item)
            evidence_items.append(item)

        db.commit()
        return evidence_items
