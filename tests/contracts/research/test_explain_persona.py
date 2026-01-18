"""
Tests for ExplainPersona contract (v2.3).

Tests persona enum, validation, and utility functions.
"""

import pytest
from contracts.research.explain_persona import (
    ExplainPersona,
    get_default_persona,
    get_persona_display_name,
    get_persona_description,
    get_persona_icon,
    validate_persona,
    get_persona_by_technical_level,
    get_all_personas,
)


class TestExplainPersona:
    """Test ExplainPersona enum and related functions."""
    
    def test_enum_values(self):
        """Test that ExplainPersona enum has expected values."""
        assert ExplainPersona.TRADER == "TRADER"
        assert ExplainPersona.ENGINEER == "ENGINEER"
        assert ExplainPersona.QA == "QA"
        assert ExplainPersona.PM == "PM"
        assert ExplainPersona.EXEC == "EXEC"
        
        # Verify all personas are present
        personas = list(ExplainPersona)
        assert len(personas) == 5
        assert set(p.value for p in personas) == {
            "TRADER", "ENGINEER", "QA", "PM", "EXEC"
        }
    
    def test_get_default_persona(self):
        """Test default persona is TRADER (backward compatibility)."""
        assert get_default_persona() == ExplainPersona.TRADER
    
    def test_get_persona_display_name(self):
        """Test persona display names."""
        assert get_persona_display_name(ExplainPersona.TRADER) == "Trader"
        assert get_persona_display_name(ExplainPersona.ENGINEER) == "Engineer"
        assert get_persona_display_name(ExplainPersona.QA) == "QA"
        assert get_persona_display_name(ExplainPersona.PM) == "Product Manager"
        assert get_persona_display_name(ExplainPersona.EXEC) == "Executive"
    
    def test_get_persona_description(self):
        """Test persona descriptions."""
        descriptions = {
            ExplainPersona.TRADER: "Quantitative trader focused on portfolio decisions",
            ExplainPersona.ENGINEER: "Technical specialist focused on system implementation",
            ExplainPersona.QA: "Quality assurance focused on validation and testing",
            ExplainPersona.PM: "Product focus on business value and user impact",
            ExplainPersona.EXEC: "Strategic focus on high-level impact and decisions",
        }
        
        for persona, expected_desc in descriptions.items():
            assert get_persona_description(persona) == expected_desc
    
    def test_get_persona_icon(self):
        """Test persona icons."""
        icons = {
            ExplainPersona.TRADER: "📈",
            ExplainPersona.ENGINEER: "⚙️",
            ExplainPersona.QA: "✅",
            ExplainPersona.PM: "📊",
            ExplainPersona.EXEC: "👔",
        }
        
        for persona, expected_icon in icons.items():
            assert get_persona_icon(persona) == expected_icon
    
    def test_validate_persona(self):
        """Test persona validation."""
        # Valid personas (case-insensitive)
        assert validate_persona("trader") == ExplainPersona.TRADER
        assert validate_persona("TRADER") == ExplainPersona.TRADER
        assert validate_persona("engineer") == ExplainPersona.ENGINEER
        assert validate_persona("qa") == ExplainPersona.QA
        assert validate_persona("pm") == ExplainPersona.PM
        assert validate_persona("exec") == ExplainPersona.EXEC
        
        # Invalid persona
        with pytest.raises(ValueError, match="Invalid persona: 'invalid'.*"):
            validate_persona("invalid")
    
    def test_get_persona_by_technical_level(self):
        """Test filtering personas by technical level."""
        # All personas
        all_personas = get_persona_by_technical_level("all")
        assert len(all_personas) == 5
        
        # Low technical level (EXEC only)
        low_personas = get_persona_by_technical_level("low")
        assert low_personas == [ExplainPersona.EXEC]
        
        # Low-medium (PM and EXEC)
        low_medium_personas = get_persona_by_technical_level("low_medium")
        assert set(low_medium_personas) == {ExplainPersona.PM, ExplainPersona.EXEC}
        
        # Medium (TRADER)
        medium_personas = get_persona_by_technical_level("medium")
        assert medium_personas == [ExplainPersona.TRADER]
        
        # Medium-high (QA)
        medium_high_personas = get_persona_by_technical_level("medium_high")
        assert medium_high_personas == [ExplainPersona.QA]
        
        # High (ENGINEER)
        high_personas = get_persona_by_technical_level("high")
        assert high_personas == [ExplainPersona.ENGINEER]
        
        # Unknown level returns empty list
        unknown_personas = get_persona_by_technical_level("unknown")
        assert unknown_personas == []
    
    def test_get_all_personas(self):
        """Test getting all personas."""
        personas = get_all_personas()
        assert len(personas) == 5
        assert set(personas) == set(ExplainPersona)
    
    def test_persona_metadata_completeness(self):
        """Test that all personas have complete metadata."""
        from contracts.research.explain_persona import PERSONA_METADATA
        
        for persona in ExplainPersona:
            metadata = PERSONA_METADATA[persona]
            assert "display_name" in metadata
            assert "description" in metadata
            assert "icon" in metadata
            assert metadata["display_name"]  # Not empty
            assert metadata["description"]  # Not empty
            assert metadata["icon"]  # Not empty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])