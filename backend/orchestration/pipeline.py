import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.case import Case
from backend.models.evidence import EvidenceItem
from backend.models.finding import Finding
from backend.models.audit_log import AuditLog
from backend.models.pipeline_state import PipelineState
from backend.schemas.case_state import CaseState, AgentExecutionStatus
from backend.schemas.vision import PhotoAnalysis
from backend.schemas.common import FindingSchema

from backend.agents.intake_agent import IntakeAgent
from backend.agents.vision_agent import VisionAgent
from backend.agents.narrative_agent import NarrativeAgent
from backend.agents.policy_agent import PolicyAgent
from backend.agents.context_agent import ContextAgent
from backend.agents.estimate_agent import EstimateAgent
from backend.agents.consistency_engine import ConsistencyEngine
from backend.agents.reconstruction_agent import ReconstructionAgent
from backend.agents.hypothesis_agent import HypothesisAgent
from backend.agents.decision_support_agent import DecisionSupportAgent
from backend.agents.verifier_agent import VerifierAgent
from backend.config import settings

class ClaimPipeline:
    def __init__(self):
        self.intake_agent = IntakeAgent()
        self.vision_agent = VisionAgent()
        self.narrative_agent = NarrativeAgent()
        self.policy_agent = PolicyAgent()
        self.context_agent = ContextAgent()
        self.estimate_agent = EstimateAgent()
        self.consistency_engine = ConsistencyEngine()
        self.reconstruction_agent = ReconstructionAgent()
        self.hypothesis_agent = HypothesisAgent()
        self.decision_agent = DecisionSupportAgent()
        self.verifier_agent = VerifierAgent()

    async def _log_agent_run(
        self,
        db: Session,
        case_id: str,
        agent_name: str,
        prompt_version: str,
        input_summary: str,
        output_summary: str,
        event_type: str = "agent_run"
    ):
        log_entry = AuditLog(
            case_id=case_id,
            event_type=event_type,
            agent_name=agent_name,
            prompt_version=prompt_version,
            model_name=settings.GEMINI_MODEL,
            input_summary=input_summary[:2000],
            output_summary=output_summary[:2000],
            user_id="system_orchestrator"
        )
        db.add(log_entry)
        db.commit()

    async def run_pipeline(
        self,
        case_id: str,
        db: Session,
        progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ) -> CaseState:
        """
        Executes the full 11-agent pipeline:
        Phase 1: Parallel extraction agents (Vision, Narrative, Policy, Context, Estimate)
        Phase 2: Cross-evidence synthesis (Consistency, Reconstruction, Hypothesis, Decision, Verifier)
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        evidence_items = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all()
        if not evidence_items:
            raise ValueError(f"No evidence items found for case {case_id}")

        evidence_ids = [e.id for e in evidence_items]
        evidence_meta_map = {
            e.id: {
                "type": e.file_type,
                "file_name": e.file_name,
                "file_path": e.file_path,
                "extracted_text": e.extracted_text or ""
            }
            for e in evidence_items
        }

        agent_statuses: Dict[str, AgentExecutionStatus] = {
            "IntakeAgent": AgentExecutionStatus(agent_name="IntakeAgent", status="completed", timestamp=datetime.utcnow().isoformat()),
            "VisionAgent": AgentExecutionStatus(agent_name="VisionAgent", status="pending"),
            "NarrativeAgent": AgentExecutionStatus(agent_name="NarrativeAgent", status="pending"),
            "PolicyAgent": AgentExecutionStatus(agent_name="PolicyAgent", status="pending"),
            "ContextAgent": AgentExecutionStatus(agent_name="ContextAgent", status="pending"),
            "EstimateAgent": AgentExecutionStatus(agent_name="EstimateAgent", status="pending"),
            "ConsistencyEngine": AgentExecutionStatus(agent_name="ConsistencyEngine", status="pending"),
            "ReconstructionAgent": AgentExecutionStatus(agent_name="ReconstructionAgent", status="pending"),
            "HypothesisAgent": AgentExecutionStatus(agent_name="HypothesisAgent", status="pending"),
            "DecisionSupportAgent": AgentExecutionStatus(agent_name="DecisionSupportAgent", status="pending"),
            "VerifierAgent": AgentExecutionStatus(agent_name="VerifierAgent", status="pending"),
        }

        async def broadcast_status(agent_name: str, status: str, duration_ms: Optional[float] = None, error: Optional[str] = None):
            agent_statuses[agent_name] = AgentExecutionStatus(
                agent_name=agent_name,
                status=status,
                duration_ms=duration_ms,
                error_message=error,
                timestamp=datetime.utcnow().isoformat()
            )
            if progress_callback:
                try:
                    await progress_callback({
                        "event": "agent_status",
                        "agent": agent_name,
                        "status": status,
                        "duration_ms": duration_ms,
                        "error": error
                    })
                except Exception:
                    pass

        # ----------------------------------------------------
        # PHASE 1: INDEPENDENT PARALLEL EXTRACTION
        # ----------------------------------------------------
        # 1. Vision Tasks
        photos = [e for e in evidence_items if e.file_type == "photo"]
        photo_analyses: Dict[str, PhotoAnalysis] = {}

        async def run_vision():
            t0 = time.time()
            await broadcast_status("VisionAgent", "running")
            try:
                for p in photos:
                    res = await self.vision_agent.analyze_photo(
                        evidence_id=p.id,
                        file_path=p.file_path,
                        file_name=p.file_name,
                        stated_date=case.incident_date,
                        stated_location=case.incident_location
                    )
                    photo_analyses[p.id] = res
                    # Save analysis back to evidence item
                    p.analysis_json = res.model_dump_json()
                db.commit()
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("VisionAgent", "completed", duration_ms=duration)
                await self._log_agent_run(
                    db, case_id, "VisionAgent", self.vision_agent.PROMPT_VERSION,
                    f"Analyzed {len(photos)} photo(s)",
                    f"Identified zones: {[z.zone for a in photo_analyses.values() for z in a.damaged_zones]}"
                )
            except Exception as e:
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("VisionAgent", "degraded", duration_ms=duration, error=str(e))

        # 2. Narrative Task
        narrative_doc = next((e for e in evidence_items if e.file_type in ["narrative", "police_report"]), None)
        narrative_res = None

        async def run_narrative():
            nonlocal narrative_res
            t0 = time.time()
            await broadcast_status("NarrativeAgent", "running")
            try:
                text_content = narrative_doc.extracted_text if narrative_doc else ""
                narrative_res = await self.narrative_agent.analyze_narrative(
                    evidence_id=narrative_doc.id if narrative_doc else "E1",
                    text=text_content
                )
                if narrative_doc:
                    narrative_doc.analysis_json = narrative_res.model_dump_json()
                    db.commit()
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("NarrativeAgent", "completed", duration_ms=duration)
                await self._log_agent_run(
                    db, case_id, "NarrativeAgent", self.narrative_agent.PROMPT_VERSION,
                    f"Parsed narrative: {len(text_content)} chars",
                    f"Extracted {len(narrative_res.structured_facts)} discrete facts with sentence citations."
                )
            except Exception as e:
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("NarrativeAgent", "degraded", duration_ms=duration, error=str(e))

        # 3. Policy Task
        policy_doc = next((e for e in evidence_items if e.file_type == "policy"), None)
        policy_res = None

        async def run_policy():
            nonlocal policy_res
            t0 = time.time()
            await broadcast_status("PolicyAgent", "running")
            try:
                text_content = policy_doc.extracted_text if policy_doc else ""
                policy_res = await self.policy_agent.analyze_policy(
                    evidence_id=policy_doc.id if policy_doc else "E2",
                    policy_text=text_content,
                    narrative=narrative_res
                )
                if policy_doc:
                    policy_doc.analysis_json = policy_res.model_dump_json()
                    db.commit()
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("PolicyAgent", "completed", duration_ms=duration)
                await self._log_agent_run(
                    db, case_id, "PolicyAgent", self.policy_agent.PROMPT_VERSION,
                    f"Policy text: {len(text_content)} chars",
                    f"Evaluations: {policy_res.overall_coverage_status.upper()}, deductible ${policy_res.applicable_deductible}"
                )
            except Exception as e:
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("PolicyAgent", "degraded", duration_ms=duration, error=str(e))

        # 4. Context Task (Weather & History)
        context_res = None

        async def run_context():
            nonlocal context_res
            t0 = time.time()
            await broadcast_status("ContextAgent", "running")
            try:
                inc_date = case.incident_date or "2026-05-10"
                context_res = await self.context_agent.gather_context(
                    db=db,
                    incident_date_str=inc_date,
                    location_str=case.incident_location,
                    policyholder_id=case.claimant_name,
                    vehicle_vin=case.vehicle_vin,
                    claimed_weather=narrative_res.weather_claimed if narrative_res else None
                )
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("ContextAgent", "completed", duration_ms=duration)
                await self._log_agent_run(
                    db, case_id, "ContextAgent", self.context_agent.PROMPT_VERSION,
                    f"Gathered context for date {inc_date}",
                    f"Weather: {context_res.weather.condition_description if context_res.weather else 'N/A'}, prior claims matches: {len(context_res.prior_claims)}"
                )
            except Exception as e:
                duration = round((time.time() - t0) * 1000, 1)
                await broadcast_status("ContextAgent", "degraded", duration_ms=duration, error=str(e))

        # Run Phase 1 parallel extraction
        await asyncio.gather(
            run_vision(),
            run_narrative(),
            run_policy(),
            run_context()
        )

        # 5. Estimate Task (depends on photo_analyses from Vision)
        estimate_doc = next((e for e in evidence_items if e.file_type == "estimate"), None)
        estimate_res = None
        t0_est = time.time()
        await broadcast_status("EstimateAgent", "running")
        try:
            est_text = estimate_doc.extracted_text if estimate_doc else ""
            estimate_res = self.estimate_agent.parse_and_cross_check(
                estimate_text=est_text,
                photo_analyses=photo_analyses
            )
            if estimate_doc:
                estimate_doc.analysis_json = estimate_res.model_dump_json()
                db.commit()
            dur_est = round((time.time() - t0_est) * 1000, 1)
            await broadcast_status("EstimateAgent", "completed", duration_ms=dur_est)
            await self._log_agent_run(
                db, case_id, "EstimateAgent", self.estimate_agent.PROMPT_VERSION,
                f"Estimate text: {len(est_text)} chars, cross-checked against {len(photo_analyses)} photos",
                f"Total: ${estimate_res.grand_total:.2f}, phantom items: {len(estimate_res.phantom_line_items)}"
            )
        except Exception as e:
            dur_est = round((time.time() - t0_est) * 1000, 1)
            await broadcast_status("EstimateAgent", "degraded", duration_ms=dur_est, error=str(e))

        # ----------------------------------------------------
        # PHASE 2: CROSS-EVIDENCE SYNTHESIS
        # ----------------------------------------------------
        # 6. ConsistencyEngine (Deterministic Python)
        t0_c = time.time()
        await broadcast_status("ConsistencyEngine", "running")
        matrix_res = self.consistency_engine.evaluate_matrix(
            narrative=narrative_res,
            photos=photo_analyses,
            policy=policy_res,
            context=context_res,
            estimate=estimate_res,
            evidence_metadata=evidence_meta_map
        )
        dur_c = round((time.time() - t0_c) * 1000, 1)
        await broadcast_status("ConsistencyEngine", "completed", duration_ms=dur_c)
        await self._log_agent_run(
            db, case_id, "ConsistencyEngine", self.consistency_engine.PROMPT_VERSION,
            f"Evaluated {len(matrix_res.facts)} facts across {len(evidence_ids)} evidence items ({len(matrix_res.cells)} cells)",
            f"Supports: {matrix_res.support_count}, Contradicts: {matrix_res.discrepancy_count}, Silent: {matrix_res.silent_count}"
        )

        # 7. ReconstructionAgent
        t0_r = time.time()
        await broadcast_status("ReconstructionAgent", "running")
        reconstruction_res = self.reconstruction_agent.reconstruct(
            narrative=narrative_res,
            photos=photo_analyses
        )
        dur_r = round((time.time() - t0_r) * 1000, 1)
        await broadcast_status("ReconstructionAgent", "completed", duration_ms=dur_r)
        await self._log_agent_run(
            db, case_id, "ReconstructionAgent", self.reconstruction_agent.PROMPT_VERSION,
            f"Synthesized {len(reconstruction_res.timeline)} timeline events",
            f"Compatibility score: {reconstruction_res.physical_damage_compatibility_score:.2f}, consistent: {reconstruction_res.is_damage_consistent_with_narrative}"
        )

        # 8. HypothesisAgent
        t0_h = time.time()
        await broadcast_status("HypothesisAgent", "running")
        hypothesis_res = await self.hypothesis_agent.generate_hypotheses(matrix=matrix_res)
        dur_h = round((time.time() - t0_h) * 1000, 1)
        await broadcast_status("HypothesisAgent", "completed", duration_ms=dur_h)
        await self._log_agent_run(
            db, case_id, "HypothesisAgent", self.hypothesis_agent.PROMPT_VERSION,
            f"Processed {len(matrix_res.discrepancies)} discrepancies",
            f"Generated {len(hypothesis_res.items)} hypothesis sets with innocent & alternative explanations."
        )

        # 9. DecisionSupportAgent
        t0_d = time.time()
        await broadcast_status("DecisionSupportAgent", "running")
        raw_findings, decision_res = self.decision_agent.synthesize(
            matrix=matrix_res,
            hypotheses=hypothesis_res,
            estimate=estimate_res,
            policy=policy_res
        )
        dur_d = round((time.time() - t0_d) * 1000, 1)
        await broadcast_status("DecisionSupportAgent", "completed", duration_ms=dur_d)
        await self._log_agent_run(
            db, case_id, "DecisionSupportAgent", self.decision_agent.PROMPT_VERSION,
            f"Synthesized decision for {len(raw_findings)} findings",
            f"Settlement range: ${decision_res.settlement_range.settlement_minimum:.2f} - ${decision_res.settlement_range.settlement_maximum:.2f}. Status: {decision_res.status_label}"
        )

        # 10. VerifierAgent
        t0_v = time.time()
        await broadcast_status("VerifierAgent", "running")
        verified_findings, verified_decision, verifier_res = self.verifier_agent.verify(
            findings=raw_findings,
            decision_support=decision_res,
            valid_evidence_ids=evidence_ids
        )
        dur_v = round((time.time() - t0_v) * 1000, 1)
        await broadcast_status("VerifierAgent", "completed", duration_ms=dur_v)
        await self._log_agent_run(
            db, case_id, "VerifierAgent", self.verifier_agent.PROMPT_VERSION,
            f"Checked {verifier_res.total_statements_checked} statements across evidence items {evidence_ids}",
            f"Passed: {verifier_res.passed}, Citation coverage: {verifier_res.citation_coverage_pct}%, Prohibited terms detected: {verifier_res.prohibited_terms_detected}",
            event_type="verifier_check"
        )

        # ----------------------------------------------------
        # PERSIST RESULTS TO SQLITE
        # ----------------------------------------------------
        # Clear existing findings for this case
        db.query(Finding).filter(Finding.case_id == case_id).delete(synchronize_session="fetch")
        db.flush()
        for f in verified_findings:
            db_finding = Finding(
                id=f.id,
                case_id=case_id,
                title=f.title,
                severity=f.severity,
                inconsistency=f.inconsistency,
                possible_explanations_json=json.dumps(f.possible_explanations),
                missing_evidence_json=json.dumps(f.missing_evidence),
                recommended_action=f.recommended_action,
                confidence=f.confidence,
                confidence_explanation=f.confidence_explanation,
                sources_json=json.dumps([s.model_dump() for s in f.sources])
            )
            db.add(db_finding)

        # Update PipelineState
        p_state = db.query(PipelineState).filter(PipelineState.case_id == case_id).first()
        if not p_state:
            p_state = PipelineState(case_id=case_id)
            db.add(p_state)

        p_state.status = "completed"
        p_state.agent_statuses_json = json.dumps({k: v.model_dump() for k, v in agent_statuses.items()})
        p_state.matrix_json = matrix_res.model_dump_json()
        p_state.reconstruction_json = reconstruction_res.model_dump_json()
        p_state.policy_evaluation_json = policy_res.model_dump_json() if policy_res else None
        p_state.decision_json = verified_decision.model_dump_json()
        p_state.verifier_json = verifier_res.model_dump_json()

        db.commit()

        return CaseState(
            case_id=case_id,
            claim_number=case.claim_number,
            evidence_ids=evidence_ids,
            agent_statuses=agent_statuses,
            photo_analyses=photo_analyses,
            narrative_analysis=narrative_res,
            policy_analysis=policy_res,
            context_analysis=context_res,
            estimate_analysis=estimate_res,
            consistency_matrix=matrix_res,
            reconstruction_analysis=reconstruction_res,
            hypothesis_report=hypothesis_res,
            decision_support=verified_decision,
            findings=verified_findings,
            verifier_result=verifier_res,
            overall_status="completed"
        )

    async def run_incremental_re_reasoning(
        self,
        case_id: str,
        new_evidence_ids: List[str],
        db: Session,
        progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ) -> CaseState:
        """
        Executes incremental re-reasoning when additional evidence is uploaded:
        1. Captures previous findings and settlement range.
        2. Re-runs affected independent agents and all synthesis agents.
        3. Computes a rich structured diff view.
        """
        # Load previous findings
        old_findings = db.query(Finding).filter(Finding.case_id == case_id).all()
        prev_findings_schemas: List[FindingSchema] = []
        for of in old_findings:
            prev_findings_schemas.append(FindingSchema(
                id=of.id,
                title=of.title,
                severity=of.severity,
                inconsistency=of.inconsistency,
                possible_explanations=json.loads(of.possible_explanations_json),
                missing_evidence=json.loads(of.missing_evidence_json),
                recommended_action=of.recommended_action,
                confidence=of.confidence,
                confidence_explanation=of.confidence_explanation,
                sources=json.loads(of.sources_json)
            ))

        old_pipeline_state = db.query(PipelineState).filter(PipelineState.case_id == case_id).first()
        prev_decision = json.loads(old_pipeline_state.decision_json) if (old_pipeline_state and old_pipeline_state.decision_json) else None

        # Re-run full pipeline with newly incorporated evidence
        new_state = await self.run_pipeline(case_id=case_id, db=db, progress_callback=progress_callback)

        # Compute structured diff
        prev_finding_titles = {f.title: f for f in prev_findings_schemas}
        new_finding_titles = {f.title: f for f in new_state.findings}

        added_findings = [f.model_dump() for t, f in new_finding_titles.items() if t not in prev_finding_titles]
        resolved_findings = [f.model_dump() for t, f in prev_finding_titles.items() if t not in new_finding_titles]
        modified_findings = []

        for t, f in new_finding_titles.items():
            if t in prev_finding_titles:
                prev_f = prev_finding_titles[t]
                if prev_f.severity != f.severity or abs(prev_f.confidence - f.confidence) > 0.05:
                    modified_findings.append({
                        "title": t,
                        "old_severity": prev_f.severity,
                        "new_severity": f.severity,
                        "old_confidence": prev_f.confidence,
                        "new_confidence": f.confidence
                    })

        # Settlement change
        old_max = prev_decision["settlement_range"]["settlement_maximum"] if prev_decision else 0.0
        new_max = new_state.decision_support.settlement_range.settlement_maximum if new_state.decision_support else 0.0
        settlement_diff = round(new_max - old_max, 2)

        diff_summary = {
            "new_evidence_added": new_evidence_ids,
            "added_findings_count": len(added_findings),
            "resolved_findings_count": len(resolved_findings),
            "modified_findings_count": len(modified_findings),
            "added_findings": added_findings,
            "resolved_findings": resolved_findings,
            "modified_findings": modified_findings,
            "settlement_difference": settlement_diff,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Save diff in DB
        if old_pipeline_state:
            old_pipeline_state.diff_json = json.dumps(diff_summary)
            db.commit()

        new_state.previous_findings = prev_findings_schemas
        new_state.findings_diff = diff_summary

        await self._log_agent_run(
            db, case_id, "IncrementalReReasoning", "v1.0",
            f"Re-reasoned case with {len(new_evidence_ids)} new item(s): {new_evidence_ids}",
            f"Diff: +{len(added_findings)} findings, -{len(resolved_findings)} resolved, settlement change: ${settlement_diff:.2f}",
            event_type="incremental_re_reasoning"
        )

        return new_state

pipeline_runner = ClaimPipeline()

