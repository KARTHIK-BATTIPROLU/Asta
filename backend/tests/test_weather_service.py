import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.app.services.weather_service import weather_service

@pytest.mark.asyncio
async def test_get_weather():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "current": {
            "temperature_2m": 25.5,
            "apparent_temperature": 27.0
        }
    }
    
    mock_get = AsyncMock(return_value=mock_resp)
    
    with patch("httpx.AsyncClient.get", new=mock_get):
        weather = await weather_service.get_weather()
        assert weather["city"] == "Hyderabad"
        assert weather["temp_c"] == 25.5
        assert weather["feels_like_c"] == 27.0
        assert "25.5°C" in weather["summary"]

@pytest.mark.asyncio
async def test_get_weather_brief():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "current": {
            "temperature_2m": 30.0,
            "apparent_temperature": 32.0
        }
    }
    
    mock_get = AsyncMock(return_value=mock_resp)
    
    with patch("httpx.AsyncClient.get", new=mock_get):
        brief = await weather_service.get_weather_brief()
        assert "30.0°C" in brief
        assert "32.0°C" in brief
