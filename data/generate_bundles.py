import os
import json
from PIL import Image, ImageDraw, ImageFont
from PIL.ExifTags import Base
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "bundles")

def create_synthetic_photo(
    file_path: str,
    title: str,
    damage_zone: str,
    severity: str,
    exif_datetime: str = "2026:05:10 14:45:00",
    strip_exif: bool = False
):
    """Generates a synthetic vehicle damage photo with embedded zone overlays and EXIF metadata."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    width, height = 640, 480
    img = Image.new("RGB", (width, height), color=(40, 50, 65))
    draw = ImageDraw.Draw(img)

    # Draw mock vehicle body
    draw.rectangle([100, 100, 540, 380], fill=(70, 80, 95), outline=(180, 190, 205), width=3)
    # Windshield / glass
    draw.rectangle([200, 140, 440, 240], fill=(120, 150, 180), outline=(220, 230, 240), width=2)
    # Wheels
    draw.ellipse([140, 350, 200, 410], fill=(20, 20, 25))
    draw.ellipse([440, 350, 500, 410], fill=(20, 20, 25))

    # Damage Zone Highlight
    if damage_zone == "front":
        draw.rectangle([80, 180, 160, 340], fill=(220, 50, 50), outline=(255, 255, 0), width=4)
        draw.text((90, 250), "IMPACT\nFRONT", fill=(255, 255, 255))
    elif damage_zone == "rear":
        draw.rectangle([480, 180, 560, 340], fill=(220, 50, 50), outline=(255, 255, 0), width=4)
        draw.text((490, 250), "IMPACT\nREAR", fill=(255, 255, 255))
    elif damage_zone == "left":
        draw.rectangle([160, 240, 320, 340], fill=(240, 120, 40), outline=(255, 255, 0), width=3)
        draw.text((180, 280), "LEFT DOOR SCRATCH", fill=(255, 255, 255))
    elif damage_zone == "right":
        draw.rectangle([320, 240, 480, 340], fill=(240, 120, 40), outline=(255, 255, 0), width=3)
        draw.text((340, 280), "RIGHT QUARTER CREASE", fill=(255, 255, 255))

    # Title & Metadata Overlay
    draw.rectangle([10, 10, 630, 60], fill=(15, 23, 42))
    draw.text((20, 18), f"CLAIM EVIDENCE PHOTO - {title.upper()}", fill=(241, 245, 249))
    draw.text((20, 38), f"Zone: {damage_zone.upper()} | Severity: {severity.upper()} | Forensic Capture", fill=(148, 163, 184))

    if not strip_exif:
        exif = img.getexif()
        exif[Base.DateTimeOriginal] = exif_datetime
        exif[Base.Make] = "Sony"
        exif[Base.Model] = "ILCE-7RM4"
        img.save(file_path, "JPEG", quality=90, exif=exif)
    else:
        img.save(file_path, "JPEG", quality=75)

def create_policy_pdf(file_path: str, policyholder: str, policy_num: str, has_rideshare_exclusion: bool = True):
    """Generates a professional 2-page policy document PDF."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    c = canvas.Canvas(file_path, pagesize=letter)
    
    # Page 1
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "APEX MUTUAL INSURANCE COMPANY")
    c.setFont("Helvetica", 12)
    c.drawString(50, 730, "PERSONAL AUTO POLICY - DECLARATIONS & TERMS")
    c.line(50, 720, 550, 720)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, 690, "SECTION 0.1: POLICY PERIOD & NAMED INSURED")
    c.setFont("Helvetica", 10)
    c.drawString(60, 675, f"Named Insured: {policyholder}")
    c.drawString(60, 660, f"Policy Number: {policy_num}")
    c.drawString(60, 645, "Effective Period: 2026-01-01 00:01 EST to 2026-12-31 23:59 EST")
    c.drawString(60, 630, "Covered Auto: 2023 Honda Accord Sedan (VIN: 1HGCR2F89HA123456)")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, 595, "SECTION 1.1: LIABILITY COVERAGE (PART A)")
    c.setFont("Helvetica", 10)
    c.drawString(60, 580, "Bodily Injury Limit: $100,000 each person / $300,000 each accident")
    c.drawString(60, 565, "Property Damage Liability Limit: $100,000 each accident")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, 530, "SECTION 2.1: COLLISION COVERAGE (PART D)")
    c.setFont("Helvetica", 10)
    c.drawString(60, 515, "Peril: Direct and accidental loss to your covered auto caused by collision.")
    c.drawString(60, 500, "Maximum Stated Limit: $50,000.00 ACV")
    c.drawString(60, 485, "Deductible: $500.00 per occurrence")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, 450, "SECTION 2.2: COMPREHENSIVE COVERAGE")
    c.setFont("Helvetica", 10)
    c.drawString(60, 435, "Deductible: $250.00 per occurrence (fire, theft, vandalism, weather)")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, 400, "SECTION 4.2: EXCLUSIONS - COMMERCIAL & RIDESHARE USE")
    c.setFont("Helvetica", 10)
    if has_rideshare_exclusion:
        c.drawString(60, 385, "We do not provide coverage under Part D for any auto while being operated")
        c.drawString(60, 370, "or used by any person to carry persons or cargo for compensation or fee,")
        c.drawString(60, 355, "including during active logging into a digital transportation network (Uber, Lyft, DoorDash).")
    else:
        c.drawString(60, 385, "Commercial endorsement active.")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, 320, "SECTION 6.1: DUTIES AFTER AN ACCIDENT")
    c.setFont("Helvetica", 10)
    c.drawString(60, 305, "1. Notify company promptly with date, time, and location.")
    c.drawString(60, 290, "2. Provide police report for multi-vehicle, highway, or hit-and-run collisions.")

    c.drawString(250, 50, "Page 1 of 1")
    c.showPage()
    c.save()

def create_estimate_pdf(file_path: str, garage: str, items: list, grand_total: float):
    """Generates a professional repair estimate PDF with line items."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    c = canvas.Canvas(file_path, pagesize=letter)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 750, f"{garage.upper()} - APPRAISAL ESTIMATE")
    c.setFont("Helvetica", 10)
    c.drawString(50, 735, "Certified Collision Center & Frame Repair Specialist")
    c.line(50, 725, 550, 725)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 700, "Item")
    c.drawString(80, 700, "Description")
    c.drawString(260, 700, "Zone")
    c.drawString(330, 700, "Parts ($)")
    c.drawString(410, 700, "Labor (h)")
    c.drawString(470, 700, "Subtotal ($)")
    c.line(50, 692, 550, 692)

    y = 675
    c.setFont("Helvetica", 9)
    for idx, item in enumerate(items):
        c.drawString(50, y, str(idx + 1))
        c.drawString(80, y, item["desc"][:32])
        c.drawString(260, y, item["zone"])
        c.drawString(330, y, f"{item['parts']:.2f}")
        c.drawString(410, y, f"{item['labor_hrs']:.1f}h")
        subtotal = item["parts"] + (item["labor_hrs"] * 70.0)
        c.drawString(470, y, f"{subtotal:.2f}")
        y -= 22

    c.line(50, y + 10, 550, y + 10)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(350, y - 10, f"GRAND TOTAL: ${grand_total:,.2f}")

    c.drawString(250, 50, "Page 1 of 1")
    c.showPage()
    c.save()

def generate_all_bundles():
    os.makedirs(BASE_DATA_DIR, exist_ok=True)

    # ----------------------------------------------------
    # BUNDLE 1: Clean, Consistent Claim
    # ----------------------------------------------------
    b1_dir = os.path.join(BASE_DATA_DIR, "bundle_1_clean")
    create_synthetic_photo(
        os.path.join(b1_dir, "rear_bumper_damage.jpg"),
        "Rear Bumper Cover Dent",
        damage_zone="rear",
        severity="moderate",
        exif_datetime="2026:05:10 14:42:15"
    )
    create_policy_pdf(os.path.join(b1_dir, "policy.pdf"), "Michael Adams", "POL-100201-A")
    create_estimate_pdf(
        os.path.join(b1_dir, "estimate.pdf"),
        "Metro Collision Center",
        [
            {"desc": "Rear Bumper Cover Replacement", "zone": "rear", "parts": 450.0, "labor_hrs": 3.0},
            {"desc": "Tailgate Panel Paint Blending", "zone": "rear", "parts": 120.0, "labor_hrs": 2.5}
        ],
        grand_total=955.0
    )
    with open(os.path.join(b1_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10 at approximately 2:30 PM, I was stopped at a red light at the intersection of Main St and 4th Ave in New York. "
            "Without warning, my vehicle was struck from behind by a passenger sedan. "
            "The impact pushed my rear bumper forward and dented the tailgate. "
            "The weather was sunny and roads were completely dry."
        )
    with open(os.path.join(b1_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 1,
            "title": "Clean, Consistent Claim",
            "should_detect_inconsistency": False,
            "expected_findings_count": 0,
            "expected_coverage_status": "covered"
        }, f, indent=2)

    # ----------------------------------------------------
    # BUNDLE 2: Front Damage in Photos vs Rear-Ended Story
    # ----------------------------------------------------
    b2_dir = os.path.join(BASE_DATA_DIR, "bundle_2_front_vs_rear")
    create_synthetic_photo(
        os.path.join(b2_dir, "front_bumper_damage.jpg"),
        "Front Bumper and Radiator Crush",
        damage_zone="front",
        severity="severe",
        exif_datetime="2026:05:10 15:10:00"
    )
    create_policy_pdf(os.path.join(b2_dir, "policy.pdf"), "Marcus Vance", "POL-200302-B")
    create_estimate_pdf(
        os.path.join(b2_dir, "estimate.pdf"),
        "Apex Body Shop",
        [
            {"desc": "Front Bumper Grille Assembly", "zone": "front", "parts": 650.0, "labor_hrs": 4.0},
            {"desc": "Radiator Support & AC Condenser", "zone": "front", "parts": 850.0, "labor_hrs": 5.0}
        ],
        grand_total=2130.0
    )
    with open(os.path.join(b2_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10 at 2:30 PM, I was stationary at a traffic light when my car was struck from behind with great force. "
            "The rear impact was sudden and threw me forward in my seat. "
            "There were no other vehicles ahead of me."
        )
    with open(os.path.join(b2_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 2,
            "title": "Front Damage in Photos vs Rear-Ended Story",
            "should_detect_inconsistency": True,
            "expected_inconsistency_type": "impact_direction_mismatch",
            "expected_severity": "investigate",
            "expected_coverage_status": "covered"
        }, f, indent=2)

    # ----------------------------------------------------
    # BUNDLE 3: Photo EXIF Date Different from Claimed Date
    # ----------------------------------------------------
    b3_dir = os.path.join(BASE_DATA_DIR, "bundle_3_exif_mismatch")
    create_synthetic_photo(
        os.path.join(b3_dir, "damaged_quarter_panel.jpg"),
        "Right Side Quarter Damage",
        damage_zone="right",
        severity="moderate",
        exif_datetime="2025:11:04 09:20:11"  # 6 months earlier!
    )
    create_policy_pdf(os.path.join(b3_dir, "policy.pdf"), "Elena Rostova", "POL-300403-C")
    create_estimate_pdf(
        os.path.join(b3_dir, "estimate.pdf"),
        "Eastside Auto Body",
        [{"desc": "Right Quarter Panel Repair", "zone": "right", "parts": 700.0, "labor_hrs": 4.0}],
        grand_total=980.0
    )
    with open(os.path.join(b3_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10 at 10:15 AM, I parked my vehicle on 5th Avenue and returned to find someone had scraped my right quarter panel. "
            "I took this photograph immediately at the scene after discovering the damage."
        )
    with open(os.path.join(b3_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 3,
            "title": "Photo EXIF Date Different from Claimed Date",
            "should_detect_inconsistency": True,
            "expected_inconsistency_type": "exif_date_conflict",
            "expected_severity": "investigate"
        }, f, indent=2)

    # ----------------------------------------------------
    # BUNDLE 4: Weather Contradiction
    # ----------------------------------------------------
    b4_dir = os.path.join(BASE_DATA_DIR, "bundle_4_weather_contradiction")
    create_synthetic_photo(
        os.path.join(b4_dir, "front_guardrail_impact.jpg"),
        "Front Bumper Skid Damage",
        damage_zone="front",
        severity="moderate",
        exif_datetime="2026:05:10 16:00:00"
    )
    create_policy_pdf(os.path.join(b4_dir, "policy.pdf"), "Brian Taylor", "POL-400504-D")
    create_estimate_pdf(
        os.path.join(b4_dir, "estimate.pdf"),
        "Valley Repair Co",
        [{"desc": "Front Bumper and Fog Light", "zone": "front", "parts": 500.0, "labor_hrs": 3.0}],
        grand_total=710.0
    )
    with open(os.path.join(b4_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10 at 3:45 PM, I was driving when a sudden blizzard struck with freezing conditions and thick black ice on the highway. "
            "My car lost all traction on the slippery ice and spun into the safety guardrail."
        )
    with open(os.path.join(b4_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 4,
            "title": "Weather Contradicts Stated Conditions",
            "should_detect_inconsistency": True,
            "expected_inconsistency_type": "weather_contradiction",
            "expected_severity": "investigate"
        }, f, indent=2)

    # ----------------------------------------------------
    # BUNDLE 5: Repair Estimate Outliers / Phantom Items
    # ----------------------------------------------------
    b5_dir = os.path.join(BASE_DATA_DIR, "bundle_5_phantom_estimate")
    create_synthetic_photo(
        os.path.join(b5_dir, "left_door_scratch.jpg"),
        "Minor Left Door Surface Scratch",
        damage_zone="left",
        severity="minor",
        exif_datetime="2026:05:10 11:30:00"
    )
    create_policy_pdf(os.path.join(b5_dir, "policy.pdf"), "Kevin Miller", "POL-500605-E")
    create_estimate_pdf(
        os.path.join(b5_dir, "estimate.pdf"),
        "Speedy Precision Garage",
        [
            {"desc": "Left Door Surface Respray", "zone": "left", "parts": 250.0, "labor_hrs": 2.0},
            {"desc": "Front Axle Assembly Replacement", "zone": "mechanical", "parts": 1800.0, "labor_hrs": 8.0},
            {"desc": "Windshield Glass Replacement", "zone": "glass", "parts": 950.0, "labor_hrs": 3.0}
        ],
        grand_total=3780.0
    )
    with open(os.path.join(b5_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10, another car door swung open and made contact with my left driver-side door while parked outside a market."
        )
    with open(os.path.join(b5_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 5,
            "title": "Estimate Phantom Items Not In Photos",
            "should_detect_inconsistency": True,
            "expected_inconsistency_type": "phantom_estimate_items",
            "expected_severity": "review"
        }, f, indent=2)

    # ----------------------------------------------------
    # BUNDLE 6: Claim Excluded by Policy Clause
    # ----------------------------------------------------
    b6_dir = os.path.join(BASE_DATA_DIR, "bundle_6_policy_exclusion")
    create_synthetic_photo(
        os.path.join(b6_dir, "front_collision.jpg"),
        "Front Collision Damage",
        damage_zone="front",
        severity="moderate",
        exif_datetime="2026:05:10 17:30:00"
    )
    create_policy_pdf(os.path.join(b6_dir, "policy.pdf"), "Travis Wright", "POL-600706-F", has_rideshare_exclusion=True)
    create_estimate_pdf(
        os.path.join(b6_dir, "estimate.pdf"),
        "Downtown Motors",
        [{"desc": "Front Bumper & Hood", "zone": "front", "parts": 800.0, "labor_hrs": 4.5}],
        grand_total=1115.0
    )
    with open(os.path.join(b6_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10 at 5:15 PM, I was actively driving paying passengers for Uber rideshare when traffic abruptly stopped ahead. "
            "I collided with the vehicle in front while on duty completing a commercial trip."
        )
    with open(os.path.join(b6_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 6,
            "title": "Claim Excluded by Policy Clause (Commercial Rideshare)",
            "should_detect_inconsistency": True,
            "expected_coverage_status": "excluded",
            "expected_inconsistency_type": "policy_exclusion"
        }, f, indent=2)

    # ----------------------------------------------------
    # BUNDLE 7: Repeat Claimant with Similar Prior Damage
    # ----------------------------------------------------
    b7_dir = os.path.join(BASE_DATA_DIR, "bundle_7_repeat_claimant")
    create_synthetic_photo(
        os.path.join(b7_dir, "right_quarter_panel.jpg"),
        "Right Quarter Panel Crease",
        damage_zone="right",
        severity="moderate",
        exif_datetime="2026:05:10 13:00:00"
    )
    create_policy_pdf(os.path.join(b7_dir, "policy.pdf"), "Sarah Jenkins", "POL-700807-G")
    create_estimate_pdf(
        os.path.join(b7_dir, "estimate.pdf"),
        "Metro Precision Collision",
        [{"desc": "Right Quarter Panel Repair & Blending", "zone": "right", "parts": 900.0, "labor_hrs": 5.0}],
        grand_total=1250.0
    )
    with open(os.path.join(b7_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10 at 12:45 PM, my vehicle sustained damage to the right quarter panel and door in a parking collision."
        )
    with open(os.path.join(b7_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 7,
            "title": "Repeat Claimant with Identical Damage Pattern",
            "should_detect_inconsistency": True,
            "expected_inconsistency_type": "claims_history_match",
            "expected_severity": "review"
        }, f, indent=2)

    # ----------------------------------------------------
    # BUNDLE 8: Missing Key Evidence
    # ----------------------------------------------------
    b8_dir = os.path.join(BASE_DATA_DIR, "bundle_8_missing_evidence")
    create_synthetic_photo(
        os.path.join(b8_dir, "blurry_incident_photo.jpg"),
        "Low Quality Blurry Vehicle Photo",
        damage_zone="front",
        severity="moderate",
        strip_exif=True  # Stripped EXIF
    )
    create_policy_pdf(os.path.join(b8_dir, "policy.pdf"), "Unknown Driver", "POL-800908-H")
    create_estimate_pdf(
        os.path.join(b8_dir, "estimate.pdf"),
        "Express Collision",
        [{"desc": "Front End Body Repair", "zone": "front", "parts": 1200.0, "labor_hrs": 6.0}],
        grand_total=1620.0
    )
    with open(os.path.join(b8_dir, "narrative.txt"), "w") as f:
        f.write(
            "On 2026-05-10, there was a major high-speed multi-car pileup on the interstate involving 4 cars and injuries. "
            "I could not obtain police contact information or other driver licenses at the scene."
        )
    with open(os.path.join(b8_dir, "expected.json"), "w") as f:
        json.dump({
            "bundle_id": 8,
            "title": "Missing Key Evidence (No Police Report / Missing EXIF)",
            "should_detect_inconsistency": True,
            "expected_inconsistency_type": "missing_key_evidence",
            "expected_severity": "review"
        }, f, indent=2)

    print(f"Successfully generated all 8 synthetic claim bundles in {BASE_DATA_DIR}")

if __name__ == "__main__":
    generate_all_bundles()

