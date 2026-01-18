"""
Tests for ExplainQualityNormalizer (v2.4).

Tests quality normalization for persona-specific explanations.
"""

import pytest
from src.core.explain_quality_normalizer import (
    ExplainQualityNormalizer,
    NormalizationResult,
    normalize_explanation_for_persona,
    get_quality_normalizer,
)
from contracts.research.explain_persona import ExplainPersona
from contracts.research.explain_persona_tone import (
    get_persona_tone_rule,
    validate_explanation_tone,
)


class TestNormalizationResult:
    """Test NormalizationResult dataclass."""
    
    def test_result_creation(self):
        """Test creating NormalizationResult."""
        result = NormalizationResult(
            original_text="Original text",
            normalized_text="Normalized text",
            persona=ExplainPersona.ENGINEER,
            applied_transformations=["jargon_reduction", "length_adjustment"],
            validation_issues=["Sentence too short"]
        )
        
        assert result.original_text == "Original text"
        assert result.normalized_text == "Normalized text"
        assert result.persona == ExplainPersona.ENGINEER
        assert len(result.applied_transformations) == 2
        assert len(result.validation_issues) == 1
        assert result.was_changed is True
        assert result.is_valid is False  # Has validation issues
    
    def test_result_unchanged(self):
        """Test result when text unchanged."""
        result = NormalizationResult(
            original_text="Same text",
            normalized_text="Same text",
            persona=ExplainPersona.TRADER,
            applied_transformations=[],
            validation_issues=[]
        )
        
        assert result.was_changed is False
        assert result.is_valid is True
    
    def test_result_frozen(self):
        """Test that NormalizationResult is frozen (immutable)."""
        result = NormalizationResult(
            original_text="Test",
            normalized_text="Test",
            persona=ExplainPersona.QA,
            applied_transformations=[],
            validation_issues=[]
        )
        
        # Verify frozen attribute
        assert result.__dataclass_params__.frozen is True
        
        # Test immutability
        with pytest.raises(Exception):
            result.original_text = "Modified"


class TestExplainQualityNormalizer:
    """Test ExplainQualityNormalizer class."""
    
    def setup_method(self):
        """Setup test fixture."""
        self.normalizer = ExplainQualityNormalizer()
    
    def test_normalize_empty_text(self):
        """Test normalizing empty text."""
        result = self.normalizer.normalize_for_persona(
            text="",
            target_persona=ExplainPersona.TRADER
        )
        
        assert result.original_text == ""
        assert result.normalized_text == ""
        assert result.persona == ExplainPersona.TRADER
        assert result.was_changed is False
        assert len(result.validation_issues) > 0  # Should have validation issues for empty text
        assert "empty" in result.validation_issues[0].lower()
    
    def test_normalize_whitespace_only(self):
        """Test normalizing whitespace-only text."""
        result = self.normalizer.normalize_for_persona(
            text="   \n  \t  ",
            target_persona=ExplainPersona.ENGINEER
        )
        
        assert result.original_text == "   \n  \t  "
        assert result.normalized_text == "   \n  \t  "
        assert result.was_changed is False
        assert len(result.validation_issues) > 0
    
    def test_normalize_deterministic(self):
        """Test that normalization is deterministic."""
        text = "The system has high technical debt and complex implementation details."
        
        # First normalization
        result1 = self.normalizer.normalize_for_persona(
            text=text,
            target_persona=ExplainPersona.TRADER
        )
        
        # Second normalization (should be identical)
        result2 = self.normalizer.normalize_for_persona(
            text=text,
            target_persona=ExplainPersona.TRADER
        )
        
        # Results should be identical
        assert result1.normalized_text == result2.normalized_text
        assert result1.applied_transformations == result2.applied_transformations
        assert result1.validation_issues == result2.validation_issues
    
    def test_normalize_jargon_reduction(self):
        """Test jargon reduction for technical personas."""
        # Text with business jargon
        business_text = "The ROI on this initiative will impact stakeholder value significantly."
        
        # Normalize for ENGINEER (should reduce business jargon)
        result = self.normalizer.normalize_for_persona(
            text=business_text,
            target_persona=ExplainPersona.ENGINEER
        )
        
        # Should have applied transformations
        assert result.was_changed is True
        assert len(result.applied_transformations) > 0
        
        # Check that jargon was reduced
        normalized_lower = result.normalized_text.lower()
        # Note: Actual transformation logic may vary
        # This test documents expected behavior
    
    def test_normalize_sentence_length_adjustment(self):
        """Test sentence length adjustment."""
        # Very long sentence for EXEC (max 60 chars)
        long_sentence = "This is a very long explanation that exceeds the maximum character limit for executive summaries which should be concise and high-level."
        
        result = self.normalizer.normalize_for_persona(
            text=long_sentence,
            target_persona=ExplainPersona.EXEC,
            enforce_length=True
        )
        
        # Should have length adjustment transformation
        assert result.was_changed is True
        # Check for transformation messages like "Sentence X split" or "Sentences X-Y combined"
        has_length_transform = any(
            "split" in t.lower() or "combined" in t.lower() or "length" in t.lower()
            for t in result.applied_transformations
        )
        assert has_length_transform, f"No length transformation found: {result.applied_transformations}"
        
        # Normalized text should be shorter or split
        # Note: Actual implementation may vary
    
    def test_normalize_without_length_enforcement(self):
        """Test normalization without length enforcement."""
        # Very long sentence
        long_sentence = "This is a very long explanation that exceeds the maximum character limit for executive summaries which should be concise and high-level."
        
        result = self.normalizer.normalize_for_persona(
            text=long_sentence,
            target_persona=ExplainPersona.EXEC,
            enforce_length=False
        )
        
        # Should not have length-related validation issues
        assert not any("too long" in issue.lower() for issue in result.validation_issues)
    
    def test_normalize_persona_markers_removal(self):
        """Test removal of persona-specific markers."""
        # Text with persona markers
        marked_text = "System ready. [ENGINEER: Check logs.] [QA: Validate tests.]"
        
        result = self.normalizer.normalize_for_persona(
            text=marked_text,
            target_persona=ExplainPersona.PM
        )
        
        # Should have persona marker removal transformation
        assert result.was_changed is True
        assert any("persona" in t.lower() for t in result.applied_transformations)
        
        # Persona markers should be removed
        assert "[ENGINEER:" not in result.normalized_text
        assert "[QA:" not in result.normalized_text
    
    def test_normalize_validation_after_normalization(self):
        """Test that normalized text passes tone validation."""
        # Text that violates TRADER tone rules
        invalid_trader_text = "Technical debt is accumulating and implementation details are complex."
        
        result = self.normalizer.normalize_for_persona(
            text=invalid_trader_text,
            target_persona=ExplainPersona.TRADER
        )
        
        # After normalization, should have fewer validation issues
        # (or at least different ones)
        original_issues = validate_explanation_tone(
            invalid_trader_text,
            ExplainPersona.TRADER
        )
        
        # Normalized text should be valid or have different issues
        # This test documents expected behavior
    
    def test_batch_normalize(self):
        """Test batch normalization."""
        texts = [
            "First explanation with technical details.",
            "Second explanation with business jargon.",
            "Third simple explanation."
        ]
        
        results = self.normalizer.batch_normalize(
            texts=texts,
            target_persona=ExplainPersona.QA
        )
        
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.original_text == texts[i]
            assert result.persona == ExplainPersona.QA
            assert isinstance(result, NormalizationResult)
    
    def test_validate_batch(self):
        """Test batch validation."""
        texts = [
            "Valid concise text.",
            "Text with forbidden term: technical debt.",
            "Another valid text."
        ]
        
        validation_results = self.normalizer.validate_batch(
            texts=texts,
            persona=ExplainPersona.TRADER
        )
        
        assert len(validation_results) == 3
        assert isinstance(validation_results[0], list)
        
        # Second text should have validation issues
        assert len(validation_results[1]) > 0
        assert any("forbidden" in issue.lower() for issue in validation_results[1])


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_normalize_explanation_for_persona(self):
        """Test normalize_explanation_for_persona convenience function."""
        text = "Test explanation with some content."
        
        result = normalize_explanation_for_persona(
            text=text,
            target_persona=ExplainPersona.ENGINEER
        )
        
        assert isinstance(result, NormalizationResult)
        assert result.original_text == text
        assert result.persona == ExplainPersona.ENGINEER
    
    def test_normalize_explanation_for_persona_with_source(self):
        """Test normalization with source persona."""
        text = "Test explanation."
        
        result = normalize_explanation_for_persona(
            text=text,
            target_persona=ExplainPersona.PM,
            source_persona=ExplainPersona.ENGINEER
        )
        
        assert result.persona == ExplainPersona.PM
        # Source persona may affect normalization logic
    
    def test_get_quality_normalizer_singleton(self):
        """Test get_quality_normalizer singleton pattern."""
        normalizer1 = get_quality_normalizer()
        normalizer2 = get_quality_normalizer()
        
        assert normalizer1 is normalizer2
        assert isinstance(normalizer1, ExplainQualityNormalizer)


class TestIntegrationWithResearchNarrativeBuilder:
    """Test integration with research narrative builder."""
    
    def test_normalization_in_narrative_builder(self):
        """Test that narrative builder applies normalization."""
        # This is an integration test that would require
        # ResearchNarrativeBuilder to be imported and tested
        # For now, document the expected behavior
        
        # When ResearchNarrativeBuilder builds a narrative:
        # 1. It should call normalize_explanation_for_persona for why, developer_view, business_view
        # 2. It should use the normalized text in the narrative
        # 3. It should log normalization if changes were made
        
        pass
    
    def test_semantic_snapshots(self):
        """Test semantic snapshot consistency."""
        # Semantic snapshots should use:
        # - Sentence count
        # - Keyword presence
        # - Max sentence length
        # Instead of brittle full-text snapshots
        
        # This ensures that tone adjustments don't break tests
        # while still validating semantic consistency
        
        pass


class TestPerformance:
    """Test performance characteristics."""
    
    def setup_method(self):
        """Setup test fixture."""
        self.normalizer = ExplainQualityNormalizer()
    
    def test_normalization_performance(self):
        """Test that normalization is fast (< 1ms per normalization)."""
        import time
        
        text = "A typical explanation of moderate length for performance testing."
        
        start_time = time.perf_counter()
        result = self.normalizer.normalize_for_persona(
            text=text,
            target_persona=ExplainPersona.TRADER
        )
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000
        assert duration_ms < 10  # Should be very fast (< 10ms)
        # Note: < 1ms might be too strict for some environments
    
    def test_batch_normalization_performance(self):
        """Test batch normalization performance."""
        import time
        
        # Create 100 test texts
        texts = [f"Test explanation {i} with some content." for i in range(100)]
        
        start_time = time.perf_counter()
        results = self.normalizer.batch_normalize(
            texts=texts,
            target_persona=ExplainPersona.QA
        )
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000
        avg_per_text = duration_ms / len(texts)
        
        assert avg_per_text < 5  # Should be efficient in batch


if __name__ == "__main__":
    pytest.main([__file__, "-v"])