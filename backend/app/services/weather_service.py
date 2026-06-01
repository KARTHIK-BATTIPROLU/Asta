"""
ASTA Weather Service
Fetches weather data from OpenWeather API.
"""
import logging
import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)


class WeatherService:
    """Service for fetching weather information."""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
    
    async def get_weather(self, city: str = "Hyderabad") -> dict:
        """Get current weather for a city. Default: Hyderabad (Karthik's location)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "q": city,
                        "appid": settings.OPENWEATHER_API_KEY,
                        "units": "metric"
                    }
                )
                data = resp.json()
                
                return {
                    "city": city,
                    "temp_c": data["main"]["temp"],
                    "feels_like_c": data["main"]["feels_like"],
                    "condition": data["weather"][0]["description"],
                    "humidity": data["main"]["humidity"],
                    "summary": (
                        f"{city}: {data['main']['temp']:.0f}°C, "
                        f"{data['weather'][0]['description']}, "
                        f"feels like {data['main']['feels_like']:.0f}°C"
                    )
                }
        except Exception as e:
            logger.error(f"Weather fetch failed for {city}: {e}")
            return {
                "city": city,
                "temp_c": None,
                "feels_like_c": None,
                "condition": "unavailable",
                "humidity": None,
                "summary": f"Weather data unavailable for {city}"
            }
    
    async def get_weather_brief(self, city: str = "Hyderabad") -> str:
        """Get brief weather summary string."""
        w = await self.get_weather(city)
        return w["summary"]


# Global instance
weather_service = WeatherService()
