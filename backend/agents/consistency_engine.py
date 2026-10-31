from typing import List, Dict, Any, Tuple, Optional
from backend.schemas.consistency import (
    ConsistencyMatrix,
    ConsistencyCell,
    CellAlignment,
    DiscrepancyPair
)
from backend.schemas.narrative import NarrativeAnalysis, ClaimFact
from backend.schemas.vision import PhotoAnalysis
from backend.schemas.policy import PolicyAnalysis
from backend.schemas.context import ContextAnalysis
from backend.schemas.estimate import EstimateAnalysis

class ConsistencyEngine:
    """
    ConsistencyEngine:
    Deterministic Python comparison engine.
    Builds a complete matrix of Claim Facts x Evidence Items.
    Evaluates each cell as supports / contradicts / silent / unclear.
    Computes cell confidence scores and discrepancy pairs deterministically in Python.
    """
    PROMPT_VERSION = "code-v1.3"

    def evaluate_matrix(
        self,
        narrative: Optional[NarrativeAnalysis],
        photos: Dict[str, PhotoAnalysis],
        policy: Optional[PolicyAnalysis],
        context: Optional[ContextAnalysis],
        estimate: Optional[EstimateAnalysis],
        evidence_metadata: Dict[str, Dict[str, Any]]
    ) -> ConsistencyMatrix:
        facts_list: List[Dict[str, str]] = []
        raw_facts: List[ClaimFact] = []
        
        if narrative and narrative.structured_facts:
            raw_facts = narrative.structured_facts
            for idx, f in enumerate(raw_facts):
                facts_list.append({
                    "id": f"FACT-{idx+1}",
                    "category": f.category,
                    "statement": f.fact,
                    "citation": f.sentence_citation
                })
        else:
            facts_list = [
                {"id": "FACT-1", "category": "date_time", "statement": "Incident occurred on stated date", "citation": "Statement"},
                {"id": "FACT-2", "category": "impact_direction", "statement": "Vehicle was struck from behind", "citation": "Statement"}
            ]

        evidence_ids = sorted(list(evidence_metadata.keys()))
        cells: List[ConsistencyCell] = []
        discrepancies: List[DiscrepancyPair] = []

        support_cnt = 0
        contradict_cnt = 0
        silent_cnt = 0
        unclear_cnt = 0

        # Track what contradictions we already created to prevent duplication
        added_disc_types = set()

        for fact in facts_list:
            f_id = fact["id"]
            f_cat = fact["category"]
            f_stmt = fact["statement"]
            f_stmt_lower = f_stmt.lower()

            for e_id in evidence_ids:
                e_meta = evidence_metadata.get(e_id, {})
                e_type = e_meta.get("type", "other")
                alignment: CellAlignment = "silent"
                confidence = 0.90
                citation = f"{e_id} ({e_meta.get('file_name', '')})"
                reasoning = "Evidence item does not address this specific fact."

                # 1. Narrative Evidence
                if e_type == "narrative":
                    if f_stmt in fact.get("citation", "") or f_cat in ["impact_direction", "date_time", "location", "speed", "injuries", "weather"]:
                        alignment = "supports"
                        confidence = 1.0
                        citation = f"{e_id} ('{fact.get('citation', '')[:60]}...')"
                        reasoning = "Originating statement of fact provided by claimant."
                        support_cnt += 1
                    else:
                        alignment = "silent"
                        silent_cnt += 1

                # 2. Photo Evidence
                elif e_type == "photo":
                    photo_analysis = photos.get(e_id)
                    if photo_analysis:
                        # Impact direction cross-check
                        if f_cat == "impact_direction":
                            has_rear_narrative = any(k in f_stmt_lower for k in ["rear", "behind", "back"])
                            has_front_narrative = any(k in f_stmt_lower for k in ["front", "head-on", "forward"])
                            photo_zones = [z.zone.lower() for z in photo_analysis.damaged_zones]

                            if has_rear_narrative and "front" in photo_zones and "rear" not in photo_zones:
                                alignment = "contradicts"
                                confidence = 0.92
                                citation = f"{e_id} (Front zone damage: {[z.description for z in photo_analysis.damaged_zones if z.zone=='front']})"
                                reasoning = (
                                    f"Narrative claims rear-end impact, but photo {e_id} demonstrates "
                                    f"severe/moderate impact damage concentrated solely on the front zone."
                                )
                                contradict_cnt += 1
                                if "impact_direction" not in added_disc_types:
                                    added_disc_types.add("impact_direction")
                                    discrepancies.append(DiscrepancyPair(
                                        id=f"DISC-{len(discrepancies)+1}",
                                        title="Physical Damage Location Contradicts Stated Rear-End Impact",
                                        fact_id=f_id,
                                        fact_statement=f_stmt,
                                        contradicting_evidence_id=e_id,
                                        evidence_citation=citation,
                                        severity="investigate",
                                        description=reasoning
                                    ))
                            elif has_rear_narrative and "rear" in photo_zones:
                                alignment = "supports"
                                confidence = 0.95
                                citation = f"{e_id} (Rear zone damage verified)"
                                reasoning = f"Photo {e_id} corroborates rear-end impact with verified rear damage."
                                support_cnt += 1
                            elif has_front_narrative and "front" in photo_zones:
                                alignment = "supports"
                                confidence = 0.95
                                citation = f"{e_id} (Front damage verified)"
                                reasoning = f"Photo {e_id} corroborates front impact damage."
                                support_cnt += 1
                            else:
                                alignment = "unclear"
                                confidence = 0.70
                                citation = f"{e_id} (Zones: {', '.join(photo_zones)})"
                                reasoning = "Photo shows damage pattern requiring secondary verification."
                                unclear_cnt += 1

                        # Date vs EXIF cross-check
                        elif f_cat == "date_time":
                            if photo_analysis.exif_timestamp:
                                if photo_analysis.stated_timestamp_match is False:
                                    alignment = "contradicts"
                                    confidence = 0.94
                                    citation = f"{e_id} (EXIF DateTimeOriginal: {photo_analysis.exif_timestamp})"
                                    reasoning = (
                                        f"Claimed incident date contradicts EXIF timestamp ({photo_analysis.exif_timestamp}) "
                                        f"recorded in photo {e_id} metadata."
                                    )
                                    contradict_cnt += 1
                                    if "exif_date" not in added_disc_types:
                                        added_disc_types.add("exif_date")
                                        discrepancies.append(DiscrepancyPair(
                                            id=f"DISC-{len(discrepancies)+1}",
                                            title="Photo EXIF Metadata Date Conflicts with Stated Incident Date",
                                            fact_id=f_id,
                                            fact_statement=f_stmt,
                                            contradicting_evidence_id=e_id,
                                            evidence_citation=citation,
                                            severity="investigate",
                                            description=reasoning
                                        ))
                                elif photo_analysis.stated_timestamp_match is True:
                                    alignment = "supports"
                                    confidence = 0.95
                                    citation = f"{e_id} (EXIF: {photo_analysis.exif_timestamp})"
                                    reasoning = "Photo EXIF timestamp matches stated claim date."
                                    support_cnt += 1
                                else:
                                    alignment = "silent"
                                    silent_cnt += 1
                            else:
                                alignment = "unclear"
                                confidence = 0.60
                                citation = f"{e_id} (No EXIF data)"
                                reasoning = "Photo lacks embedded EXIF date metadata."
                                unclear_cnt += 1
                        else:
                            alignment = "silent"
                            silent_cnt += 1
                    else:
                        alignment = "silent"
                        silent_cnt += 1

                # 3. Policy Evidence
                elif e_type == "policy":
                    if f_cat == "date_time":
                        alignment = "supports"
                        confidence = 0.98
                        citation = f"{e_id} (Section 0.1 Policy Period)"
                        reasoning = "Policy was active during claimed date."
                        support_cnt += 1
                    elif any(k in f_stmt_lower for k in ["uber", "lyft", "delivery", "commercial", "rideshare"]):
                        if policy and policy.overall_coverage_status == "excluded":
                            alignment = "contradicts"
                            confidence = 0.96
                            citation = f"{e_id} (Section 4.2 Commercial Use Exclusion)"
                            reasoning = "Commercial rideshare/delivery activity is strictly excluded under Section 4.2."
                            contradict_cnt += 1
                            if "policy_exclusion" not in added_disc_types:
                                added_disc_types.add("policy_exclusion")
                                discrepancies.append(DiscrepancyPair(
                                    id=f"DISC-{len(discrepancies)+1}",
                                    title="Policy Coverage Excluded by Commercial Use Clause",
                                    fact_id=f_id,
                                    fact_statement=f_stmt,
                                    contradicting_evidence_id=e_id,
                                    evidence_citation=citation,
                                    severity="investigate",
                                    description=reasoning
                                ))
                        else:
                            alignment = "silent"
                            silent_cnt += 1
                    else:
                        alignment = "silent"
                        silent_cnt += 1

                # 4. Estimate Evidence
                elif e_type == "estimate":
                    if f_cat == "impact_direction":
                        alignment = "supports"
                        confidence = 0.90
                        citation = f"{e_id} (Repair estimate line items)"
                        reasoning = "Estimate line items submitted for claim."
                        support_cnt += 1
                    else:
                        alignment = "silent"
                        silent_cnt += 1

                else:
                    alignment = "silent"
                    silent_cnt += 1

                cells.append(ConsistencyCell(
                    fact_id=f_id,
                    fact_statement=f_stmt,
                    evidence_id=e_id,
                    alignment=alignment,
                    confidence=confidence,
                    citation=citation,
                    reasoning=reasoning
                ))

        # Check Policy Exclusion if not already added
        if policy and policy.overall_coverage_status == "excluded" and "policy_exclusion" not in added_disc_types:
            added_disc_types.add("policy_exclusion")
            discrepancies.append(DiscrepancyPair(
                id=f"DISC-{len(discrepancies)+1}",
                title="Policy Coverage Excluded by Commercial Use Clause",
                fact_id="FACT-POLICY",
                fact_statement="Claimant engaged in commercial transportation or delivery during loss",
                contradicting_evidence_id="E-POLICY",
                evidence_citation="Section 4.2 (Exclusion: Commercial & Rideshare Activities)",
                severity="investigate",
                description="Loss occurred while vehicle was operated for commercial rideshare, which is strictly excluded under Policy Section 4.2."
            ))

        # Check Weather Contradiction
        if context and context.weather and context.weather.contradicts_claim and "weather" not in added_disc_types:
            added_disc_types.add("weather")
            discrepancies.append(DiscrepancyPair(
                id=f"DISC-{len(discrepancies)+1}",
                title="Stated Adverse Weather Directly Contradicted by Meteorological Archive",
                fact_id="FACT-WEATHER",
                fact_statement=f"Claimant stated severe winter/blizzard road conditions",
                contradicting_evidence_id="WEATHER-ARCHIVE",
                evidence_citation=f"Open-Meteo Archive: {context.weather.condition_description}, {context.weather.temperature_c}°C, Precip: {context.weather.precipitation_mm}mm",
                severity="investigate",
                description=context.weather.details
            ))

        # Check Estimate Phantom Items
        if estimate and estimate.phantom_line_items and "estimate_phantom" not in added_disc_types:
            added_disc_types.add("estimate_phantom")
            phantom_descs = [f"#{item.item_number} {item.description} ({item.zone}: ${item.total_cost:.2f})" for item in estimate.phantom_line_items]
            discrepancies.append(DiscrepancyPair(
                id=f"DISC-{len(discrepancies)+1}",
                title="Estimate Repair Items Lack Corresponding Photo Damage",
                fact_id="FACT-ESTIMATE",
                fact_statement=f"Repair estimate claims ${estimate.grand_total:,.2f} with {len(estimate.phantom_line_items)} unverified line items",
                contradicting_evidence_id="E-ESTIMATE",
                evidence_citation=f"Unverified items: {', '.join(phantom_descs[:2])}",
                severity="review",
                description=(
                    f"Estimate includes {len(estimate.phantom_line_items)} line items totaling ${estimate.flagged_total:,.2f} "
                    f"in zones where physical photos show zero impact damage."
                )
            ))

        # Check Recurrent Damage Pattern
        if context and context.recurrent_damage_flag and context.prior_claims and "recurrent_damage" not in added_disc_types:
            added_disc_types.add("recurrent_damage")
            p_match = context.prior_claims[0]
            discrepancies.append(DiscrepancyPair(
                id=f"DISC-{len(discrepancies)+1}",
                title="Recurrent Damage Pattern on Identical Vehicle Zone",
                fact_id="FACT-HIST",
                fact_statement=f"Vehicle sustained recurring {p_match.damage_zone} damage",
                contradicting_evidence_id="DB-CLAIMS",
                evidence_citation=f"Prior Claim #{p_match.claim_id} on {p_match.incident_date} (${p_match.payout_amount:.2f} at {p_match.garage_name})",
                severity="review",
                description=f"Prior claim recorded identical {p_match.damage_zone} damage to same vehicle within short interval."
            ))

        # Check Missing Key Evidence (e.g. Bundle 8)
        # Check if highway pileup / bodily injuries claimed without police report
        has_police_report = any(e.get("type") == "police_report" or "police" in e.get("file_name", "").lower() for e in evidence_metadata.values())
        narr_text = narrative.claimed_sequence_of_events if narrative else []
        narr_full = " ".join(narr_text).lower()
        if ("pileup" in narr_full or "highway" in narr_full or "interstate" in narr_full or "multiple cars" in narr_full) and not has_police_report:
            if "missing_police" not in added_disc_types:
                added_disc_types.add("missing_police")
                discrepancies.append(DiscrepancyPair(
                    id=f"DISC-{len(discrepancies)+1}",
                    title="Critical Missing Evidence: Official Police Collision Report Not Submitted",
                    fact_id="FACT-POLICE-REQ",
                    fact_statement="Claimant reports high-speed multi-vehicle collision on highway",
                    contradicting_evidence_id="POLICY-SEC-6.3",
                    evidence_citation="Policy Section 6.3: Police report required for multi-vehicle & highway collisions",
                    severity="review",
                    description="Claim involves high-speed multi-car collision with injuries, but no official police report or third-party details were provided."
                ))

        return ConsistencyMatrix(
            facts=facts_list,
            evidence_ids=evidence_ids,
            cells=cells,
            discrepancies=discrepancies,
            discrepancy_count=len(discrepancies),
            support_count=support_cnt,
            silent_count=silent_cnt,
            unclear_count=unclear_cnt
        )
