"""Tests for GraphLTM seed data validation logic."""
import pytest
from backend.app.services.memory.graph_ltm import GraphLTMManager


@pytest.fixture
def graph_ltm():
    """Create a GraphLTMManager instance for testing."""
    return GraphLTMManager()


@pytest.fixture
def valid_seed_data():
    """Create a complete valid seed data structure."""
    return {
        "person": {
            "name": "Test User",
            "role": "Developer",
            "location": "Test City",
            "github": "testuser",
            "college": "Test University",
            "year_of_study": "3rd Year",
            "personality_summary": "Test personality",
            "timezone": "UTC",
            "current_focus": "Testing"
        },
        "skills": [
            {"name": "Python", "level": "Expert", "priority": "High"}
        ],
        "projects": [
            {"name": "Test Project", "description": "A test", "stage": "Active", 
             "emotional_state": "Excited", "started_date": "2024-01-01"}
        ],
        "goals": [
            {"name": "Test Goal", "deadline": "2024-12-31", 
             "current_progress": "50%", "type": "Short-term"}
        ],
        "priorities": [
            {"name": "Test Priority", "category": "Work", "weight": 0.8,
             "source": "User-defined", "trend": "Stable", "constraint": None}
        ],
        "communities": [
            {"name": "Test Community", "member_count": 100, "growth_target": 200}
        ],
        "organizations": [
            {"name": "Test Org", "role": "Member", "type": "Company"}
        ],
        "relationships": [
            {"from": "Test User", "to": "Python", "type": "HAS_SKILL", "metadata": {}}
        ]
    }


class TestValidateSeedSchema:
    """Test suite for _validate_seed_schema method."""

    def test_valid_complete_seed_data(self, graph_ltm, valid_seed_data):
        """Test validation passes with complete valid seed data."""
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is True
        assert result["missing_fields"] == []

    def test_missing_person_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'person' field is missing."""
        del valid_seed_data["person"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "person" in result["missing_fields"]
        assert len(result["missing_fields"]) == 1

    def test_person_field_not_dict(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'person' field is not a dict/object."""
        valid_seed_data["person"] = "not a dict"
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "person" in result["missing_fields"]

    def test_person_field_is_none(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'person' field is None."""
        valid_seed_data["person"] = None
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "person" in result["missing_fields"]

    def test_missing_skills_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'skills' array field is missing."""
        del valid_seed_data["skills"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "skills" in result["missing_fields"]

    def test_missing_projects_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'projects' array field is missing."""
        del valid_seed_data["projects"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "projects" in result["missing_fields"]

    def test_missing_goals_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'goals' array field is missing."""
        del valid_seed_data["goals"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "goals" in result["missing_fields"]

    def test_missing_priorities_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'priorities' array field is missing."""
        del valid_seed_data["priorities"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "priorities" in result["missing_fields"]

    def test_missing_communities_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'communities' array field is missing."""
        del valid_seed_data["communities"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "communities" in result["missing_fields"]

    def test_missing_organizations_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'organizations' array field is missing."""
        del valid_seed_data["organizations"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "organizations" in result["missing_fields"]

    def test_missing_relationships_field(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'relationships' array field is missing."""
        del valid_seed_data["relationships"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "relationships" in result["missing_fields"]

    def test_skills_field_not_list(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'skills' field is not an array/list."""
        valid_seed_data["skills"] = "not a list"
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "skills" in result["missing_fields"]

    def test_projects_field_not_list(self, graph_ltm, valid_seed_data):
        """Test validation fails when 'projects' field is not an array/list."""
        valid_seed_data["projects"] = {"not": "a list"}
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "projects" in result["missing_fields"]

    def test_multiple_missing_fields(self, graph_ltm, valid_seed_data):
        """Test validation fails with multiple missing fields and reports all."""
        del valid_seed_data["person"]
        del valid_seed_data["skills"]
        del valid_seed_data["projects"]
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "person" in result["missing_fields"]
        assert "skills" in result["missing_fields"]
        assert "projects" in result["missing_fields"]
        assert len(result["missing_fields"]) == 3

    def test_all_fields_missing(self, graph_ltm):
        """Test validation fails when all required fields are missing."""
        empty_data = {}
        
        result = graph_ltm._validate_seed_schema(empty_data)
        
        assert result["valid"] is False
        assert len(result["missing_fields"]) == 8  # All 8 required fields
        assert "person" in result["missing_fields"]
        assert "skills" in result["missing_fields"]
        assert "projects" in result["missing_fields"]
        assert "goals" in result["missing_fields"]
        assert "priorities" in result["missing_fields"]
        assert "communities" in result["missing_fields"]
        assert "organizations" in result["missing_fields"]
        assert "relationships" in result["missing_fields"]

    def test_empty_arrays_are_valid(self, graph_ltm, valid_seed_data):
        """Test validation passes when array fields are empty but present."""
        valid_seed_data["skills"] = []
        valid_seed_data["projects"] = []
        valid_seed_data["goals"] = []
        valid_seed_data["priorities"] = []
        valid_seed_data["communities"] = []
        valid_seed_data["organizations"] = []
        valid_seed_data["relationships"] = []
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is True
        assert result["missing_fields"] == []

    def test_extra_fields_are_ignored(self, graph_ltm, valid_seed_data):
        """Test validation passes when extra fields are present."""
        valid_seed_data["extra_field"] = "should be ignored"
        valid_seed_data["another_extra"] = {"nested": "data"}
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is True
        assert result["missing_fields"] == []

    def test_array_field_is_none(self, graph_ltm, valid_seed_data):
        """Test validation fails when array field is None instead of list."""
        valid_seed_data["skills"] = None
        
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        assert result["valid"] is False
        assert "skills" in result["missing_fields"]

    def test_validation_result_structure(self, graph_ltm, valid_seed_data):
        """Test validation result always has correct structure."""
        result = graph_ltm._validate_seed_schema(valid_seed_data)
        
        # Check result has required keys
        assert "valid" in result
        assert "missing_fields" in result
        
        # Check types
        assert isinstance(result["valid"], bool)
        assert isinstance(result["missing_fields"], list)

    def test_validation_result_structure_on_error(self, graph_ltm):
        """Test validation result has correct structure even on validation failure."""
        invalid_data = {"person": "not a dict"}
        
        result = graph_ltm._validate_seed_schema(invalid_data)
        
        # Check result has required keys
        assert "valid" in result
        assert "missing_fields" in result
        
        # Check types
        assert isinstance(result["valid"], bool)
        assert isinstance(result["missing_fields"], list)
        
        # Check values
        assert result["valid"] is False
        assert len(result["missing_fields"]) > 0
