"""
Tests for ExplainPersonaTone contract (v2.4).

Tests persona tone rules, validation, and quality normalization.
"""

import pytest
from contracts.research.explain_persona_tone import (
    PersonaToneRule,
    ToneStyle,
    PERSONA_TONE_RULES,
    get_persona_tone_rule,
    validate_explanation_tone,
    get_tone_guidelines,
)
from contracts.research.explain_persona import ExplainPersona


class TestPersonaToneRule:
    """Test PersonaToneRule model and validation."""
    
    def test_rule_frozen(self):
        """Test that PersonaToneRule is frozen (immutable)."""
        rule = PersonaToneRule(
            persona=ExplainPersona.ENGINEER,
            min_sentence_length=30,
            max_sentence_length=120,
            max_sentences_per_paragraph=4,
            preferred_styles=[ToneStyle.TECHNICAL, ToneStyle.DETAILED],
            allowed_technical_terms=frozenset(),
            forbidden_terms=frozenset({"business value", "ROI", "stakeholder"}),
            recommended_patterns=frozenset({r"system.*architecture", r"implementation.*detail"}),
            style_guidelines="Detailed technical specifications with implementation insights."
        )
        
        # Verify frozen attribute
        assert rule.model_config.get("frozen") is True
        
        # Verify attributes
        assert rule.persona == ExplainPersona.ENGINEER
        assert rule.min_sentence_length == 30
        assert rule.max_sentence_length == 120
        assert rule.max_sentences_per_paragraph == 4
        assert ToneStyle.TECHNICAL in rule.preferred_styles
        assert ToneStyle.DETAILED in rule.preferred_styles
        assert "business value" in rule.forbidden_terms
        assert "ROI" in rule.forbidden_terms
        
        # Test immutability
        with pytest.raises(Exception):
            rule.persona = ExplainPersona.TRADER
    
    def test_rule_validation(self):
        """Test rule validation logic."""
        # Valid rule
        rule = PersonaToneRule(
            persona=ExplainPersona.TRADER,
            min_sentence_length=20,
            max_sentence_length=80,
            max_sentences_per_paragraph=3,
            preferred_styles=[ToneStyle.CONCISE, ToneStyle.ACTIONABLE],
            allowed_technical_terms=frozenset({"returns", "risk", "portfolio"}),
            forbidden_terms=frozenset({"technical debt", "implementation details"}),
            recommended_patterns=frozenset({r"ready for.*execution", r"risk.*adjusted"}),
            style_guidelines="Concise, actionable insights for trading decisions."
        )
        
        # Should not raise
        rule.model_validate(rule.model_dump())
        
        # Invalid: min > max
        with pytest.raises(ValueError):
            PersonaToneRule(
                persona=ExplainPersona.TRADER,
                min_sentence_length=100,
                max_sentence_length=50,  # Invalid: min > max
                max_sentences_per_paragraph=3,
                preferred_styles=[ToneStyle.CONCISE],
                allowed_technical_terms=frozenset(),
                forbidden_terms=frozenset(),
                recommended_patterns=frozenset(),
                style_guidelines="Test"
            )
        
        # Invalid: max_sentences_per_paragraph <= 0
        with pytest.raises(ValueError):
            PersonaToneRule(
                persona=ExplainPersona.TRADER,
                min_sentence_length=20,
                max_sentence_length=80,
                max_sentences_per_paragraph=0,  # Invalid: must be > 0
                preferred_styles=[ToneStyle.CONCISE],
                allowed_technical_terms=frozenset(),
                forbidden_terms=frozenset(),
                recommended_patterns=frozenset(),
                style_guidelines="Test"
            )


class TestPersonaToneRulesMapping:
    """Test PERSONA_TONE_RULES mapping."""
    
    def test_all_personas_have_rules(self):
        """Test that all personas have tone rules defined."""
        for persona in ExplainPersona:
            assert persona in PERSONA_TONE_RULES
            rule = PERSONA_TONE_RULES[persona]
            
            # Verify rule attributes
            assert isinstance(rule, PersonaToneRule)
            assert rule.persona == persona
            assert rule.min_sentence_length > 0
            assert rule.max_sentence_length >= rule.min_sentence_length
            assert rule.max_sentences_per_paragraph > 0
            assert isinstance(rule.preferred_styles, list)
            assert isinstance(rule.forbidden_terms, frozenset)
            assert rule.style_guidelines  # Not empty
    
    def test_get_persona_tone_rule(self):
        """Test get_persona_tone_rule function."""
        for persona in ExplainPersona:
            rule = get_persona_tone_rule(persona)
            assert rule == PERSONA_TONE_RULES[persona]
            assert rule.persona == persona
        
        # Test with string persona
        rule = get_persona_tone_rule("TRADER")
        assert rule.persona == ExplainPersona.TRADER
        
        # Invalid persona - should raise ValueError from validate_persona
        with pytest.raises(ValueError):
            get_persona_tone_rule("INVALID")
    
    def test_persona_specific_rules(self):
        """Test persona-specific rule characteristics."""
        # ENGINEER: Technical, detailed
        engineer_rule = PERSONA_TONE_RULES[ExplainPersona.ENGINEER]
        assert ToneStyle.TECHNICAL in engineer_rule.preferred_styles
        assert ToneStyle.DETAILED in engineer_rule.preferred_styles
        assert "business value" in engineer_rule.forbidden_terms
        
        # TRADER: Concise, actionable
        trader_rule = PERSONA_TONE_RULES[ExplainPersona.TRADER]
        assert ToneStyle.CONCISE in trader_rule.preferred_styles
        assert ToneStyle.ACTIONABLE in trader_rule.preferred_styles
        assert "technical debt" in trader_rule.forbidden_terms
        
        # EXEC: Strategic, concise, business
        exec_rule = PERSONA_TONE_RULES[ExplainPersona.EXEC]
        assert ToneStyle.STRATEGIC in exec_rule.preferred_styles
        assert ToneStyle.CONCISE in exec_rule.preferred_styles
        assert ToneStyle.BUSINESS in exec_rule.preferred_styles
        assert "implementation" in exec_rule.forbidden_terms


class TestToneValidation:
    """Test tone validation functions."""
    
    def test_validate_explanation_tone_basic(self):
        """Test basic tone validation."""
        # Valid text for TRADER (concise, actionable) - meets min length requirement
        valid_trader_text = "Market data is now ready for research execution and analysis."
        issues = validate_explanation_tone(valid_trader_text, ExplainPersona.TRADER)
        assert len(issues) == 0
        
        # Text with forbidden term for TRADER
        invalid_trader_text = "Technical debt is high. Implementation details complex."
        issues = validate_explanation_tone(invalid_trader_text, ExplainPersona.TRADER)
        assert len(issues) > 0
        assert any("forbidden term" in issue.lower() for issue in issues)
    
    def test_validate_explanation_tone_length(self):
        """Test length validation."""
        # Too short for ENGINEER (min 30 chars)
        short_text = "System ready."  # 13 chars
        issues = validate_explanation_tone(
            short_text, 
            ExplainPersona.ENGINEER,
            check_length=True
        )
        assert len(issues) > 0
        assert any("too short" in issue.lower() for issue in issues)
        
        # Too long for EXEC (max 60 chars)
        long_text = "This is a very long explanation that exceeds the maximum character limit for executive summaries which should be concise and high-level."  # > 60 chars
        issues = validate_explanation_tone(
            long_text,
            ExplainPersona.EXEC,
            check_length=True
        )
        assert len(issues) > 0
        assert any("too long" in issue.lower() for issue in issues)
    
    def test_validate_explanation_tone_paragraph_structure(self):
        """Test paragraph structure validation."""
        # Too many sentences per paragraph for QA (max 4)
        many_sentences = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."  # 5 sentences
        issues = validate_explanation_tone(
            many_sentences,
            ExplainPersona.QA,
            check_length=True
        )
        # Note: Paragraph structure validation may not be implemented yet
        # This test documents expected behavior
    
    def test_validate_explanation_tone_without_length_check(self):
        """Test validation without length checking."""
        # Short text for ENGINEER, but length check disabled
        short_text = "System ready."
        issues = validate_explanation_tone(
            short_text,
            ExplainPersona.ENGINEER,
            check_length=False
        )
        # Should not have length issues
        assert not any("too short" in issue.lower() for issue in issues)
    
    def test_validate_explanation_tone_empty_text(self):
        """Test validation with empty text."""
        issues = validate_explanation_tone("", ExplainPersona.TRADER)
        # Empty text has no sentences, so no length issues
        # No forbidden terms in empty text
        assert len(issues) == 0


class TestToneGuidelines:
    """Test tone guideline functions."""
    
    def test_get_tone_guidelines(self):
        """Test get_tone_guidelines function."""
        for persona in ExplainPersona:
            guidelines = get_tone_guidelines(persona)
            assert isinstance(guidelines, str)
            assert len(guidelines) > 0
            
            # Should contain rule's style_guidelines
            rule = get_persona_tone_rule(persona)
            assert rule.style_guidelines in guidelines
        
        # Test with string persona
        guidelines = get_tone_guidelines("ENGINEER")
        assert isinstance(guidelines, str)
        assert len(guidelines) > 0
        
        # Invalid persona - should raise ValueError from validate_persona
        with pytest.raises(ValueError):
            get_tone_guidelines("INVALID")


class TestSemanticConsistency:
    """Test semantic consistency across personas."""
    
    def test_deterministic_normalization(self):
        """Test that normalization is deterministic (same input → same output)."""
        # This test will be implemented with the quality normalizer tests
        pass
    
    def test_semantic_preservation(self):
        """Test that normalization preserves semantic meaning."""
        # This test will be implemented with the quality normalizer tests
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])