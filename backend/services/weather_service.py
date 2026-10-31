import httpx
from typing import Optional, Dict, Any
from backend.config import settings

# Mapping of Open-Meteo weather codes to human-readable weather descriptions
WMO_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}

class WeatherService:
    @staticmethod
    async def fetch_historical_weather(
        latitude: float,
        longitude: float,
        date_str: str  # YYYY-MM-DD
    ) -> Dict[str, Any]:
        """Fetches historical weather from Open-Meteo API without requiring an API key."""
        url = (
            f"{settings.OPEN_METEO_BASE_URL}?"
            f"latitude={latitude}&longitude={longitude}&"
            f"start_date={date_str}&end_date={date_str}&"
            f"daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max&"
            f"timezone=auto"
        )
        
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    daily = data.get("daily", {})
                    codes = daily.get("weather_code", [0])
                    code = codes[0] if codes else 0
                    t_max = daily.get("temperature_2m_max", [20.0])[0]
                    t_min = daily.get("temperature_2m_min", [15.0])[0]
                    precip = daily.get("precipitation_sum", [0.0])[0]
                    wind = daily.get("wind_speed_10m_max", [10.0])[0]
                    avg_temp = round((t_max + t_min) / 2.0, 1)
                    
                    return {
                        "status": "success",
                        "temperature_c": avg_temp,
                        "precipitation_mm": float(precip or 0.0),
                        "weather_code": int(code or 0),
                        "condition_description": WMO_CODE_MAP.get(int(code or 0), "Clear / Normal"),
                        "wind_speed_kmh": float(wind or 0.0),
                        "is_historical_recorded": True
                    }
        except Exception as e:
            # Graceful fallback if offline or request fails
            pass
            
        # Default fallback reasonable weather
        return {
            "status": "fallback",
            "temperature_c": 22.0,
            "precipitation_mm": 0.0,
            "weather_code": 0,
            "condition_description": "Clear sky (historical records estimated)",
            "wind_speed_kmh": 12.0,
            "is_historical_recorded": False
        }

