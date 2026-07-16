import pytest
from backend.app.services.memory.extractor import ExtractionSchema

def test_extraction_schema_validation():
    valid_json = {
        "insights": [
            {
                "kind": "fact",
                "text": "Karthik decided to test the memory system.",
                "entities": ["Karthik", "memory system"],
                "confidence": 0.9,
                "evidence": "I want to test the memory system today."
            }
        ],
        "priority_signals": [
            {
                "priority": "ASTA",
                "direction": "up",
                "stated_or_behaved": "stated",
                "strength": 0.8
            }
        ],
        "contradictions": [],
        "emotional_state": {
            "overall": "focused",
            "notable_moments": []
        },
        "open_loops": ["Finish phase 3 by tonight"]
    }
    
    # Should not raise exception
    schema = ExtractionSchema(**valid_json)
    assert len(schema.insights) == 1
    assert schema.insights[0].kind == "fact"
    assert schema.priority_signals[0].priority == "ASTA"
    assert len(schema.open_loops) == 1

def test_extraction_schema_invalid():
    invalid_json = {
        "insights": "This should be a list",
        "priority_signals": [],
        "contradictions": [],
        "emotional_state": {"overall": "happy", "notable_moments": []},
        "open_loops": []
    }
    
    with pytest.raises(ValueError):
        ExtractionSchema(**invalid_json)
