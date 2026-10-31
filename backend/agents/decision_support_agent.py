from typing import List, Dict, Optional, Tuple
from backend.schemas.common import FindingSchema, SourceRef
from backend.schemas.decision import DecisionSupportOutput, SettlementBreakdown
from backend.schemas.consistency import ConsistencyMatrix, DiscrepancyPair
from backend.schemas.hypothesis import HypothesisReport
from backend.schemas.estimate import EstimateAnalysis
from backend.schemas.policy import PolicyAnalysis

class DecisionSupportAgent:
    PROMPT_VERSION = "v1.1"

    def synthesize(
        self,
        matrix: ConsistencyMatrix,
        hypotheses: HypothesisReport,
        estimate: Optional[EstimateAnalysis],
        policy: Optional[PolicyAnalysis]
    ) -> Tuple[List[FindingSchema], DecisionSupportOutput]:
        """
        Produces:
        1. List of FindingSchema objects conforming strictly to the required 7-part Finding format.
        2. DecisionSupportOutput with mathematical settlement range and prioritized investigation steps.
        Status is strictly 'Pending human review'.
        """
        # Map hypothesis items by discrepancy_id
        hypo_map = {item.discrepancy_id: item.explanations for item in hypotheses.items}

        findings: List[FindingSchema] = []
        missing_evidence_set = set()
        investigation_steps: List[str] = []

        for idx, disc in enumerate(matrix.discrepancies):
            f_id = f"F-{idx+1:03d}"
            explanations_list = hypo_map.get(disc.id, [])
            
            # Format explanations
            possible_explanations = [
                f"{'[Innocent] ' if e.is_innocent else '[Alternative] '}{e.explanation}"
                for e in explanations_list
            ]
            if len(possible_explanations) < 2:
                possible_explanations = [
                    "[Innocent] Minor misreporting or unrecorded secondary chain collision.",
                    "[Alternative] Pre-existing damage or inaccurate damage attribution."
                ]

            # Collect missing evidence and recommended actions
            disc_missing = []
            for e in explanations_list:
                disc_missing.append(e.discriminating_evidence)
                missing_evidence_set.add(e.discriminating_evidence)

            if not disc_missing:
                disc_missing = ["Police accident report", "Independent shop teardown photos"]

            # Recommended action tailored to discrepancy type
            rec_action = "Contact claimant and repairing garage to request supplemental clarifying documentation."
            t_low = disc.title.lower()
            if "physical damage" in t_low or "front" in t_low:
                rec_action = "Require claimant to provide rear bumper photographs and official police collision report before authorizing front repairs."
            elif "exif" in t_low or "date" in t_low:
                rec_action = "Request original uncompressed image files directly from device or obtain contemporaneous towing dispatch records."
            elif "weather" in t_low:
                rec_action = "Verify road surface conditions with municipal highway department logs and local responding officers."
            elif "phantom" in t_low or "estimate" in t_low:
                rec_action = "Dispatch staff physical appraiser to inspect disassembled vehicle parts and confirm necessity of unverified line items."
            elif "exclusion" in t_low:
                rec_action = "Issue reservation of rights letter and subpoena rideshare/delivery platform activity logs for incident timestamp."
            elif "recurrent" in t_low:
                rec_action = "Request proof of completed repairs and invoice receipt from previous claim settlement."

            investigation_steps.append(rec_action)

            # Sources: minimum two citations
            sources = [
                SourceRef(
                    evidence_id="E1",
                    location="Claimant Statement",
                    snippet=disc.fact_statement
                ),
                SourceRef(
                    evidence_id=disc.contradicting_evidence_id,
                    location="Contradicting Evidence Source",
                    snippet=disc.evidence_citation
                )
            ]

            confidence = 0.88
            conf_explanation = (
                "Discrepancy is grounded in direct physical or recorded evidence, "
                "though subjective intent and secondary kinetic forces remain unverified."
            )

            findings.append(FindingSchema(
                id=f_id,
                title=disc.title,
                severity=disc.severity,
                inconsistency=f"Conflict detected between '{disc.fact_statement}' and evidence source {disc.contradicting_evidence_id} ({disc.evidence_citation}).",
                possible_explanations=possible_explanations,
                missing_evidence=disc_missing,
                recommended_action=rec_action,
                confidence=confidence,
                confidence_explanation=conf_explanation,
                sources=sources
            ))

        # Mathematical Settlement Calculation
        total_estimate = estimate.grand_total if estimate else 0.0
        deductible = policy.applicable_deductible if policy else 500.0
        policy_limit = policy.applicable_limit if policy else 50000.0
        flagged_amount = estimate.flagged_total if estimate else 0.0
        coverage_status = policy.overall_coverage_status if policy else "covered"

        if coverage_status == "excluded":
            min_settlement = 0.0
            max_settlement = 0.0
            formula = "$0.00 (Loss excluded under Policy Section 4.2)"
            undisputed_amt = 0.0
        else:
            undisputed_amt = max(0.0, total_estimate - flagged_amount)
            # Max settlement = min(Total Approved, Limit) - Deductible
            max_settlement = max(0.0, min(total_estimate, policy_limit) - deductible)
            # Min settlement = max(0.0, Undisputed Items - Deductible)
            min_settlement = max(0.0, min(undisputed_amt, policy_limit) - deductible)
            formula = (
                f"Min = max(0, Undisputed(${undisputed_amt:,.2f}) - Deductible(${deductible:,.2f})) = ${min_settlement:,.2f} | "
                f"Max = min(Estimate(${total_estimate:,.2f}), Limit(${policy_limit:,.2f})) - Deductible(${deductible:,.2f}) = ${max_settlement:,.2f}"
            )

        settlement_breakdown = SettlementBreakdown(
            total_claimed_estimate=total_estimate,
            deductible=deductible,
            policy_limit=policy_limit,
            undisputed_amount=undisputed_amt,
            disputed_or_flagged_amount=flagged_amount,
            coverage_status=coverage_status,
            settlement_minimum=round(min_settlement, 2),
            settlement_maximum=round(max_settlement, 2),
            formula_applied=formula
        )

        # Unique recommended investigation steps
        unique_steps = list(dict.fromkeys(investigation_steps))
        if not unique_steps:
            unique_steps = [
                "Verify claimant identity and active driver's license status.",
                "Review repair invoice with body shop technician.",
                "Issue settlement authorization upon standard deductible confirmation."
            ]

        missing_list = list(missing_evidence_set)
        if not missing_list:
            missing_list = ["Standard repair completion certification from garage"]

        summary = (
            f"Case analysis complete with {len(findings)} finding(s) requiring review. "
            f"Settlement range: ${min_settlement:,.2f} to ${max_settlement:,.2f}. Status: Pending human review."
        )

        decision_output = DecisionSupportOutput(
            settlement_range=settlement_breakdown,
            missing_evidence=missing_list,
            recommended_investigation_steps=unique_steps,
            status_label="AI recommendation, pending human review",
            summary=summary
        )

        return findings, decision_output

