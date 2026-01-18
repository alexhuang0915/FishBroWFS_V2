"""
ExplainPersonaTone Contract - v2.4 Explain Quality & Content Evolution

Frozen SSOT mapping defining persona-specific tone, style, and quality rules.
This contract ensures explanations maintain consistent quality across personas.

NON-NEGOTIABLE CONSTITUTION:
- This is a FROZEN contract (ConfigDict(frozen=True))
- Rules are deterministic and testable
- No runtime modifications allowed
- Must be imported by quality normalizer and consistency tests
"""

from typing import Dict, List, TypedDict, FrozenSet
from pydantic import ConfigDict, BaseModel, field_validator
from enum import Enum

from .explain_persona import ExplainPersona


class ToneStyle(str, Enum):
    """Tone style categories for persona content."""
    TECHNICAL = "technical"
    BUSINESS = "business"
    CONCISE = "concise"
    DETAILED = "detailed"
    ACTIONABLE = "actionable"
    STRATEGIC = "strategic"


class PersonaToneRule(BaseModel):
    """
    Frozen tone rule for a specific persona.
    
    These rules define the expected characteristics of explanations
    for each persona, ensuring consistent quality and appropriateness.
    """
    model_config = ConfigDict(frozen=True)
    
    # Persona this rule applies to
    persona: ExplainPersona
    
    # Target sentence length range (in characters)
    min_sentence_length: int
    max_sentence_length: int
    
    # Target paragraph length (max sentences per paragraph)
    max_sentences_per_paragraph: int
    
    # Preferred tone styles (ordered by priority)
    preferred_styles: List[ToneStyle]
    
    # Allowed technical terms (if empty, all allowed)
    allowed_technical_terms: FrozenSet[str]
    
    # Forbidden terms (should never appear for this persona)
    forbidden_terms: FrozenSet[str]
    
    # Recommended vocabulary patterns (regex patterns)
    recommended_patterns: FrozenSet[str]
    
    # Style guidelines (human-readable)
    style_guidelines: str
    
    @field_validator('max_sentence_length')
    @classmethod
    def validate_sentence_length_range(cls, v, info):
        """Validate that max_sentence_length >= min_sentence_length."""
        if 'min_sentence_length' in info.data:
            min_length = info.data['min_sentence_length']
            if v < min_length:
                raise ValueError(
                    f"max_sentence_length ({v}) must be >= min_sentence_length ({min_length})"
                )
        return v
    
    @field_validator('max_sentences_per_paragraph')
    @classmethod
    def validate_max_sentences(cls, v):
        """Validate that max_sentences_per_paragraph > 0."""
        if v <= 0:
            raise ValueError(f"max_sentences_per_paragraph ({v}) must be > 0")
        return v


# ============================================================================
# Persona Tone Rules (Frozen SSOT)
# ============================================================================

PERSONA_TONE_RULES: Dict[ExplainPersona, PersonaToneRule] = {
    ExplainPersona.TRADER: PersonaToneRule(
        persona=ExplainPersona.TRADER,
        min_sentence_length=20,
        max_sentence_length=80,
        max_sentences_per_paragraph=3,
        preferred_styles=[
            ToneStyle.CONCISE,
            ToneStyle.ACTIONABLE,
            ToneStyle.BUSINESS,
        ],
        allowed_technical_terms=frozenset({
            "returns", "risk", "portfolio", "allocation", "signals",
            "execution", "drawdown", "sharpe", "alpha", "beta",
            "correlation", "volatility", "liquidity",
        }),
        forbidden_terms=frozenset({
            "TODO", "FIXME", "HACK", "kludge", "workaround",
            "implementation detail", "code smell", "technical debt",
        }),
        recommended_patterns=frozenset({
            r"ready for.*execution",
            r"risk.*adjusted",
            r"portfolio.*construction",
            r"signal.*generation",
            r"market.*conditions",
        }),
        style_guidelines=(
            "Concise, actionable insights with clear trade implications. "
            "Focus on risk-adjusted returns and portfolio construction. "
            "Avoid deep technical implementation details."
        ),
    ),
    
    ExplainPersona.ENGINEER: PersonaToneRule(
        persona=ExplainPersona.ENGINEER,
        min_sentence_length=30,
        max_sentence_length=120,
        max_sentences_per_paragraph=4,
        preferred_styles=[
            ToneStyle.TECHNICAL,
            ToneStyle.DETAILED,
            ToneStyle.ACTIONABLE,
        ],
        allowed_technical_terms=frozenset(),  # All technical terms allowed
        forbidden_terms=frozenset({
            "business value", "ROI", "stakeholder", "executive summary",
            "high-level", "simplified", "dumbed down",
        }),
        recommended_patterns=frozenset({
            r"system.*architecture",
            r"implementation.*detail",
            r"error.*analysis",
            r"data.*quality",
            r"debug.*trace",
            r"performance.*metrics",
        }),
        style_guidelines=(
            "Detailed technical specifications with implementation insights. "
            "Include error analysis, system architecture, and debugging details. "
            "Use precise technical terminology."
        ),
    ),
    
    ExplainPersona.QA: PersonaToneRule(
        persona=ExplainPersona.QA,
        min_sentence_length=25,
        max_sentence_length=100,
        max_sentences_per_paragraph=3,
        preferred_styles=[
            ToneStyle.DETAILED,
            ToneStyle.TECHNICAL,
            ToneStyle.ACTIONABLE,
        ],
        allowed_technical_terms=frozenset({
            "validation", "testing", "coverage", "reproducibility",
            "quality", "metrics", "gates", "checks", "verification",
            "edge cases", "test scenarios", "acceptance criteria",
        }),
        forbidden_terms=frozenset({
            "assume", "probably", "maybe", "should work",
            "untested", "unverified", "experimental",
        }),
        recommended_patterns=frozenset({
            r"quality.*gate",
            r"test.*coverage",
            r"validation.*procedure",
            r"reproducibility.*check",
            r"edge.*case",
            r"acceptance.*criteria",
        }),
        style_guidelines=(
            "Focus on validation procedures, test coverage, and quality metrics. "
            "Be precise about verification steps and edge cases. "
            "Avoid ambiguous language about test status."
        ),
    ),
    
    ExplainPersona.PM: PersonaToneRule(
        persona=ExplainPersona.PM,
        min_sentence_length=25,
        max_sentence_length=90,
        max_sentences_per_paragraph=2,
        preferred_styles=[
            ToneStyle.BUSINESS,
            ToneStyle.STRATEGIC,
            ToneStyle.CONCISE,
        ],
        allowed_technical_terms=frozenset({
            "feature", "timeline", "roadmap", "priority", "ROI",
            "user impact", "business value", "delivery", "milestone",
        }),
        forbidden_terms=frozenset({
            "stack trace", "code review", "implementation detail",
            "technical debt", "debugging", "low-level",
        }),
        recommended_patterns=frozenset({
            r"business.*value",
            r"user.*impact",
            r"ROI.*analysis",
            r"feature.*priority",
            r"delivery.*timeline",
            r"roadmap.*alignment",
        }),
        style_guidelines=(
            "Business-focused explanations with clear user impact and ROI analysis. "
            "Connect technical outcomes to business value and feature prioritization. "
            "Avoid deep technical implementation details."
        ),
    ),
    
    ExplainPersona.EXEC: PersonaToneRule(
        persona=ExplainPersona.EXEC,
        min_sentence_length=15,
        max_sentence_length=60,
        max_sentences_per_paragraph=1,
        preferred_styles=[
            ToneStyle.STRATEGIC,
            ToneStyle.CONCISE,
            ToneStyle.BUSINESS,
        ],
        allowed_technical_terms=frozenset({
            "strategy", "financial", "risk", "summary", "impact",
            "decision", "allocation", "performance", "outcome",
        }),
        forbidden_terms=frozenset({
            "implementation", "technical", "code", "debug",
            "detailed analysis", "parameter tuning", "configuration",
        }),
        recommended_patterns=frozenset({
            r"strategic.*impact",
            r"financial.*implication",
            r"risk.*management",
            r"high.*level.*summary",
            r"key.*metric",
            r"decision.*point",
        }),
        style_guidelines=(
            "High-level strategic summaries with financial implications. "
            "Focus on key metrics, risk management, and decision points. "
            "Use minimal technical jargon, maximum business clarity."
        ),
    ),
}


# ============================================================================
# Utility Functions
# ============================================================================

def get_persona_tone_rule(persona: ExplainPersona | str) -> PersonaToneRule:
    """
    Get tone rule for specified persona.
    
    Args:
        persona: ExplainPersona enum or string persona name
        
    Returns:
        PersonaToneRule for the persona
        
    Raises:
        KeyError: If persona not in rules (should not happen)
        ValueError: If persona string is invalid
    """
    from .explain_persona import validate_persona
    
    # Convert string to enum if needed
    if isinstance(persona, str):
        persona = validate_persona(persona)
    
    return PERSONA_TONE_RULES[persona]


def validate_explanation_tone(
    text: str,
    persona: ExplainPersona | str,
    check_length: bool = True,
    check_terms: bool = True,
) -> List[str]:
    """
    Validate explanation text against persona tone rules.
    
    Args:
        text: Explanation text to validate
        persona: Target persona (enum or string)
        check_length: Whether to check sentence length
        check_terms: Whether to check forbidden terms
        
    Returns:
        List of validation issues (empty if all checks pass)
    """
    issues = []
    rule = get_persona_tone_rule(persona)
    
    # Split into sentences (simple approach)
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    
    if check_length:
        # Check sentence length
        for i, sentence in enumerate(sentences):
            if len(sentence) < rule.min_sentence_length:
                issues.append(
                    f"Sentence {i+1} too short ({len(sentence)} chars < "
                    f"min {rule.min_sentence_length}): '{sentence[:50]}...'"
                )
            if len(sentence) > rule.max_sentence_length:
                issues.append(
                    f"Sentence {i+1} too long ({len(sentence)} chars > "
                    f"max {rule.max_sentence_length}): '{sentence[:50]}...'"
                )
        
        # Check paragraph length
        if len(sentences) > rule.max_sentences_per_paragraph:
            issues.append(
                f"Too many sentences ({len(sentences)} > "
                f"max {rule.max_sentences_per_paragraph}) for {rule.persona.value}"
            )
    
    if check_terms:
        # Check for forbidden terms
        text_lower = text.lower()
        for term in rule.forbidden_terms:
            if term.lower() in text_lower:
                issues.append(
                    f"Forbidden term '{term}' found in {rule.persona.value} explanation"
                )
    
    return issues


def get_tone_guidelines(persona: ExplainPersona | str) -> str:
    """
    Get human-readable tone guidelines for persona.
    
    Args:
        persona: ExplainPersona enum or string persona name
        
    Returns:
        String with tone guidelines
    """
    rule = get_persona_tone_rule(persona)
    return f"""
{rule.persona.value} Tone Guidelines:
- Sentence length: {rule.min_sentence_length}-{rule.max_sentence_length} characters
- Max sentences per paragraph: {rule.max_sentences_per_paragraph}
- Preferred styles: {', '.join(s.value for s in rule.preferred_styles)}
- Style: {rule.style_guidelines}
"""


def get_all_persona_tone_rules() -> Dict[ExplainPersona, PersonaToneRule]:
    """
    Get all persona tone rules.
    
    Returns:
        Dictionary of all persona tone rules
    """
    return PERSONA_TONE_RULES.copy()


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "ToneStyle",
    "PersonaToneRule",
    "PERSONA_TONE_RULES",
    "get_persona_tone_rule",
    "validate_explanation_tone",
    "get_tone_guidelines",
    "get_all_persona_tone_rules",
]