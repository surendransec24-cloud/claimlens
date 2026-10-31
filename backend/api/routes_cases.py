import os
import json
import uuid
import asyncio
from typing import List, Optional, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db, SessionLocal
from backend.models.case import Case
from backend.models.evidence import EvidenceItem
from backend.models.finding import Finding
from backend.models.audit_log import AuditLog
from backend.models.pipeline_state import PipelineState
from backend.models.claims_history import ClaimsHistory
from backend.models.user import User
from backend.agents.intake_agent import IntakeAgent
from backend.orchestration.pipeline import pipeline_runner
from backend.config import settings
from backend.api import sse_bus
from backend.api.deps import get_current_user, verify_csrf

router = APIRouter(prefix="/api/cases", tags=["cases"])

class CaseCreateRequest(BaseModel):
    claim_number: Optional[str] = None
    policy_number: str
    claimant_name: str
    vehicle_vin: Optional[str] = None
    vehicle_plate: Optional[str] = None
    incident_date: Optional[str] = "2026-05-10"
    incident_location: Optional[str] = "Main St & 4th Ave, NY"

class AdjusterDecisionRequest(BaseModel):
    decision: str  # Approved, Request More Info, Escalated
    reason: str
    adjuster_id: Optional[str] = None


def _check_case_access(case: Case, user: User):
    """
    Adjuster sees and interacts only with cases they created (or legacy unassigned cases).
    Supervisors and admins have full access across all cases.
    """
    if user.role in ["supervisor", "admin"]:
        return
    if case.creator_id and case.creator_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You do not have permission to access cases assigned to another adjuster."
        )


@router.post("", dependencies=[Depends(verify_csrf)])
def create_case(
    req: CaseCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    c_num = req.claim_number or f"CLM-{uuid.uuid4().hex[:6].upper()}"
    new_case = Case(
        id=str(uuid.uuid4()),
        creator_id=current_user.id,
        claim_number=c_num,
        policy_number=req.policy_number,
        claimant_name=req.claimant_name,
        vehicle_vin=req.vehicle_vin or f"1HGCR2F8{uuid.uuid4().hex[:9].upper()}",
        vehicle_plate=req.vehicle_plate or "7XYZ89",
        incident_date=req.incident_date,
        incident_location=req.incident_location,
        status="Pending human review"
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Log case creation
    log = AuditLog(
        case_id=new_case.id,
        event_type="case_created",
        user_id=current_user.id,
        user_role=current_user.role,
        input_summary=f"Case created: {c_num} for claimant {req.claimant_name}",
        output_summary=f"Case ID {new_case.id} assigned to creator {current_user.email}"
    )
    db.add(log)
    db.commit()

    return {
        "id": new_case.id,
        "claim_number": new_case.claim_number,
        "policy_number": new_case.policy_number,
        "claimant_name": new_case.claimant_name,
        "vehicle_vin": new_case.vehicle_vin,
        "vehicle_plate": new_case.vehicle_plate,
        "incident_date": new_case.incident_date,
        "incident_location": new_case.incident_location,
        "status": new_case.status,
        "creator_id": new_case.creator_id,
        "created_at": new_case.created_at.isoformat() if new_case.created_at else None
    }


@router.get("")
def list_cases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Adjusters only see their own cases or legacy unassigned cases
    if current_user.role == "adjuster":
        cases = db.query(Case).filter(
            (Case.creator_id == current_user.id) | (Case.creator_id == None)
        ).order_by(Case.created_at.desc()).all()
    else:
        cases = db.query(Case).order_by(Case.created_at.desc()).all()

    results = []
    for c in cases:
        ev_count = db.query(EvidenceItem).filter(EvidenceItem.case_id == c.id).count()
        findings_count = db.query(Finding).filter(Finding.case_id == c.id).count()
        results.append({
            "id": c.id,
            "claim_number": c.claim_number,
            "policy_number": c.policy_number,
            "claimant_name": c.claimant_name,
            "incident_date": c.incident_date,
            "incident_location": c.incident_location,
            "status": c.status,
            "adjuster_decision": c.adjuster_decision,
            "creator_id": c.creator_id,
            "evidence_count": ev_count,
            "findings_count": findings_count,
            "created_at": c.created_at.isoformat() if c.created_at else None
        })
    return results


@router.get("/{case_id}")
def get_case_detail(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    evidence_items = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all()
    findings = db.query(Finding).filter(Finding.case_id == case_id).all()
    p_state = db.query(PipelineState).filter(PipelineState.case_id == case_id).first()
    audit_logs = db.query(AuditLog).filter(AuditLog.case_id == case_id).order_by(AuditLog.timestamp.desc()).all()

    evidence_out = []
    for e in evidence_items:
        evidence_out.append({
            "id": e.id,
            "file_name": e.file_name,
            "file_type": e.file_type,
            "mime_type": e.mime_type,
            "extracted_text": e.extracted_text,
            "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
            "analysis": json.loads(e.analysis_json) if e.analysis_json else None,
            "file_url": f"/api/evidence/{e.id}/file"
        })

    findings_out = []
    for f in findings:
        findings_out.append({
            "id": f.id,
            "title": f.title,
            "severity": f.severity,
            "inconsistency": f.inconsistency,
            "possible_explanations": json.loads(f.possible_explanations_json) if f.possible_explanations_json else [],
            "missing_evidence": json.loads(f.missing_evidence_json) if f.missing_evidence_json else [],
            "recommended_action": f.recommended_action,
            "confidence": f.confidence,
            "confidence_explanation": f.confidence_explanation,
            "sources": json.loads(f.sources_json) if f.sources_json else []
        })

    audit_out = []
    for a in audit_logs:
        audit_out.append({
            "id": a.id,
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
        })

    pipeline_out = None
    if p_state:
        pipeline_out = {
            "status": p_state.status,
            "agent_statuses": json.loads(p_state.agent_statuses_json) if p_state.agent_statuses_json else {},
            "matrix": json.loads(p_state.matrix_json) if p_state.matrix_json else None,
            "reconstruction": json.loads(p_state.reconstruction_json) if p_state.reconstruction_json else None,
            "policy_evaluation": json.loads(p_state.policy_evaluation_json) if p_state.policy_evaluation_json else None,
            "decision": json.loads(p_state.decision_json) if p_state.decision_json else None,
            "verifier": json.loads(p_state.verifier_json) if p_state.verifier_json else None,
            "diff": json.loads(p_state.diff_json) if p_state.diff_json else None,
            "updated_at": p_state.updated_at.isoformat() if p_state.updated_at else None
        }

    return {
        "case": {
            "id": case.id,
            "claim_number": case.claim_number,
            "policy_number": case.policy_number,
            "claimant_name": case.claimant_name,
            "vehicle_vin": case.vehicle_vin,
            "vehicle_plate": case.vehicle_plate,
            "incident_date": case.incident_date,
            "incident_location": case.incident_location,
            "status": case.status,
            "adjuster_decision": case.adjuster_decision,
            "adjuster_reason": case.adjuster_reason,
            "creator_id": case.creator_id,
            "created_at": case.created_at.isoformat() if case.created_at else None
        },
        "evidence": evidence_out,
        "findings": findings_out,
        "pipeline_state": pipeline_out,
        "audit_logs": audit_out
    }


@router.post("/{case_id}/upload", dependencies=[Depends(verify_csrf)])
async def upload_evidence(
    case_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    case_upload_dir = os.path.join(settings.UPLOAD_DIR, case_id)
    os.makedirs(case_upload_dir, exist_ok=True)

    file_entries = []
    for f in files:
        safe_filename = os.path.basename(f.filename or "uploaded_file")
        dest_path = os.path.join(case_upload_dir, safe_filename)
        contents = await f.read()
        with open(dest_path, "wb") as out_f:
            out_f.write(contents)
        file_entries.append({"file_path": dest_path, "file_name": safe_filename})

    existing_count = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).count()
    intake = IntakeAgent()
    created_items = intake.process_files(db, case_id, file_entries, start_index=existing_count + 1)

    for item in created_items:
        log = AuditLog(
            case_id=case_id,
            event_type="evidence_uploaded",
            agent_name="IntakeAgent",
            input_summary=f"Uploaded file: {item.file_name} ({item.mime_type})",
            output_summary=f"Assigned ID: {item.id}, Classified as: {item.file_type}",
            user_id=current_user.id,
            user_role=current_user.role
        )
        db.add(log)
    db.commit()

    return {
        "status": "success",
        "uploaded_count": len(created_items),
        "items": [{"id": item.id, "file_name": item.file_name, "file_type": item.file_type} for item in created_items]
    }


@router.post("/{case_id}/upload_preset/{bundle_id}", dependencies=[Depends(verify_csrf)])
async def upload_bundle_preset(
    case_id: str,
    bundle_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    import shutil
    bundles_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "bundles"))
    matching_dirs = [d for d in os.listdir(bundles_root) if d.startswith(f"bundle_{bundle_id}_") or d == f"bundle_{bundle_id}"]
    if not matching_dirs:
        raise HTTPException(status_code=404, detail=f"Bundle preset {bundle_id} not found")

    b_dir = os.path.join(bundles_root, matching_dirs[0])
    case_upload_dir = os.path.join(settings.UPLOAD_DIR, case_id)
    os.makedirs(case_upload_dir, exist_ok=True)

    file_entries = []
    for fn in os.listdir(b_dir):
        if fn != "expected.json":
            src = os.path.join(b_dir, fn)
            dst = os.path.join(case_upload_dir, fn)
            shutil.copy2(src, dst)
            file_entries.append({"file_path": dst, "file_name": fn})

    intake = IntakeAgent()
    created_items = intake.process_files(db, case_id, file_entries, start_index=1)
    
    # Audit log
    log = AuditLog(
        case_id=case_id,
        event_type="bundle_preset_uploaded",
        agent_name="IntakeAgent",
        input_summary=f"Uploaded bundle {bundle_id} ({len(created_items)} files)",
        output_summary=f"Processed items for pipeline run",
        user_id=current_user.id,
        user_role=current_user.role
    )
    db.add(log)
    db.commit()

    # Run pipeline
    state = await pipeline_runner.run_pipeline(case_id=case_id, db=db)
    return {
        "status": "success",
        "bundle_id": bundle_id,
        "evidence_count": len(created_items),
        "findings_count": len(state.findings)
    }


@router.post("/{case_id}/run", dependencies=[Depends(verify_csrf)])
async def run_case_pipeline(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    try:
        case_state = await pipeline_runner.run_pipeline(case_id=case_id, db=db)
        return {
            "status": "success",
            "findings_count": len(case_state.findings),
            "discrepancy_count": case_state.consistency_matrix.discrepancy_count if case_state.consistency_matrix else 0,
            "settlement_range": case_state.decision_support.settlement_range.model_dump() if case_state.decision_support else None,
            "verifier_passed": case_state.verifier_result.passed if case_state.verifier_result else True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/incremental", dependencies=[Depends(verify_csrf)])
async def run_incremental(
    case_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    case_upload_dir = os.path.join(settings.UPLOAD_DIR, case_id)
    os.makedirs(case_upload_dir, exist_ok=True)

    file_entries = []
    for f in files:
        safe_filename = os.path.basename(f.filename or "supplemental_file")
        dest_path = os.path.join(case_upload_dir, safe_filename)
        contents = await f.read()
        with open(dest_path, "wb") as out_f:
            out_f.write(contents)
        file_entries.append({"file_path": dest_path, "file_name": safe_filename})

    existing_count = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).count()
    intake = IntakeAgent()
    created_items = intake.process_files(db, case_id, file_entries, start_index=existing_count + 1)
    new_ids = [item.id for item in created_items]

    # Audit log
    log = AuditLog(
        case_id=case_id,
        event_type="incremental_evidence_uploaded",
        agent_name="IntakeAgent",
        input_summary=f"Supplemental upload ({len(new_ids)} files)",
        output_summary=f"Evidence IDs: {', '.join(new_ids)}",
        user_id=current_user.id,
        user_role=current_user.role
    )
    db.add(log)
    db.commit()

    # Run incremental re-reasoning
    new_state = await pipeline_runner.run_incremental_re_reasoning(
        case_id=case_id,
        new_evidence_ids=new_ids,
        db=db
    )

    return {
        "status": "success",
        "new_evidence_ids": new_ids,
        "diff": new_state.findings_diff,
        "findings_count": len(new_state.findings)
    }


@router.post("/{case_id}/decision", dependencies=[Depends(verify_csrf)])
def submit_adjuster_decision(
    case_id: str,
    req: AdjusterDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role not in ["adjuster", "supervisor"]:
        raise HTTPException(status_code=403, detail="Forbidden: Only adjusters and supervisors can record decisions.")

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="A mandatory justification reason is required for adjuster decision.")

    case.adjuster_decision = req.decision
    case.adjuster_reason = req.reason
    case.status = f"Decision: {req.decision}"

    # Immutable Audit Log
    log = AuditLog(
        case_id=case_id,
        event_type="adjuster_decision",
        decision=req.decision,
        reason=req.reason,
        user_id=current_user.id,
        user_role=current_user.role,
        input_summary=f"Decision recorded: {req.decision}",
        output_summary=f"Mandatory justification: {req.reason}"
    )
    db.add(log)
    db.commit()

    return {
        "status": "success",
        "decision": req.decision,
        "reason": req.reason,
        "case_status": case.status
    }


@router.get("/{case_id}/stream")
async def stream_pipeline_status(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events endpoint. Clients connect here before calling /run;
    they receive real-time agent status updates as the pipeline progresses.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    async def event_generator() -> AsyncGenerator[str, None]:
        q = sse_bus.subscribe(case_id)
        try:
            yield "event: connected\ndata: {\"case_id\": \"" + case_id + "\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("agent") == "__done__":
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            sse_bus.unsubscribe(case_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/{case_id}/run_stream", dependencies=[Depends(verify_csrf)])
async def run_case_pipeline_stream(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Runs the pipeline and publishes SSE events for each agent.
    Connect to GET /{case_id}/stream first to receive events.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    _check_case_access(case, current_user)

    async def sse_progress(event: dict):
        await sse_bus.publish(case_id, event)

    try:
        case_state = await pipeline_runner.run_pipeline(
            case_id=case_id,
            db=db,
            progress_callback=sse_progress
        )
        await sse_bus.publish(case_id, {"agent": "__done__", "status": "completed"})
        return {
            "status": "success",
            "findings_count": len(case_state.findings),
            "discrepancy_count": case_state.consistency_matrix.discrepancy_count if case_state.consistency_matrix else 0,
            "settlement_range": case_state.decision_support.settlement_range.model_dump() if case_state.decision_support else None,
            "verifier_passed": case_state.verifier_result.passed if case_state.verifier_result else True
        }
    except Exception as e:
        await sse_bus.publish(case_id, {"agent": "__done__", "status": "failed", "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))
