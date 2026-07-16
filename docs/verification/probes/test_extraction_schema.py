import pytest
from pydantic import ValidationError

from backend.app.services.memory.extractor import ExtractionSchema

def test_extraction_schema_valid():
    # Test valid extraction schema
    data = {
        "insights": [
            {
                "kind": "preference",
                "text": "User loves Python",
                "entities": ["Python"],
                "confidence": 0.9,
                "evidence": "I really love Python."
            }
        ],
        "priority_signals": [],
        "contradictions": [],
        "emotional_state": {
            "overall": "happy",
            "notable_moments": ["Laughed when talking about Python"]
        },
        "open_loops": []
    }
    
    # Should not raise exception
    schema = ExtractionSchema(**data)
    assert len(schema.insights) == 1
    assert schema.emotional_state.overall == "happy"

def test_extraction_schema_invalid():
    # Test missing evidence
    data = {
        "insights": [
            {
                "kind": "preference",
                "text": "User loves Python",
                "entities": ["Python"],
                "confidence": 0.9
            }
        ],
        "priority_signals": [],
        "contradictions": [],
        "emotional_state": {
            "overall": "happy",
            "notable_moments": []
        },
        "open_loops": []
    }
    
    with pytest.raises(ValidationError):
        ExtractionSchema(**data)
