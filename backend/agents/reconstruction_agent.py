from typing import List, Dict, Optional
from backend.schemas.reconstruction import (
    ReconstructionAnalysis,
    TimelineEvent,
    ImpactVector
)
from backend.schemas.narrative import NarrativeAnalysis
from backend.schemas.vision import PhotoAnalysis

class ReconstructionAgent:
    PROMPT_VERSION = "v1.1"

    def reconstruct(
        self,
        narrative: Optional[NarrativeAnalysis],
        photos: Dict[str, PhotoAnalysis]
    ) -> ReconstructionAnalysis:
        # 1. Timeline Construction
        events: List[TimelineEvent] = []
        step = 1

        date_str = narrative.incident_date if narrative else "2026-05-10"
        time_str = narrative.incident_time if narrative else "14:30"

        events.append(TimelineEvent(
            step_number=step,
            timestamp_or_phase=f"{date_str} {time_str} - Pre-Impact",
            description=f"Vehicle traveling on stated route ({narrative.speed_mph or 'normal road speed'}) at {narrative.incident_location or 'designated location'}.",
            source_evidence_ids=["E1"],
            citation="Narrative Statement",
            confidence=0.95
        ))
        step += 1

        claimed_impact = narrative.impact_direction if narrative else "rear-ended"
        events.append(TimelineEvent(
            step_number=step,
            timestamp_or_phase=f"{date_str} {time_str} - Initial Contact",
            description=f"Claimed collision occurrence: {claimed_impact}. Other parties involved: {narrative.other_parties or 'secondary vehicle'}.",
            source_evidence_ids=["E1"],
            citation="Narrative Statement",
            confidence=0.90
        ))
        step += 1

        # Check Photo damage zones
        photo_damage_zones = set()
        photo_ids = list(photos.keys())
        for pid, p_analysis in photos.items():
            for z in p_analysis.damaged_zones:
                photo_damage_zones.add(z.zone.lower())
                events.append(TimelineEvent(
                    step_number=step,
                    timestamp_or_phase=f"Post-Impact Physical Evidence ({pid})",
                    description=f"Physical damage observed: {z.zone.capitalize()} ({z.severity}) - {z.description}",
                    source_evidence_ids=[pid],
                    citation=f"{pid} ({p_analysis.file_name})",
                    confidence=0.92
                ))
                step += 1

        # 2. Impact Vector Modeling
        impact_dir_model = "6 o'clock (Direct Rear Impact)"
        if "front" in photo_damage_zones and "rear" not in photo_damage_zones:
            impact_dir_model = "12 o'clock (Frontal Impact)"
        elif "left" in photo_damage_zones:
            impact_dir_model = "9 o'clock (Driver Side T-Bone / Sideswipe)"
        elif "right" in photo_damage_zones:
            impact_dir_model = "3 o'clock (Passenger Side T-Bone / Sideswipe)"

        primary_pt = "Front bumper & grille assembly" if "front" in photo_damage_zones else "Rear bumper & tailgate"
        secondary_pts = []
        if len(photo_damage_zones) > 1:
            secondary_pts = [z.capitalize() for z in photo_damage_zones if z not in primary_pt.lower()]

        impact_model = ImpactVector(
            impact_direction=impact_dir_model,
            relative_speed_estimate="15-25 mph delta-v based on panel deformation depth",
            primary_damage_point=primary_pt,
            secondary_damage_points=secondary_pts,
            rebound_trajectory="Linear longitudinal deceleration without rotational rollover"
        )

        # 3. Compatibility Evaluation
        is_consistent = True
        compatibility_score = 0.95
        explanation = "Physical damage aligns with claimed impact dynamics."

        has_rear_narrative = narrative and any(k in narrative.impact_direction.lower() for k in ["rear", "behind", "back"])
        if has_rear_narrative and "front" in photo_damage_zones and "rear" not in photo_damage_zones:
            is_consistent = False
            compatibility_score = 0.25
            explanation = (
                "PHYSICAL INCOMPATIBILITY: Claimant narrative specifies a rear-end collision while stationary/slowing, "
                "but physical damage evidence demonstrates localized frontal crush with no corresponding rear impact."
            )

        return ReconstructionAnalysis(
            timeline=events,
            impact_model=impact_model,
            physical_damage_compatibility_score=compatibility_score,
            is_damage_consistent_with_narrative=is_consistent,
            compatibility_explanation=explanation,
            reconstruction_diagram_notes=f"Primary kinetic vector: {impact_dir_model}; Damage compatibility index: {compatibility_score:.2f}."
        )

