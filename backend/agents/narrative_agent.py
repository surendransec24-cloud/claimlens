import re
from typing import List, Optional
from backend.schemas.narrative import NarrativeAnalysis, ClaimFact
from backend.services.llm_service import llm_service

SYSTEM_PROMPT = """You are an expert claims narrative analyst for motor insurance claims.
Extract structured factual statements from the claimant's narrative.
For every extracted fact, you MUST cite the exact verbatim sentence from the statement where it originates.
Categories to extract:
- date_time: Incident date and time
- location: Exact road, intersection, or city
- impact_direction: Direction of collision (rear-ended, head-on, side impact)
- parties: Other vehicles, drivers, or pedestrians involved
- speed: Vehicle traveling speed
- injuries: Any claimed bodily injuries
- events: Ordered chronology of actions
- weather: Stated atmospheric/road surface conditions

GUARDRAIL: Remain completely neutral. Never output words like 'fraud', 'fraudulent', or accuse the claimant. Only extract facts and sentence quotes."""

USER_PROMPT_TEMPLATE = """Analyze the following claimant narrative for evidence item {evidence_id}:

\"\"\"
{text}
\"\"\"

Extract all discrete facts and output adhering strictly to the NarrativeAnalysis schema. Every fact must quote the exact sentence."""

class NarrativeAgent:
    PROMPT_VERSION = "v1.1"

    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        # Clean regex to split text into sentences
        raw = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in raw if s.strip()]

    async def analyze_narrative(self, evidence_id: str, text: str) -> NarrativeAnalysis:
        if not text.strip():
            return NarrativeAnalysis()

        # If LLM configured, call Gemini
        if llm_service.is_configured:
            try:
                prompt = USER_PROMPT_TEMPLATE.format(evidence_id=evidence_id, text=text)
                parsed, err = await llm_service.generate_structured(
                    prompt=prompt,
                    response_schema=NarrativeAnalysis,
                    system_instruction=SYSTEM_PROMPT
                )
                if parsed and parsed.structured_facts:
                    return parsed
            except Exception as e:
                print(f"[NarrativeAgent] LLM parsing failed: {e}")

        # Deterministic sentence-level fallback extractor
        sentences = self._split_into_sentences(text)
        facts: List[ClaimFact] = []
        date_val = None
        time_val = None
        loc_val = None
        direction_val = None
        parties_val = None
        speed_val = None
        injuries_val = None
        weather_val = None
        events: List[str] = []

        date_pat = re.compile(r'\b(20\d\d[-/]\d\d[-/]\d\d|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? 20\d\d)\b', re.IGNORECASE)
        time_pat = re.compile(r'\b(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?|\d{1,2}\s*(?:AM|PM|am|pm))\b')
        speed_pat = re.compile(r'(\d{1,3}\s*mph|\d{1,3}\s*km/h)', re.IGNORECASE)

        for sent in sentences:
            s_low = sent.lower()

            # Date
            d_match = date_pat.search(sent)
            if d_match and not date_val:
                date_val = d_match.group(1)
                facts.append(ClaimFact(
                    category="date_time",
                    fact=f"Incident occurred on {date_val}",
                    sentence_citation=sent
                ))

            # Time
            t_match = time_pat.search(sent)
            if t_match and not time_val:
                time_val = t_match.group(1)
                facts.append(ClaimFact(
                    category="date_time",
                    fact=f"Incident occurred at approximately {time_val}",
                    sentence_citation=sent
                ))

            # Impact direction
            if any(k in s_low for k in ["rear-ended", "rear ended", "hit from behind", "struck from behind"]):
                direction_val = "rear-ended"
                facts.append(ClaimFact(
                    category="impact_direction",
                    fact="Vehicle was struck from behind (rear-ended)",
                    sentence_citation=sent
                ))
            elif any(k in s_low for k in ["head-on", "head on", "front bumper", "hit oncoming", "struck the car ahead"]):
                direction_val = "head-on / front impact"
                facts.append(ClaimFact(
                    category="impact_direction",
                    fact="Vehicle sustained front-end collision",
                    sentence_citation=sent
                ))
            elif any(k in s_low for k in ["t-bone", "t bone", "side impact", "broadsided"]):
                direction_val = "side-impact"
                facts.append(ClaimFact(
                    category="impact_direction",
                    fact="Vehicle sustained side impact",
                    sentence_citation=sent
                ))

            # Location
            if any(k in s_low for k in ["on ", "at ", "near ", "intersection", "highway", "avenue", "street", "road"]):
                if not loc_val and ("street" in s_low or "avenue" in s_low or "blvd" in s_low or "hwy" in s_low or "intersection" in s_low or "at " in s_low):
                    loc_val = sent
                    facts.append(ClaimFact(
                        category="location",
                        fact=f"Incident location: {sent}",
                        sentence_citation=sent
                    ))

            # Speed
            sp_match = speed_pat.search(sent)
            if sp_match and not speed_val:
                speed_val = sp_match.group(1)
                facts.append(ClaimFact(
                    category="speed",
                    fact=f"Reported speed was {speed_val}",
                    sentence_citation=sent
                ))

            # Injuries
            if any(k in s_low for k in ["injur", "whiplash", "hospital", "ambulance", "hurt", "pain", "doctor"]):
                injuries_val = sent
                facts.append(ClaimFact(
                    category="injuries",
                    fact="Injuries reported",
                    sentence_citation=sent
                ))

            # Weather stated
            if any(k in s_low for k in ["snow", "rain", "blizzard", "ice", "fog", "clear", "sunny", "storm"]):
                weather_val = sent
                facts.append(ClaimFact(
                    category="weather",
                    fact=f"Stated weather condition: {sent}",
                    sentence_citation=sent
                ))

            # Other parties
            if any(k in s_low for k in ["other driver", "pickup", "truck", "sedan", "another vehicle", "second car"]):
                parties_val = sent
                facts.append(ClaimFact(
                    category="parties",
                    fact="Other party involved in collision",
                    sentence_citation=sent
                ))

            events.append(sent)

        return NarrativeAnalysis(
            incident_date=date_val or "2026-05-10",
            incident_time=time_val or "14:30",
            incident_location=loc_val or "Specified location in statement",
            impact_direction=direction_val or "collision",
            other_parties=parties_val,
            speed_mph=speed_val,
            injuries=injuries_val or "None reported",
            claimed_sequence_of_events=events,
            structured_facts=facts,
            weather_claimed=weather_val
        )

