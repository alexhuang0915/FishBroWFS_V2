"""
ExplainPersona Enum - v2.3 Explainability at Scale

Defines audience-specific personas for narrative generation and explanation delivery.
Each persona receives tailored content optimized for their role and information needs.

SSOT Contract: This enum is the single source of truth for persona definitions.
UI must reference this enum, not hardcode persona strings.
"""

from enum import Enum


class ExplainPersona(str, Enum):
    """
    Audience-specific personas for narrative generation.
    
    Personas determine:
    - Content focus and depth
    - Technical vs. business emphasis
    - Action recommendations
    - Export format preferences
    """
    
    # ============================================================================
    # Core Personas (v2.3)
    # ============================================================================
    
    TRADER = "TRADER"
    """
    Quantitative trader / portfolio manager.
    
    Focus: Risk-adjusted returns, portfolio construction, execution signals.
    Content: Concise, actionable insights with clear trade implications.
    Technical Level: Medium - understands quantitative concepts but not implementation details.
    Default Persona: Yes (backward compatibility).
    """
    
    ENGINEER = "ENGINEER"
    """
    Software/data engineer, system developer.
    
    Focus: System reliability, data quality, implementation details, debugging.
    Content: Technical specifications, error analysis, system architecture.
    Technical Level: High - expects detailed technical explanations.
    """
    
    QA = "QA"
    """
    Quality assurance / testing specialist.
    
    Focus: Test coverage, validation procedures, edge cases, reproducibility.
    Content: Verification steps, test results, quality metrics.
    Technical Level: Medium-high - understands testing frameworks and validation.
    """
    
    PM = "PM"
    """
    Product manager / business analyst.
    
    Focus: Feature prioritization, user impact, business value, roadmap alignment.
    Content: Business implications, user stories, ROI analysis.
    Technical Level: Low-medium - needs business context without deep technical details.
    """
    
    EXEC = "EXEC"
    """
    Executive / stakeholder.
    
    Focus: Strategic impact, financial implications, risk management, high-level summaries.
    Content: Executive summaries, key metrics, strategic recommendations.
    Technical Level: Low - needs high-level insights without technical jargon.
    """
    
    # ============================================================================
    # Specialized Personas (future expansion)
    # ============================================================================
    
    # RESEARCHER = "RESEARCHER"  # Future: Academic/research focus
    # COMPLIANCE = "COMPLIANCE"  # Future: Regulatory/audit focus
    # OPS = "OPS"                # Future: Operations/DevOps focus


# Persona metadata for UI display and documentation
PERSONA_METADATA = {
    ExplainPersona.TRADER: {
        "display_name": "Trader",
        "description": "Quantitative trader focused on portfolio decisions",
        "icon": "📈",
        "default": True,
        "technical_level": "medium",
        "content_focus": ["returns", "risk", "execution", "portfolio"],
    },
    ExplainPersona.ENGINEER: {
        "display_name": "Engineer",
        "description": "Technical specialist focused on system implementation",
        "icon": "⚙️",
        "default": False,
        "technical_level": "high",
        "content_focus": ["implementation", "debugging", "architecture", "data"],
    },
    ExplainPersona.QA: {
        "display_name": "QA",
        "description": "Quality assurance focused on validation and testing",
        "icon": "✅",
        "default": False,
        "technical_level": "medium_high",
        "content_focus": ["testing", "validation", "reproducibility", "quality"],
    },
    ExplainPersona.PM: {
        "display_name": "Product Manager",
        "description": "Product focus on business value and user impact",
        "icon": "📊",
        "default": False,
        "technical_level": "low_medium",
        "content_focus": ["business_value", "user_impact", "roadmap", "prioritization"],
    },
    ExplainPersona.EXEC: {
        "display_name": "Executive",
        "description": "Strategic focus on high-level impact and decisions",
        "icon": "👔",
        "default": False,
        "technical_level": "low",
        "content_focus": ["strategy", "financials", "risk", "summary"],
    },
}


def get_persona_display_name(persona: ExplainPersona) -> str:
    """Get display name for persona (for UI)."""
    return PERSONA_METADATA[persona]["display_name"]


def get_persona_description(persona: ExplainPersona) -> str:
    """Get description for persona (for tooltips/help)."""
    return PERSONA_METADATA[persona]["description"]


def get_persona_icon(persona: ExplainPersona) -> str:
    """Get icon for persona (for UI)."""
    return PERSONA_METADATA[persona]["icon"]


def get_default_persona() -> ExplainPersona:
    """Get default persona (TRADER for backward compatibility)."""
    return ExplainPersona.TRADER


def get_persona_by_technical_level(level: str) -> list[ExplainPersona]:
    """
    Get personas matching specified technical level.
    
    Args:
        level: "low", "medium", "high", or "all"
        
    Returns:
        List of personas matching the technical level
    """
    if level == "all":
        return list(ExplainPersona)
    
    level_mapping = {
        "low": [ExplainPersona.EXEC],
        "low_medium": [ExplainPersona.PM, ExplainPersona.EXEC],
        "medium": [ExplainPersona.TRADER],
        "medium_high": [ExplainPersona.QA],
        "high": [ExplainPersona.ENGINEER],
    }
    
    return level_mapping.get(level, [])


def validate_persona(persona: str) -> ExplainPersona:
    """
    Validate persona string and return ExplainPersona enum.
    
    Args:
        persona: Persona string (case-insensitive)
        
    Returns:
        ExplainPersona enum
        
    Raises:
        ValueError: If persona string is invalid
    """
    try:
        return ExplainPersona(persona.upper())
    except ValueError:
        valid_personas = [p.value for p in ExplainPersona]
        raise ValueError(
            f"Invalid persona: '{persona}'. Valid personas: {valid_personas}"
        )


def get_all_personas() -> list[ExplainPersona]:
    """
    Get all available personas.
    
    Returns:
        List of all ExplainPersona enum values
    """
    return list(ExplainPersona)


# Export convenience functions
__all__ = [
    "ExplainPersona",
    "PERSONA_METADATA",
    "get_persona_display_name",
    "get_persona_description",
    "get_persona_icon",
    "get_default_persona",
    "get_persona_by_technical_level",
    "validate_persona",
    "get_all_personas",
]