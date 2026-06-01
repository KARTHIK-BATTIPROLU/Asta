"""
WeatherTool — Current and forecast weather via OpenWeatherMap.

Operations: get_current, get_today, get_week, should_jog
Provider: OpenWeatherMap (OPENWEATHER_API_KEY env var)
Cache: 30 minutes for identical city queries
"""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

from backend.app.tools.base_tool import BaseTool

logger = logging.getLogger("WeatherTool")

OWM_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"
DEFAULT_CITY = "Lelystad"
TIMEOUT = 10.0
MAX_RETRIES = 3

# Cache: key → (timestamp, data)
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 1800  # 30 minutes


def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _cache_set(key: str, data: dict):
    _cache[key] = (time.time(), data)


class WeatherTool(BaseTool):
    name = "weather"
    description = "Current weather, daily/weekly forecast, and jog recommendation via OpenWeatherMap."

    async def validate(self, payload: dict) -> tuple[bool, str]:
        operation = payload.get("operation", "")
        if operation not in ("get_current", "get_today", "get_week", "should_jog"):
            return False, f"Invalid operation '{operation}'. Must be: get_current, get_today, get_week, should_jog"

        if not OWM_API_KEY:
            return False, "OPENWEATHER_API_KEY not configured in environment"

        return True, ""

    async def execute(self, payload: dict) -> dict:
        operation = payload["operation"]
        city = payload.get("city", DEFAULT_CITY).strip() or DEFAULT_CITY

        if operation == "get_current":
            return await self._get_current(city)
        elif operation == "get_today":
            return await self._get_today(city)
        elif operation == "get_week":
            return await self._get_week(city)
        elif operation == "should_jog":
            return await self._should_jog(city)
        else:
            return {"error": f"Unknown operation: {operation}"}

    async def _get_current(self, city: str) -> dict:
        cache_key = f"current:{city.lower()}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        data = await self._api_call("/weather", {"q": city, "units": "metric"})
        if "error" in data:
            return data

        result = {
            "data": {
                "city": data.get("name", city),
                "temperature": f"{data['main']['temp']:.0f}°C",
                "feels_like": f"{data['main']['feels_like']:.0f}°C",
                "description": data["weather"][0]["description"].capitalize(),
                "humidity": f"{data['main']['humidity']}%",
                "wind_speed": f"{data['wind']['speed']} m/s",
                "raw_temp": data["main"]["temp"],
                "raw_weather_id": data["weather"][0]["id"],
            },
            "message": f"{data['main']['temp']:.0f}°C, {data['weather'][0]['description']}, wind {data['wind']['speed']} m/s",
        }
        _cache_set(cache_key, result)
        return result

    async def _get_today(self, city: str) -> dict:
        cache_key = f"today:{city.lower()}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        data = await self._api_call("/forecast", {"q": city, "units": "metric", "cnt": 8})
        if "error" in data:
            return data

        forecasts = []
        for item in data.get("list", [])[:8]:
            forecasts.append({
                "time": item["dt_txt"],
                "temp": f"{item['main']['temp']:.0f}°C",
                "description": item["weather"][0]["description"].capitalize(),
                "rain_chance": f"{item.get('pop', 0) * 100:.0f}%",
            })

        result = {
            "data": {"city": city, "forecasts": forecasts},
            "message": f"Today's forecast for {city}: {len(forecasts)} time slots",
        }
        _cache_set(cache_key, result)
        return result

    async def _get_week(self, city: str) -> dict:
        cache_key = f"week:{city.lower()}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        data = await self._api_call("/forecast", {"q": city, "units": "metric", "cnt": 40})
        if "error" in data:
            return data

        # Group by day
        days = {}
        for item in data.get("list", []):
            day = item["dt_txt"][:10]
            if day not in days:
                days[day] = {
                    "date": day,
                    "high": item["main"]["temp_max"],
                    "low": item["main"]["temp_min"],
                    "description": item["weather"][0]["description"].capitalize(),
                }
            else:
                days[day]["high"] = max(days[day]["high"], item["main"]["temp_max"])
                days[day]["low"] = min(days[day]["low"], item["main"]["temp_min"])

        week = [
            {**d, "high": f"{d['high']:.0f}°C", "low": f"{d['low']:.0f}°C"}
            for d in list(days.values())[:7]
        ]

        result = {
            "data": {"city": city, "days": week},
            "message": f"7-day forecast for {city}",
        }
        _cache_set(cache_key, result)
        return result

    async def _should_jog(self, city: str) -> dict:
        current = await self._get_current(city)
        if "error" in current:
            return current

        data = current["data"]
        temp = data.get("raw_temp", 20)
        weather_id = data.get("raw_weather_id", 800)

        reasons = []
        should = True

        # Rain/Storm (weather codes 2xx = thunderstorm, 3xx = drizzle, 5xx = rain)
        if 200 <= weather_id < 600:
            should = False
            reasons.append(f"Weather: {data['description']} (precipitation expected)")

        # Extreme heat
        if temp > 38:
            should = False
            reasons.append(f"Temperature too high: {temp:.0f}°C (>38°C)")

        # Extreme cold
        if temp < 5:
            should = False
            reasons.append(f"Temperature too low: {temp:.0f}°C (<5°C)")

        if should:
            reasons.append(f"Good conditions: {data['description']}, {temp:.0f}°C")

        return {
            "data": {
                "should_jog": should,
                "reasons": reasons,
                "current_weather": data["description"],
                "temperature": data["temperature"],
            },
            "message": f"{'Yes' if should else 'No'} — {'; '.join(reasons)}",
        }

    async def _api_call(self, endpoint: str, params: dict) -> dict:
        params["appid"] = OWM_API_KEY

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.get(f"{OWM_BASE_URL}{endpoint}", params=params)

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning(f"[Weather] Rate limited. Retrying in {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    return resp.json()

            except httpx.TimeoutException:
                if attempt == MAX_RETRIES - 1:
                    return {"error": "Weather API timed out"}
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    return {"error": f"Weather API failed: {e}"}
                await asyncio.sleep(2 ** attempt)

        return {"error": "Weather API failed after retries"}
