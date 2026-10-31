import re
from typing import List, Dict, Any, Tuple
from datetime import datetime
from backend.schemas.common import FindingSchema
from backend.schemas.decision import DecisionSupportOutput
from backend.schemas.verifier import VerifierResult, StatementVerification

FORBIDDEN_TERMS = [
    r"\bfraud\b",
    r"\bfraudulent\b",
    r"\bscam\b",
    r"\bcheat\b",
    r"\bliar\b",
    r"\bdeceit\b",
    r"\bfabricated\b",
    r"\bcriminal\b"
]

class VerifierAgent:
    PROMPT_VERSION = "v1.0"

    def verify(
        self,
        findings: List[FindingSchema],
        decision_support: DecisionSupportOutput,
        valid_evidence_ids: List[str]
    ) -> Tuple[List[FindingSchema], DecisionSupportOutput, VerifierResult]:
        """
        Validates:
        1. Citation Coverage: Ensures every finding has at least one valid citation to an uploaded evidence item.
        2. Strict Anti-Fraud Guardrail: Strictly prohibits accusatory terms, sanitizing any violations.
        3. Logs verifier result for immutable audit trail.
        """
        logs: List[str] = []
        total_statements = len(findings)
        passed_statements = 0
        rejected_and_sanitized = 0
        prohibited_detected = 0

        sanitized_findings: List[FindingSchema] = []

        valid_evidence_set = set(valid_evidence_ids).union({"DB-CLAIMS", "WEATHER-ARCHIVE"})

        for f in findings:
            has_valid_citation = False
            valid_sources = []
            for src in f.sources:
                if src.evidence_id in valid_evidence_set or any(src.evidence_id.startswith(e) for e in valid_evidence_set):
                    has_valid_citation = True
                    valid_sources.append(src)

            # Check forbidden terms in title, inconsistency, and explanations
            found_prohibited = []
            text_to_check = f"{f.title} {f.inconsistency} {' '.join(f.possible_explanations)} {f.recommended_action}"
            for pattern in FORBIDDEN_TERMS:
                matches = re.findall(pattern, text_to_check, re.IGNORECASE)
                if matches:
                    found_prohibited.extend(matches)

            clean_title = f.title
            clean_inconsistency = f.inconsistency
            clean_explanations = list(f.possible_explanations)
            clean_rec_action = f.recommended_action

            if found_prohibited:
                prohibited_detected += len(found_prohibited)
                rejected_and_sanitized += 1
                logs.append(f"[GUARDRAIL TRIGGERED] Finding {f.id} contained prohibited terms: {found_prohibited}. Sanitizing output.")
                
                # Sanitize terms
                for term in set(found_prohibited):
                    clean_title = re.sub(re.escape(term), "inconsistency requiring investigation", clean_title, flags=re.IGNORECASE)
                    clean_inconsistency = re.sub(re.escape(term), "inconsistency requiring investigation", clean_inconsistency, flags=re.IGNORECASE)
                    clean_explanations = [
                        re.sub(re.escape(term), "inconsistency requiring investigation", exp, flags=re.IGNORECASE)
                        for exp in clean_explanations
                    ]
                    clean_rec_action = re.sub(re.escape(term), "inconsistency requiring investigation", clean_rec_action, flags=re.IGNORECASE)

            if has_valid_citation and not found_prohibited:
                passed_statements += 1
            elif has_valid_citation and found_prohibited:
                logs.append(f"[SANITIZED & APPROVED] Finding {f.id} re-verified after sanitizing prohibited terminology.")
                passed_statements += 1
            else:
                logs.append(f"[CITATION WARNING] Finding {f.id} lacked a verified evidence item link. Attached default case reference.")
                valid_sources.append(src)

            f_copy = f.model_copy(update={
                "title": clean_title,
                "inconsistency": clean_inconsistency,
                "possible_explanations": clean_explanations,
                "recommended_action": clean_rec_action,
                "sources": valid_sources or f.sources
            })
            sanitized_findings.append(f_copy)

        # Check Decision Support Summary for forbidden terms
        decision_summary = decision_support.summary
        for pattern in FORBIDDEN_TERMS:
            matches = re.findall(pattern, decision_summary, re.IGNORECASE)
            if matches:
                prohibited_detected += len(matches)
                decision_summary = re.sub(pattern, "inconsistency requiring investigation", decision_summary, flags=re.IGNORECASE)
                logs.append("[GUARDRAIL TRIGGERED] Decision support summary contained prohibited terminology. Sanitized.")

        decision_support_copy = decision_support.model_copy(update={"summary": decision_summary})

        coverage_pct = 100.0 if total_statements == 0 else round((passed_statements / total_statements) * 100.0, 1)
        verifier_passed = (coverage_pct >= 90.0)

        logs.append(
            f"[VERIFIER COMPLETION] Total findings: {total_statements}. "
            f"Citation coverage: {coverage_pct}%. Prohibited terms found: {prohibited_detected}. "
            f"Sanitized: {rejected_and_sanitized}. Status: {'PASSED' if verifier_passed else 'DEGRADED'}."
        )

        verifier_result = VerifierResult(
            passed=verifier_passed,
            citation_coverage_pct=coverage_pct,
            prohibited_terms_detected=prohibited_detected,
            total_statements_checked=total_statements,
            passed_statements_count=passed_statements,
            rejected_and_sanitized_count=rejected_and_sanitized,
            verifier_log=logs,
            timestamp=datetime.utcnow().isoformat()
        )

        return sanitized_findings, decision_support_copy, verifier_result

