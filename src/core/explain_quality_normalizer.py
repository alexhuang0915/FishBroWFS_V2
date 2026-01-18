"""
Explain Quality Normalizer - v2.4 Explain Quality & Content Evolution

Deterministic service that adjusts explanation tone for different personas
while preserving semantic meaning. Ensures explanations don't leak wrong tone
or exceed verbosity expectations.

NON-NEGOTIABLE CONSTITUTION:
- Pure function: same input → same output (deterministic)
- Preserves semantic meaning (doesn't change facts)
- No external dependencies (no LLMs, no APIs)
- Must be fast (< 1ms per normalization)
- Must be testable with semantic snapshots
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from contracts.research.explain_persona import ExplainPersona
from contracts.research.explain_persona_tone import (
    PersonaToneRule,
    get_persona_tone_rule,
    validate_explanation_tone,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizationResult:
    """Result of quality normalization."""
    original_text: str
    normalized_text: str
    persona: ExplainPersona
    applied_transformations: List[str]
    validation_issues: List[str]
    
    @property
    def is_valid(self) -> bool:
        """Check if normalized text passes tone validation."""
        return len(self.validation_issues) == 0
    
    @property
    def was_changed(self) -> bool:
        """Check if normalization changed the text."""
        return self.original_text != self.normalized_text


class ExplainQualityNormalizer:
    """
    Deterministic quality normalizer for persona-specific explanations.
    
    Applies tone adjustments to make explanations appropriate for target persona
    while preserving semantic meaning.
    """
    
    def __init__(self):
        """Initialize quality normalizer."""
        # Compile regex patterns for efficiency
        self._technical_jargon_patterns = [
            re.compile(r'\b(?:TODO|FIXME|HACK|kludge|workaround)\b', re.IGNORECASE),
            re.compile(r'\b(?:implementation detail|code smell|technical debt)\b', re.IGNORECASE),
            re.compile(r'\b(?:stack trace|debug trace|error log)\b', re.IGNORECASE),
        ]
        
        self._business_jargon_patterns = [
            re.compile(r'\b(?:ROI|business value|stakeholder|executive summary)\b', re.IGNORECASE),
            re.compile(r'\b(?:high-level|simplified|dumbed down)\b', re.IGNORECASE),
        ]
        
        self._sentence_split_pattern = re.compile(r'[.!?]+')
        
    def normalize_for_persona(
        self,
        text: str,
        target_persona: ExplainPersona,
        source_persona: Optional[ExplainPersona] = None,
        enforce_length: bool = True,
    ) -> NormalizationResult:
        """
        Normalize explanation text for target persona.
        
        Args:
            text: Original explanation text
            target_persona: Persona to normalize for
            source_persona: Optional source persona (for context-aware normalization)
            enforce_length: Whether to enforce length constraints
            
        Returns:
            NormalizationResult with normalized text and metadata
        """
        if not text or not text.strip():
            return NormalizationResult(
                original_text=text,
                normalized_text=text,
                persona=target_persona,
                applied_transformations=[],
                validation_issues=["Empty text"],
            )
        
        applied_transformations = []
        normalized = text
        
        # Get tone rules for target persona
        target_rule = get_persona_tone_rule(target_persona)
        
        # Step 1: Remove persona-specific markers if present
        normalized, marker_transforms = self._remove_persona_markers(normalized)
        applied_transformations.extend(marker_transforms)
        
        # Step 2: Adjust technical/business jargon based on target persona
        if target_persona in [ExplainPersona.EXEC, ExplainPersona.PM]:
            # Reduce technical jargon for business personas
            normalized, tech_transforms = self._reduce_technical_jargon(normalized)
            applied_transformations.extend(tech_transforms)
        
        if target_persona in [ExplainPersona.ENGINEER, ExplainPersona.QA]:
            # Reduce business jargon for technical personas
            normalized, biz_transforms = self._reduce_business_jargon(normalized)
            applied_transformations.extend(biz_transforms)
        
        # Step 3: Adjust sentence length if needed
        if enforce_length:
            normalized, length_transforms = self._adjust_sentence_length(
                normalized, target_rule
            )
            applied_transformations.extend(length_transforms)
        
        # Step 4: Ensure paragraph structure
        normalized, para_transforms = self._adjust_paragraph_structure(
            normalized, target_rule
        )
        applied_transformations.extend(para_transforms)
        
        # Step 5: Validate against tone rules
        validation_issues = validate_explanation_tone(
            normalized,
            target_persona,
            check_length=enforce_length,
            check_terms=True,
        )
        
        # Create result
        result = NormalizationResult(
            original_text=text,
            normalized_text=normalized,
            persona=target_persona,
            applied_transformations=applied_transformations,
            validation_issues=validation_issues,
        )
        
        logger.debug(
            f"Normalized text for {target_persona.value}: "
            f"{len(applied_transformations)} transformations, "
            f"{len(validation_issues)} validation issues"
        )
        
        return result
    
    def _remove_persona_markers(self, text: str) -> Tuple[str, List[str]]:
        """
        Remove persona-specific markers from text.
        
        Example: "[ENGINEER: Review error stack trace]" → ""
        
        Returns:
            Tuple of (cleaned_text, transformations)
        """
        transformations = []
        
        # Pattern for persona markers like [ENGINEER: ...]
        pattern = r'\[(?:TRADER|ENGINEER|QA|PM|EXEC):[^\]]*\]'
        cleaned = re.sub(pattern, '', text)
        
        # Check if any markers were removed
        if cleaned != text:
            transformations.append("Removed persona-specific markers")
        
        # Remove extra spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned, transformations
    
    def _reduce_technical_jargon(self, text: str) -> Tuple[str, List[str]]:
        """
        Reduce technical jargon for business personas.
        
        Replaces technical terms with simpler equivalents where possible.
        """
        transformations = []
        normalized = text
        
        # Technical term replacements (simplified mapping)
        technical_replacements = {
            r'\bstack trace\b': 'error details',
            r'\bdebug trace\b': 'troubleshooting details',
            r'\berror log\b': 'error record',
            r'\bimplementation detail\b': 'system detail',
            r'\bcode smell\b': 'code issue',
            r'\btechnical debt\b': 'system improvement needed',
            r'\bTODO\b': 'action needed',
            r'\bFIXME\b': 'requires fixing',
            r'\bHACK\b': 'temporary solution',
        }
        
        for pattern_str, replacement in technical_replacements.items():
            pattern = re.compile(pattern_str, re.IGNORECASE)
            if pattern.search(normalized):
                normalized = pattern.sub(replacement, normalized)
                transformations.append(f"Replaced technical term: {pattern_str} → {replacement}")
        
        return normalized, transformations
    
    def _reduce_business_jargon(self, text: str) -> Tuple[str, List[str]]:
        """
        Reduce business jargon for technical personas.
        
        Replaces business terms with more precise technical equivalents.
        """
        transformations = []
        normalized = text
        
        # Business term replacements
        business_replacements = {
            r'\bROI\b': 'return on investment',
            r'\bbusiness value\b': 'system value',
            r'\bstakeholder\b': 'user',
            r'\bexecutive summary\b': 'summary',
            r'\bhigh-level\b': 'overview',
            r'\bsimplified\b': 'basic',
        }
        
        for pattern_str, replacement in business_replacements.items():
            pattern = re.compile(pattern_str, re.IGNORECASE)
            if pattern.search(normalized):
                normalized = pattern.sub(replacement, normalized)
                transformations.append(f"Replaced business term: {pattern_str} → {replacement}")
        
        return normalized, transformations
    
    def _adjust_sentence_length(
        self, text: str, rule: PersonaToneRule
    ) -> Tuple[str, List[str]]:
        """
        Adjust sentence length to fit within persona constraints.
        
        Splits long sentences and combines short sentences where appropriate.
        """
        transformations = []
        normalized = text
        
        # Split into sentences
        sentences = [s.strip() for s in self._sentence_split_pattern.split(text) if s.strip()]
        
        if not sentences:
            return normalized, transformations
        
        adjusted_sentences = []
        
        for i, sentence in enumerate(sentences):
            current_len = len(sentence)
            
            # Check if sentence is too long
            if current_len > rule.max_sentence_length:
                # Simple split: split on conjunctions or commas
                parts = self._split_long_sentence(sentence, rule.max_sentence_length)
                adjusted_sentences.extend(parts)
                transformations.append(
                    f"Sentence {i+1} split ({current_len} > {rule.max_sentence_length}): "
                    f"{len(parts)} parts created"
                )
            # Check if sentence is too short (and can be combined with next)
            elif (current_len < rule.min_sentence_length and 
                  i < len(sentences) - 1 and
                  len(sentences[i+1]) < rule.max_sentence_length):
                # Combine with next sentence
                combined = f"{sentence}. {sentences[i+1]}"
                if len(combined) <= rule.max_sentence_length:
                    adjusted_sentences.append(combined)
                    # Skip next sentence since we combined it
                    sentences[i+1] = ""
                    transformations.append(
                        f"Sentences {i+1}-{i+2} combined "
                        f"({current_len} + {len(sentences[i+1])} < {rule.min_sentence_length})"
                    )
                else:
                    adjusted_sentences.append(sentence)
            else:
                adjusted_sentences.append(sentence)
        
        # Reconstruct text
        normalized = ". ".join(adjusted_sentences)
        if normalized and not normalized.endswith('.'):
            normalized += '.'
        
        return normalized, transformations
    
    def _split_long_sentence(self, sentence: str, max_length: int) -> List[str]:
        """
        Split a long sentence into shorter parts.
        
        Uses simple heuristics: split on conjunctions, commas, or clauses.
        """
        if len(sentence) <= max_length:
            return [sentence]
        
        # Try to split on common conjunctions
        split_points = [' and ', ' but ', ' or ', ' however ', ' therefore ', ' because ']
        
        for splitter in split_points:
            if splitter in sentence.lower():
                parts = re.split(splitter, sentence, flags=re.IGNORECASE)
                if len(parts) > 1:
                    # Capitalize second part
                    parts = [parts[0]] + [p.strip().capitalize() for p in parts[1:]]
                    return parts
        
        # Try to split on commas
        if ',' in sentence:
            parts = sentence.split(',')
            if len(parts) > 1:
                # Reconstruct with proper capitalization
                result = [parts[0].strip()]
                for part in parts[1:]:
                    if part.strip():
                        result.append(part.strip().capitalize())
                return result
        
        # Last resort: split at approximate midpoint
        midpoint = len(sentence) // 2
        # Find a space near midpoint
        for i in range(midpoint, len(sentence)):
            if sentence[i] == ' ':
                part1 = sentence[:i].strip()
                part2 = sentence[i+1:].strip().capitalize()
                return [part1, part2] if part2 else [part1]
        
        # If no space found, just return as is (will be truncated later)
        return [sentence]
    
    def _adjust_paragraph_structure(
        self, text: str, rule: PersonaToneRule
    ) -> Tuple[str, List[str]]:
        """
        Adjust paragraph structure for persona.
        
        Ensures appropriate number of sentences per paragraph.
        """
        transformations = []
        normalized = text
        
        # Split into sentences
        sentences = [s.strip() for s in self._sentence_split_pattern.split(text) if s.strip()]
        
        if len(sentences) <= rule.max_sentences_per_paragraph:
            return normalized, transformations
        
        # Too many sentences - create multiple paragraphs
        paragraphs = []
        current_paragraph = []
        
        for i, sentence in enumerate(sentences):
            current_paragraph.append(sentence)
            
            # Start new paragraph if we hit max sentences
            if (len(current_paragraph) >= rule.max_sentences_per_paragraph and
                i < len(sentences) - 1):  # Don't break if last sentence
                paragraphs.append(". ".join(current_paragraph) + ".")
                current_paragraph = []
                transformations.append(
                    f"Paragraph break inserted after sentence {i+1} "
                    f"(max {rule.max_sentences_per_paragraph} sentences)"
                )
        
        # Add remaining sentences
        if current_paragraph:
            paragraphs.append(". ".join(current_paragraph) + ".")
        
        normalized = "\n\n".join(paragraphs)
        
        return normalized, transformations
    
    def batch_normalize(
        self,
        texts: List[str],
        target_persona: ExplainPersona,
        source_persona: Optional[ExplainPersona] = None,
    ) -> List[NormalizationResult]:
        """
        Normalize multiple texts for target persona.
        
        Args:
            texts: List of original explanation texts
            target_persona: Persona to normalize for
            source_persona: Optional source persona
            
        Returns:
            List of NormalizationResult objects
        """
        return [
            self.normalize_for_persona(text, target_persona, source_persona)
            for text in texts
        ]
    
    def validate_batch(
        self,
        texts: List[str],
        persona: ExplainPersona,
    ) -> List[List[str]]:
        """
        Validate multiple texts against persona tone rules.
        
        Args:
            texts: List of explanation texts
            persona: Persona to validate against
            
        Returns:
            List of validation issue lists (one per text)
        """
        return [
            validate_explanation_tone(text, persona)
            for text in texts
        ]


# Singleton instance for easy access
_quality_normalizer_singleton: Optional[ExplainQualityNormalizer] = None


def get_quality_normalizer() -> ExplainQualityNormalizer:
    """
    Get singleton quality normalizer instance.
    
    Returns:
        ExplainQualityNormalizer: Singleton instance
    """
    global _quality_normalizer_singleton
    
    if _quality_normalizer_singleton is None:
        _quality_normalizer_singleton = ExplainQualityNormalizer()
    
    return _quality_normalizer_singleton


def normalize_explanation_for_persona(
    text: str,
    target_persona: ExplainPersona,
    source_persona: Optional[ExplainPersona] = None,
) -> NormalizationResult:
    """
    Convenience function to normalize explanation for persona.
    
    Args:
        text: Original explanation text
        target_persona: Persona to normalize for
        source_persona: Optional source persona
        
    Returns:
        NormalizationResult with normalized text
    """
    normalizer = get_quality_normalizer()
    return normalizer.normalize_for_persona(text, target_persona, source_persona)


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "NormalizationResult",
    "ExplainQualityNormalizer",
    "get_quality_normalizer",
    "normalize_explanation_for_persona",
]