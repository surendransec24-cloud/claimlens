import pytest
import os
import json
from backend.agents.intake_agent import IntakeAgent
from backend.agents.vision_agent import VisionAgent
from backend.agents.narrative_agent import NarrativeAgent
from backend.agents.policy_agent import PolicyAgent
from backend.agents.estimate_agent import EstimateAgent
from backend.agents.consistency_engine import ConsistencyEngine
from backend.agents.reconstruction_agent import ReconstructionAgent
from backend.agents.hypothesis_agent import HypothesisAgent
from backend.agents.decision_support_agent import DecisionSupportAgent
from backend.agents.verifier_agent import VerifierAgent
from backend.schemas.vision import PhotoAnalysis, DamagedZoneDetail
from backend.schemas.common import FindingSchema, SourceRef
from backend.schemas.decision import DecisionSupportOutput, SettlementBreakdown

def test_intake_classification():
    agent = IntakeAgent()
    assert agent.classify_file("front_bumper.jpg", "image/jpeg") == "photo"
    assert agent.classify_file("policy_document.pdf", "application/pdf", "insuring agreement Section 2.1") == "policy"
    assert agent.classify_file("repair_estimate.txt", "text/plain", "parts labor body shop subtotal") == "estimate"
    assert agent.classify_file("driver_statement.txt", "text/plain", "claimant incident description") == "narrative"
    assert agent.classify_file("police_collision_report.pdf", "application/pdf", "traffic collision report officer") == "police_report"

@pytest.mark.asyncio
async def test_narrative_agent_citation_extraction():
    agent = NarrativeAgent()
    text = (
        "On 2026-05-10 at approximately 2:30 PM, I was stopped at a red light at the intersection of Main St and 4th Ave. "
        "Suddenly, my vehicle was struck from behind with severe force by a black pickup truck. "
        "The impact caused me to jolt forward, resulting in mild neck whiplash pain."
    )
    analysis = await agent.analyze_narrative("E1", text)
    assert analysis.incident_date == "2026-05-10"
    assert "rear-ended" in analysis.impact_direction.lower()
    assert len(analysis.structured_facts) >= 2
    # Check that each fact cites an exact sentence
    for f in analysis.structured_facts:
        assert f.sentence_citation in text

@pytest.mark.asyncio
async def test_policy_agent_rules_and_evaluation():
    agent = PolicyAgent()
    policy_text = """
    SECTION 0.1 POLICY PERIOD
    Active from 2026-01-01 to 2026-12-31.
    SECTION 2.1 COLLISION COVERAGE
    Limit: $50,000. Deductible: $500.
    SECTION 4.2 EXCLUSIONS
    Commercial & Rideshare: No coverage applies if vehicle is used for commercial rideshare or compensated delivery.
    """
    analysis = await agent.analyze_policy("E2", policy_text)
    assert analysis.applicable_deductible == 500.0
    assert analysis.applicable_limit == 50000.0
    assert analysis.overall_coverage_status in ["covered", "excluded", "unclear"]
    assert len(analysis.evaluations) >= 2
    assert any("Section 2.1" in e.clause_cited for e in analysis.evaluations)

def test_estimate_agent_arithmetic_and_cross_check():
    agent = EstimateAgent()
    sample_text = """
    Repair Facility: Precision Auto Body
    1. Front Bumper Assembly | front | 550.00 | 3.5 | 70.00
    2. Radiator Core Support | front | 400.00 | 2.0 | 70.00
    3. Left Rear Quarter Panel | rear | 800.00 | 5.0 | 70.00
    Total Estimate: 2485.00
    """
    # Simulate photos showing only front damage
    photos = {
        "E3": PhotoAnalysis(
            evidence_id="E3",
            file_name="front_damage.jpg",
            damaged_zones=[
                DamagedZoneDetail(zone="front", severity="moderate", description="Crushed bumper and grill")
            ]
        )
    }
    analysis = agent.parse_and_cross_check(sample_text, photos)
    assert analysis.arithmetic_valid is True
    # Rear item should be flagged as phantom because only front damage is in photos
    assert len(analysis.phantom_line_items) >= 1
    assert any(item.zone == "rear" for item in analysis.phantom_line_items)

def test_consistency_engine_matrix_evaluation():
    engine = ConsistencyEngine()
    photos = {
        "E3": PhotoAnalysis(
            evidence_id="E3",
            file_name="front_crush.jpg",
            damaged_zones=[
                DamagedZoneDetail(zone="front", severity="severe", description="Front bumper crushed")
            ]
        )
    }
    from backend.schemas.narrative import NarrativeAnalysis, ClaimFact
    narrative = NarrativeAnalysis(
        incident_date="2026-05-10",
        impact_direction="rear-ended",
        structured_facts=[
            ClaimFact(category="impact_direction", fact="Vehicle was struck from behind (rear-ended)", sentence_citation="I was struck from behind.")
        ]
    )
    meta = {
        "E1": {"type": "narrative", "file_name": "statement.txt"},
        "E3": {"type": "photo", "file_name": "front_crush.jpg"}
    }
    matrix = engine.evaluate_matrix(
        narrative=narrative,
        photos=photos,
        policy=None,
        context=None,
        estimate=None,
        evidence_metadata=meta
    )
    assert matrix.discrepancy_count >= 1
    # Check that contradictory cell exists
    contradictory_cells = [c for c in matrix.cells if c.alignment == "contradicts"]
    assert len(contradictory_cells) >= 1
    assert contradictory_cells[0].evidence_id == "E3"

def test_verifier_agent_anti_fraud_guardrail():
    agent = VerifierAgent()
    # Create finding intentionally containing forbidden word "fraud"
    tainted_finding = FindingSchema(
        id="F-001",
        title="Suspected Fraud in Front Damage",
        severity="investigate",
        inconsistency="Claimant committed fraudulent misrepresentation regarding impact point.",
        possible_explanations=[
            "Fraudulent attempt to claim pre-existing front damage.",
            "Secondary impact pushed car forward."
        ],
        missing_evidence=["Rear vehicle photos"],
        recommended_action="Investigate fraud immediately.",
        confidence=0.85,
        confidence_explanation="High confidence of conflict.",
        sources=[SourceRef(evidence_id="E1", location="Sentence 1"), SourceRef(evidence_id="E3", location="Zone: front")]
    )
    decision = DecisionSupportOutput(
        settlement_range=SettlementBreakdown(
            total_claimed_estimate=2500.0,
            deductible=500.0,
            policy_limit=50000.0,
            undisputed_amount=1000.0,
            disputed_or_flagged_amount=1500.0,
            coverage_status="covered",
            settlement_minimum=500.0,
            settlement_maximum=2000.0,
            formula_applied="Formula standard"
        ),
        missing_evidence=["Rear photos"],
        recommended_investigation_steps=["Check photos"],
        status_label="AI recommendation, pending human review",
        summary="Claim has fraud flags."
    )

    clean_findings, clean_decision, verifier_res = agent.verify(
        findings=[tainted_finding],
        decision_support=decision,
        valid_evidence_ids=["E1", "E3"]
    )

    # Assert forbidden word was sanitized
    assert verifier_res.prohibited_terms_detected >= 1
    for f in clean_findings:
        assert "fraud" not in f.title.lower()
        assert "fraud" not in f.inconsistency.lower()
        assert "fraud" not in " ".join(f.possible_explanations).lower()
        assert "fraud" not in f.recommended_action.lower()
    assert "fraud" not in clean_decision.summary.lower()
    assert verifier_res.passed is True
