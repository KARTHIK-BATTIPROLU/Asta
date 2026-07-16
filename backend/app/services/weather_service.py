"""
ASTA Weather Service
Fetches weather data from Open-Meteo (free, keyless).
"""
import logging
import httpx

logger = logging.getLogger(__name__)

class WeatherService:
    """Service for fetching weather information."""
    
    # Open-Meteo endpoint for Hyderabad (default)
    BASE_URL = "https://api.open-meteo.com/v1/forecast"
    
    async def get_weather(self, lat: float = 17.3850, lon: float = 78.4867, city: str = "Hyderabad") -> dict:
        """Get current weather from Open-Meteo."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,apparent_temperature,precipitation,weather_code",
                        "timezone": "auto"
                    }
                )
                data = resp.json()
                current = data.get("current", {})
                
                temp_c = current.get("temperature_2m")
                feels_like_c = current.get("apparent_temperature")
                
                summary = f"{city}: {temp_c}°C, feels like {feels_like_c}°C."
                
                return {
                    "city": city,
                    "temp_c": temp_c,
                    "feels_like_c": feels_like_c,
                    "summary": summary
                }
        except Exception as e:
            logger.error(f"Weather fetch failed for {city}: {e}")
            return {
                "city": city,
                "temp_c": None,
                "feels_like_c": None,
                "summary": f"Weather data unavailable for {city}"
            }
    
    async def get_weather_brief(self, lat: float = 17.3850, lon: float = 78.4867, city: str = "Hyderabad") -> str:
        """Get brief weather summary string."""
        w = await self.get_weather(lat, lon, city)
        return w["summary"]

# Global instance
weather_service = WeatherService()
