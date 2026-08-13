import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.app.services.news_service import news_service

@pytest.mark.asyncio
async def test_fetch_rss_titles():
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item><title>First Title</title></item>
            <item><title>Second Title</title></item>
            <item><title>Third Title</title></item>
        </channel>
    </rss>
    """
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = rss_xml.encode("utf-8")
    
    mock_get = AsyncMock(return_value=mock_resp)
    
    with patch("httpx.AsyncClient.get", new=mock_get):
        titles = await news_service._fetch_rss_titles("http://fake.url", limit=2)
        assert len(titles) == 2
        assert titles[0] == "First Title"
        assert titles[1] == "Second Title"

@pytest.mark.asyncio
async def test_get_morning_headlines():
    with patch.object(news_service, "_fetch_rss_titles", side_effect=[["HN 1", "HN 2"], ["Arxiv 1"]]):
        brief = await news_service.get_morning_headlines()
        assert "From Hacker News:" in brief
        assert "HN 1" in brief
        assert "HN 2" in brief
        assert "From arXiv AI:" in brief
        assert "Arxiv 1" in brief
