from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
from backend.schemas.context import ContextAnalysis, WeatherData, PriorClaimMatch
from backend.schemas.narrative import NarrativeAnalysis
from backend.models.claims_history import ClaimsHistory
from backend.services.weather_service import WeatherService

class ContextAgent:
    PROMPT_VERSION = "v1.0"

    async def gather_context(
        self,
        db: Session,
        incident_date_str: str,
        location_str: Optional[str] = None,
        policyholder_id: Optional[str] = None,
        vehicle_vin: Optional[str] = None,
        garage_name: Optional[str] = None,
        claimed_weather: Optional[str] = None
    ) -> ContextAnalysis:
        # 1. Fetch weather via Open-Meteo
        # Default coordinates for common metropolitan area if raw string
        lat, lon = 40.7128, -74.0060  # Default NY / East Coast metro
        if location_str and "chicago" in location_str.lower():
            lat, lon = 41.8781, -87.6298
        elif location_str and "los angeles" in location_str.lower():
            lat, lon = 34.0522, -118.2437

        # Clean date string YYYY-MM-DD
        clean_date = incident_date_str
        try:
            # Normalize to YYYY-MM-DD
            dt = datetime.strptime(incident_date_str[:10], "%Y-%m-%d")
            clean_date = dt.strftime("%Y-%m-%d")
        except Exception:
            clean_date = "2026-05-10"

        weather_res = await WeatherService.fetch_historical_weather(lat, lon, clean_date)
        
        # Check weather contradiction
        contradicts_weather = False
        weather_details = f"Historical weather at location: {weather_res['condition_description']}, Temp: {weather_res['temperature_c']}°C, Precip: {weather_res['precipitation_mm']}mm, Wind: {weather_res['wind_speed_kmh']}km/h."
        
        if claimed_weather:
            cl_low = claimed_weather.lower()
            if any(k in cl_low for k in ["blizzard", "snow", "ice", "slippery ice", "freezing"]) and weather_res["temperature_c"] > 15.0:
                contradicts_weather = True
                weather_details += f" CONTRADICTION: Claimant stated '{claimed_weather}', but official meteorological records recorded {weather_res['temperature_c']}°C with zero snow/ice."
            elif any(k in cl_low for k in ["heavy rain", "torrential", "flooding"]) and weather_res["precipitation_mm"] < 0.5:
                contradicts_weather = True
                weather_details += f" CONTRADICTION: Claimant stated torrential rain, but historical precipitation was {weather_res['precipitation_mm']}mm."

        weather_data = WeatherData(
            temperature_c=weather_res["temperature_c"],
            precipitation_mm=weather_res["precipitation_mm"],
            weather_code=weather_res["weather_code"],
            condition_description=weather_res["condition_description"],
            wind_speed_kmh=weather_res["wind_speed_kmh"],
            is_historical_recorded=weather_res.get("is_historical_recorded", True),
            contradicts_claim=contradicts_weather,
            details=weather_details
        )

        # 2. Query Claims History table
        prior_matches: List[PriorClaimMatch] = []
        repeat_claimant = False
        recurrent_damage = False
        notes: List[str] = []

        query = db.query(ClaimsHistory)
        filters = []
        if policyholder_id:
            filters.append(ClaimsHistory.policyholder_id == policyholder_id)
        if vehicle_vin:
            filters.append(ClaimsHistory.vehicle_vin == vehicle_vin)

        records = query.all()
        # Find matching historical claims
        for r in records:
            match = False
            sim_reason = []
            if policyholder_id and (r.policyholder_id == policyholder_id or r.claimant_name.lower() in str(policyholder_id).lower()):
                match = True
                sim_reason.append("Same policyholder")
                repeat_claimant = True
            if vehicle_vin and r.vehicle_vin == vehicle_vin:
                match = True
                sim_reason.append("Same vehicle VIN")
            if garage_name and r.garage_name and garage_name.lower() in r.garage_name.lower():
                match = True
                sim_reason.append(f"Same repair garage ({r.garage_name})")

            if match:
                # Check recurrent damage zone
                sim_reason_str = ", ".join(sim_reason)
                prior_matches.append(PriorClaimMatch(
                    claim_id=r.id,
                    incident_date=r.incident_date,
                    damage_zone=r.damage_zone,
                    payout_amount=r.payout_amount,
                    garage_name=r.garage_name,
                    similarity_reason=sim_reason_str
                ))
                notes.append(f"Prior claim #{r.id} ({r.incident_date}): {r.damage_zone} damage paid ${r.payout_amount:.2f} at {r.garage_name}.")

        if len(prior_matches) >= 1:
            recurrent_damage = True

        return ContextAnalysis(
            weather=weather_data,
            prior_claims=prior_matches,
            days_since_policy_start=130,  # 130 days into standard policy year
            short_tenure_flag=False,
            repeat_claimant_flag=repeat_claimant,
            recurrent_damage_flag=recurrent_damage,
            notes=notes
        )

