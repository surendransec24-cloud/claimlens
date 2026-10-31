import pytest
import os
import uuid
from backend.database import SessionLocal, Base, engine
from backend.models.case import Case
from backend.models.evidence import EvidenceItem
from backend.orchestration.pipeline import pipeline_runner

@pytest.fixture
def test_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.mark.asyncio
async def test_end_to_end_pipeline_and_incremental_re_reasoning(test_db):
    case_id = str(uuid.uuid4())
    test_case = Case(
        id=case_id,
        claim_number=f"TEST-{uuid.uuid4().hex[:6].upper()}",
        policy_number="POL-992211",
        claimant_name="David Miller",
        vehicle_vin="1HGCR2F89HA123456",
        vehicle_plate="6ABC78",
        incident_date="2026-05-10",
        incident_location="Broadway & 42nd St, NY",
        status="Pending human review"
    )
    test_db.add(test_case)
    test_db.commit()

    # Evidence 1: Narrative (Claimant says rear-ended)
    e1 = EvidenceItem(
        id="E1",
        case_id=case_id,
        file_name="claimant_statement.txt",
        file_path="mock_path_e1.txt",
        file_type="narrative",
        mime_type="text/plain",
        extracted_text=(
            "On 2026-05-10 at approximately 2:30 PM, I was stopped at a red signal on Broadway. "
            "Without warning, my car was struck from behind by a delivery van. "
            "The impact pushed me forward slightly."
        )
    )

    # Evidence 2: Policy document
    e2 = EvidenceItem(
        id="E2",
        case_id=case_id,
        file_name="auto_policy.txt",
        file_path="mock_path_e2.txt",
        file_type="policy",
        mime_type="text/plain",
        extracted_text=(
            "Section 0.1 Policy Period: 2026-01-01 to 2026-12-31. "
            "Section 2.1 Collision Coverage: Limit $50,000, Deductible $500. "
            "Section 4.2 Exclusion: Commercial rideshare and delivery activities are excluded."
        )
    )

    # Evidence 3: Photo showing FRONT damage (planted contradiction)
    e3 = EvidenceItem(
        id="E3",
        case_id=case_id,
        file_name="front_damage.jpg",
        file_path="mock_path_e3.jpg",
        file_type="photo",
        mime_type="image/jpeg",
        extracted_text="Photo showing front bumper crush"
    )

    # Evidence 4: Estimate with front repair items
    e4 = EvidenceItem(
        id="E4",
        case_id=case_id,
        file_name="repair_estimate.txt",
        file_path="mock_path_e4.txt",
        file_type="estimate",
        mime_type="text/plain",
        extracted_text=(
            "1. Front Bumper Grille | front | 450.00 | 3.0 | 70.00\n"
            "2. Radiator Core Support | front | 600.00 | 4.0 | 70.00\n"
            "Total Estimate: 1540.00"
        )
    )

    test_db.add_all([e1, e2, e3, e4])
    test_db.commit()

    # Run full pipeline
    state = await pipeline_runner.run_pipeline(case_id=case_id, db=test_db)
    
    # Assertions
    assert state.case_id == case_id
    assert state.overall_status == "completed"
    assert len(state.findings) >= 1
    # Check that planted contradiction was caught
    planted_finding = next((f for f in state.findings if "front" in f.title.lower() or "damage" in f.title.lower()), None)
    assert planted_finding is not None
    assert planted_finding.severity in ["review", "investigate"]
    assert len(planted_finding.possible_explanations) >= 2
    assert planted_finding.recommended_action != ""
    assert len(planted_finding.sources) >= 1

    # Check verifier
    assert state.verifier_result is not None
    assert state.verifier_result.passed is True
    assert state.verifier_result.prohibited_terms_detected == 0

    # Incremental Re-Reasoning: Add supplemental rear photo Evidence 5
    e5 = EvidenceItem(
        id="E5",
        case_id=case_id,
        file_name="supplemental_rear_bumper.jpg",
        file_path="mock_path_e5.jpg",
        file_type="photo",
        mime_type="image/jpeg",
        extracted_text="Photo of rear bumper showing scratches"
    )
    test_db.add(e5)
    test_db.commit()

    inc_state = await pipeline_runner.run_incremental_re_reasoning(
        case_id=case_id,
        new_evidence_ids=["E5"],
        db=test_db
    )
    assert inc_state.findings_diff is not None
    assert "new_evidence_added" in inc_state.findings_diff
    assert inc_state.findings_diff["new_evidence_added"] == ["E5"]

