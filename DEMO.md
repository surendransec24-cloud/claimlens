# ClaimLens: Live Demonstration & Walkthrough Guide



This presentation script guides an evaluator, adjuster team, or stakeholder through the live capabilities of **ClaimLens**. It highlights the core architectural pillars: multi-agent runtime reasoning, deterministic consistency checking, uncertainty transparency, and dynamic incremental re-reasoning.

---

## Demonstration Setup
1. Ensure the ClaimLens backend server is running:
   ```bash
   python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
   ```
2. Open your web browser to **`http://127.0.0.1:8000`**.

---

## Part 1: The Planted Front-Versus-Rear Contradiction (Bundle 2)

### Step 1: Loading the Claim Bundle
1. In the top navigation bar, click the **"Load Test Bundle"** button.
2. Select **"2. Front Damage in Photos vs Rear-Ended Story"**.
3. Observe the system creating the claim, classifying files, and running the **11-agent pipeline**.
4. Point out the **Pipeline Status Bar** at the top:
   - All 11 agents (`IntakeAgent` $\rightarrow$ `VisionAgent` $\rightarrow$ `NarrativeAgent` $\rightarrow$ `PolicyAgent` $\rightarrow$ `ContextAgent` $\rightarrow$ `EstimateAgent` $\rightarrow$ `ConsistencyEngine` $\rightarrow$ `ReconstructionAgent` $\rightarrow$ `HypothesisAgent` $\rightarrow$ `DecisionSupportAgent` $\rightarrow$ `VerifierAgent`) execute with exact runtimes in milliseconds (e.g. `118ms`).
   - Click any agent pill to inspect its prompt version and model details.

### Step 2: The Core Finding (Strict 7-Part Format)
1. On the **Findings & Settlement** tab, inspect the generated finding:
   - **ID & Title**: `F-001 — Physical Damage Location Contradicts Stated Rear-End Impact`
   - **Severity Badge**: `INVESTIGATE` (Rose badge).
   - **Inconsistency Conflict**: Note the explicit citations linking the claimant's statement (*"struck from behind with great force"*) against Evidence item `E3` (*"severe impact damage concentrated solely on the front zone"*).
   - **Dual Hypotheses (Innocent vs Alternative)**:
     - *[Innocent Scenario]*: Insured vehicle was hit from behind and subsequently propelled forward into a leading vehicle (chain collision), producing primary front damage.
     - *[Alternative Scenario]*: Pre-existing frontal crushing pre-dated the reported incident and was conflated during body shop repair appraisal.
   - **Missing Resolving Evidence**: Explicitly lists *Independent police collision report, traffic camera footage, or statement/photos from the leading vehicle driver*.
   - **Recommended Adjuster Action**: *Require claimant to provide rear bumper photographs and official police collision report before authorizing front repairs.*
   - **Confidence & Uncertainty**: 88% confidence with explicit uncertainty disclosure: *"Discrepancy is grounded in direct physical evidence, though subjective intent and secondary kinetic forces remain unverified."*
   - **Sources**: Direct clickable links to `E1` and `E3`.

### Step 3: Computed Settlement Range
1. Review the **Computed Settlement Range** card on the right:
   - **Min Settlement**: `$0.00`
   - **Max Settlement**: `$1,630.00` (computed mathematically as: $\min(\$2,130.00, \$50,000.00) - \$500.00\text{ deductible}$).
   - Point out the status pill: **"AI recommendation, pending human review"**. The AI does not make the final decision.

### Step 4: Inspecting Evidence & Photo Damage Overlays
1. Click the **"Evidence Board & Photos"** tab.
2. Under **Uploaded Evidence Items**, review cards `E1` (Claimant Narrative), `E2` (Policy PDF), `E3` (Front Damage Photo), and `E4` (Repair Estimate).
3. Click on **`E3` (front_bumper_damage.jpg)**:
   - Notice the forensic photo viewer rendering the image with highlighted damage zones.
   - Inspect the metadata panel: camera make/model (`Sony ILCE-7RM4`), EXIF timestamp (`2026:05:10 15:10:00`), and detected zone tag (`FRONT: severe`).

### Step 5: The Consistency Matrix (Deterministic Python Engine)
1. Switch to the **"Consistency Matrix"** tab.
2. Point out the 2D matrix of Claim Facts (rows) across Evidence Items (columns `E1`, `E2`, `E3`, `E4`).
3. Find the row for **Impact Direction**:
   - `E1` (Narrative) cell is **GREEN (`Supports`)**.
   - `E3` (Photo) cell is **RED (`Contradicts`)**.
4. **Click the RED cell**:
   - A slide-over modal appears with the fact statement, exact evidence citation, confidence score (0.92), and the deterministic reasoning computed in Python.

### Step 6: Reconstruction & Impact Vector Model
1. Switch to the **"Timeline & Impact Model"** tab.
2. Review the chronological sequence of events.
3. Review the **Forensic Impact Vector Model**:
   - Model detects: `12 o'clock (Frontal Impact)` with `15-25 mph delta-v`.
   - Damage Compatibility Index drops to **`25% (CONFLICT)`**.
   - Explanation notes: *"Claimant narrative specifies a rear-end collision, but physical damage demonstrates localized frontal crush with no corresponding rear impact."*

---

## Part 2: Incremental Re-Reasoning Demonstration

This step proves the system is not a static visualization, but a real state machine that dynamically re-reasons when new evidence arrives.

### Step 7: Adding Supplemental Evidence
1. Switch to the **"Incremental Diff View"** tab.
2. Click **"Upload Supplemental Evidence"**.
3. In the upload dialog, select a supplemental document:
   - For example, an official police report: `data/bundles/bundle_1_clean/police_report.txt` or a supplemental photo showing the rear vehicle.
   - Click **"Upload & Re-Reason"**.

### Step 8: Inspecting the Diff View
1. Watch the pipeline dynamically re-execute only the affected agents.
2. Notice the **Incremental Diff View** updating with visual badges:
   - **New Evidence Added**: Displays the new evidence ID (e.g., `E5`).
   - **Resolved Findings**: Displays findings that were successfully resolved by the new evidence.
   - **Modified Findings**: Highlights any changes in severity or confidence.
   - **Settlement Range Shift**: Displays $\Delta$ change in dollar settlement amount.
3. Switch back to the **Consistency Matrix** to observe that new evidence column `E5` has been integrated into the 2D grid.

---

## Part 3: Human Adjuster Decision & Immutable Audit Trail

### Step 9: Recording Adjuster Decision
1. In the bottom fixed **Adjuster Decision Bar**, click **"Escalate to Senior SIU"** (or **"Approve Claim"**).
2. A modal opens with a mandatory reason field.
3. Enter an adjuster rationale:
   > *"Front-end damage contradicts stated rear-end impact. Escalating to Special Investigation Unit to obtain leading vehicle statement and inspect vehicle frame rails for prior rust oxidation."*
4. Click **"Confirm Decision"**.
5. Observe the case status badge instantly update: **"Decision: Escalated"**.

### Step 10: Verifying the Immutable Audit Log
1. Click the **"Audit Log"** button in the top right header.
2. The audit drawer slides open, displaying every immutable event:
   - Timestamped record of every agent run (`VisionAgent`, `NarrativeAgent`, `ConsistencyEngine`, `VerifierAgent`).
   - Prompt version numbers (`v1.1`, `code-v1.3`).
   - Gemini model identifier (`gemini-2.5-flash`).
   - The adjuster's escalation decision with the exact rationale entered in Step 9.
3. Point out that personal identifiers are masked in the UI when the **"PII Masked"** toggle is enabled, ensuring data privacy compliance.

---
*Walkthrough complete.*

