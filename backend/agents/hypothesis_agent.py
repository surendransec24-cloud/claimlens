from typing import List
from backend.schemas.hypothesis import (
    HypothesisReport,
    DiscrepancyHypotheses,
    AlternativeExplanation
)
from backend.schemas.consistency import ConsistencyMatrix, DiscrepancyPair
from backend.services.llm_service import llm_service

SYSTEM_PROMPT = """You are an objective claims forensic investigator.
For each reported inconsistency in a motor insurance claim, provide at least two alternative explanations:
1. An INNOCENT explanation: e.g., chain-reaction collision where vehicle was pushed into another, unsynchronized camera clock, typographical date error, secondary impact, or driver disorientation immediately following collision shock.
2. An ALTERNATIVE explanation: e.g., pre-existing damage from an earlier unfiled incident, inaccurate damage attribution, or unverified circumstance.

For each explanation, specify exactly what discriminating evidence would definitively confirm or rule it out.
CRITICAL GUARDRAIL: Never use words like 'fraud', 'fraudulent', or accuse the claimant. Frame everything as hypotheses requiring adjuster verification."""

class HypothesisAgent:
    PROMPT_VERSION = "v1.1"

    async def generate_hypotheses(
        self,
        matrix: ConsistencyMatrix
    ) -> HypothesisReport:
        items: List[DiscrepancyHypotheses] = []

        for disc in matrix.discrepancies:
            # Generate tailored hypotheses based on discrepancy title/type
            t_low = disc.title.lower()
            explanations: List[AlternativeExplanation] = []

            if "front" in t_low or "rear" in t_low or "physical damage" in t_low or "impact" in t_low:
                explanations = [
                    AlternativeExplanation(
                        explanation="Innocent Chain-Reaction Collision: Insured vehicle was hit from behind and subsequently propelled forward into a leading vehicle or barrier, producing primary front damage while rear bumper absorbed elastic impact without visible panel tears.",
                        is_innocent=True,
                        plausibility="moderate",
                        discriminating_evidence="Independent police collision report, traffic camera footage, or statement/photos from the leading vehicle driver."
                    ),
                    AlternativeExplanation(
                        explanation="Pre-Existing Frontal Damage: The front-end crushing pre-dated the reported rear-end incident and was conflated or submitted together during body shop repair appraisal.",
                        is_innocent=False,
                        plausibility="moderate",
                        discriminating_evidence="Prior vehicle service records, MOT/inspection history, or high-resolution close-ups of fracture surfaces examining pre-existing rust/oxidation."
                    )
                ]
            elif "exif" in t_low or "date" in t_low:
                explanations = [
                    AlternativeExplanation(
                        explanation="Camera Device Clock Desynchronization: The camera or smartphone utilized to capture the vehicle photographs had an incorrect internal calendar or unadjusted time zone setting.",
                        is_innocent=True,
                        plausibility="high",
                        discriminating_evidence="Smartphone raw file system timestamps, file creation metadata, or contemporaneous tow-truck dispatch and body shop check-in receipts."
                    ),
                    AlternativeExplanation(
                        explanation="Photographs Depict Prior Incident: The submitted photographs were taken months prior during an earlier event and mistakenly or intentionally reused for the current claim.",
                        is_innocent=False,
                        plausibility="moderate",
                        discriminating_evidence="Tow dispatch timestamp logs, verifiable witness statements, or recent dated photographs of the vehicle."
                    )
                ]
            elif "weather" in t_low:
                explanations = [
                    AlternativeExplanation(
                        explanation="Localized Micro-Climate / Road Surface Anomaly: A localized water leak, localized shaded frost patch, or spilled liquid created slippery conditions despite broader metropolitan meteorological stations recording clear skies.",
                        is_innocent=True,
                        plausibility="moderate",
                        discriminating_evidence="Department of Transportation municipal road condition logs, highway maintenance call logs, or responding officer field observations."
                    ),
                    AlternativeExplanation(
                        explanation="Inaccurate Narrative Recollection: The claimant erroneously described severe blizzard conditions to explain loss of control when road conditions were clear.",
                        is_innocent=False,
                        plausibility="moderate",
                        discriminating_evidence="Local weather radar sweeps at the exact 15-minute incident window and highway CCTV recordings."
                    )
                ]
            elif "phantom" in t_low or "estimate" in t_low:
                explanations = [
                    AlternativeExplanation(
                        explanation="Concealed Structural Damage Identified by Repair Technician: The repair facility identified underlying frame, mechanical, or suspension alignment displacement during disassembly that is not visible on surface exterior photographs.",
                        is_innocent=True,
                        plausibility="high",
                        discriminating_evidence="Supplement tear-down photos from the repair shop, frame-bench diagnostic printouts, and wheel alignment data."
                    ),
                    AlternativeExplanation(
                        explanation="Over-Scoping or Inadvertent Line-Item Inclusion: The body shop's estimating software bundled routine overhaul or unrelated maintenance line items not attributable to this specific collision.",
                        is_innocent=False,
                        plausibility="moderate",
                        discriminating_evidence="Independent physical inspection by an insurance staff appraiser (desk or field review)."
                    )
                ]
            elif "commercial" in t_low or "exclusion" in t_low:
                explanations = [
                    AlternativeExplanation(
                        explanation="Incidental Personal Travel with Commercial App Running: Claimant had a ride-hailing app running in the background without an active fare or passenger on board (personal commute).",
                        is_innocent=True,
                        plausibility="moderate",
                        discriminating_evidence="Rideshare platform trip-state logs confirming whether driver was in Period 0 (app off/personal), Period 1, or Period 2/3 (active passenger)."
                    ),
                    AlternativeExplanation(
                        explanation="Active Commercial Carriage Without Endorsement: Vehicle was actively carrying passengers or performing commercial delivery under standard personal personal auto coverage.",
                        is_innocent=False,
                        plausibility="moderate",
                        discriminating_evidence="Official rideshare platform loss-notice verification report."
                    )
                ]
            elif "recurrent" in t_low or "repeat" in t_low:
                explanations = [
                    AlternativeExplanation(
                        explanation="Coincidental Secondary Collision in Same Parking Location: The vehicle is parked in a high-risk street location where identical rear/quarter panel scrapes recur from neighboring vehicles.",
                        is_innocent=True,
                        plausibility="moderate",
                        discriminating_evidence="Invoices and repair completion certificates from the prior claim showing that prior damage was fully restored."
                    ),
                    AlternativeExplanation(
                        explanation="Unrepaired Prior Damage Claimed Again: Payout was disbursed on the previous claim but repairs were never executed, and the existing damage was resubmitted.",
                        is_innocent=False,
                        plausibility="moderate",
                        discriminating_evidence="Post-repair inspection photographs from the earlier claim settlement and proof of payment to the garage."
                    )
                ]
            else:
                explanations = [
                    AlternativeExplanation(
                        explanation="Reporting Discrepancy or Clerical Ambiguity: The inconsistency arises from miscommunication during statement intake or conflicting document versions.",
                        is_innocent=True,
                        plausibility="high",
                        discriminating_evidence="Adjuster recorded phone interview clarifying the disputed item."
                    ),
                    AlternativeExplanation(
                        explanation="Unsubstantiated Claim Element: The element cannot be verified against physical evidence or documentation.",
                        is_innocent=False,
                        plausibility="moderate",
                        discriminating_evidence="Independent third-party documentation."
                    )
                ]

            items.append(DiscrepancyHypotheses(
                discrepancy_id=disc.id,
                title=disc.title,
                explanations=explanations
            ))

        return HypothesisReport(items=items)

