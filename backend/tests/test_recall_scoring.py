import pytest
from datetime import datetime, timedelta, timezone
from backend.app.services.memory.recall import calculate_recency_score, calculate_behavioral_score

def test_recency_score():
    now = datetime.now(timezone.utc)
    # Today's memory should have score close to 1.0
    assert calculate_recency_score(now) == pytest.approx(1.0, abs=0.01)
    
    # 30 days old memory should have score 0.5
    thirty_days_ago = now - timedelta(days=30)
    assert calculate_recency_score(thirty_days_ago) == pytest.approx(0.5, abs=0.01)
    
    # 60 days old memory should have score 0.25
    sixty_days_ago = now - timedelta(days=60)
    assert calculate_recency_score(sixty_days_ago) == pytest.approx(0.25, abs=0.01)

def test_behavioral_score():
    memory_normal = {"confidence": 0.8, "pinned": False}
    assert calculate_behavioral_score(memory_normal) == 0.8
    
    memory_pinned = {"confidence": 0.5, "pinned": True}
    assert calculate_behavioral_score(memory_pinned) == 0.8
    
    memory_max = {"confidence": 0.9, "pinned": True}
    # Should cap at 1.0
    assert calculate_behavioral_score(memory_max) == 1.0
