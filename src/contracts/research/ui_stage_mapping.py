"""
UI Stage Mapping v2.0 - Classification Registry

Mandatory classification registry for downgrading existing UI pages.
Each existing UI page MUST be tagged with:
- supported_stage(s): Which research stages this page supports
- tier: PRIMARY (Research Flow only), TOOL (stage-bound tools), EXPERT (audit/deep dive)

NON-NEGOTIABLE CONSTITUTION:
- No page may be untagged
- No page may claim PRIMARY except Research Flow
- All navigation must pass through ResearchFlowController
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from contracts.research.research_flow_kernel import ResearchStage


class UiPageTier(str, Enum):
    """
    UI Page Tier Classification.
    
    PRIMARY: Research Flow only (THE SINGLE PRIMARY ENTRY POINT)
    TOOL: Stage-bound tools (available only in specific research stages)
    EXPERT: Audit/deep dive (always available but secondary)
    """
    PRIMARY = "primary"
    TOOL = "tool"
    EXPERT = "expert"


class UiPageClassification(BaseModel):
    """
    Classification for a UI page.
    
    Every existing UI page MUST have exactly one classification.
    No page may be untagged.
    """
    model_config = ConfigDict(frozen=True)
    
    # Page identifier (must match tab name or route)
    page_id: str = Field(
        ...,
        description="Unique identifier for UI page (e.g., 'operation', 'gate_dashboard')"
    )
    
    # Display name
    display_name: str = Field(
        ...,
        description="Human-readable display name"
    )
    
    # Tier classification
    tier: UiPageTier = Field(
        ...,
        description="UI page tier (PRIMARY, TOOL, or EXPERT)"
    )
    
    # Supported research stages
    supported_stages: List[ResearchStage] = Field(
        default_factory=list,
        description="Research stages where this page is available (empty list = all stages)"
    )
    
    # Navigation validation rules
    requires_stage_validation: bool = Field(
        default=True,
        description="Whether navigation to this page requires stage validation"
    )
    
    # Maximum allowed actions in this page (for TOOL/EXPERT pages)
    max_primary_actions: int = Field(
        default=2,
        description="Maximum number of primary actions allowed (enforced by UI)"
    )
    
    # Description for users
    description: str = Field(
        default="",
        description="Description of page purpose and usage"
    )
    
    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for page classification"
    )
    
    def is_available_in_stage(self, stage: ResearchStage) -> bool:
        """
        Check if page is available in given research stage.
        
        Args:
            stage: Research stage to check
            
        Returns:
            bool: True if page is available in stage
        """
        if not self.supported_stages:
            return True  # Available in all stages
        
        return stage in self.supported_stages
    
    def validate_navigation(self, current_stage: ResearchStage) -> tuple[bool, Optional[str]]:
        """
        Validate navigation to this page from current stage.
        
        Args:
            current_stage: Current research stage
            
        Returns:
            Tuple of (is_allowed, reason_if_blocked)
        """
        if not self.requires_stage_validation:
            return True, None
        
        if not self.is_available_in_stage(current_stage):
            reason = f"Page '{self.display_name}' not available in {current_stage.value} stage"
            return False, reason
        
        return True, None


# -----------------------------------------------------------------------------
# UI PAGE CLASSIFICATION REGISTRY (SSOT)
# -----------------------------------------------------------------------------

# NO PAGE MAY BE UNTAGGED
# NO PAGE MAY CLAIM PRIMARY EXCEPT RESEARCH FLOW

UI_PAGE_CLASSIFICATIONS = [
    # PRIMARY TIER (ONLY RESEARCH FLOW)
    UiPageClassification(
        page_id="research_flow",
        display_name="Research Flow",
        tier=UiPageTier.PRIMARY,
        supported_stages=[],  # Available in all stages
        requires_stage_validation=False,
        max_primary_actions=2,
        description="THE SINGLE PRIMARY ENTRY POINT - Master research lifecycle view",
    ),
    
    # TOOL TIER (Stage-bound tools)
    UiPageClassification(
        page_id="operation",
        display_name="Operation",
        tier=UiPageTier.TOOL,
        supported_stages=[
            ResearchStage.DATA_READINESS,
            ResearchStage.RUN_RESEARCH,
        ],
        requires_stage_validation=True,
        max_primary_actions=2,
        description="Research job execution and monitoring tool",
        metadata={"primary_use": "job_execution"},
    ),
    
    UiPageClassification(
        page_id="gate_dashboard",
        display_name="Gate Dashboard",
        tier=UiPageTier.TOOL,
        supported_stages=[
            ResearchStage.OUTCOME_TRIAGE,
            ResearchStage.DECISION,
        ],
        requires_stage_validation=True,
        max_primary_actions=2,
        description="Gate summary analysis and triage tool",
        metadata={"primary_use": "gate_analysis"},
    ),
    
    UiPageClassification(
        page_id="allocation",
        display_name="Allocation",
        tier=UiPageTier.TOOL,
        supported_stages=[
            ResearchStage.DECISION,
        ],
        requires_stage_validation=True,
        max_primary_actions=2,
        description="Portfolio allocation and decision tool",
        metadata={"primary_use": "portfolio_allocation"},
    ),
    
    # EXPERT TIER (Audit/deep dive - always available but secondary)
    UiPageClassification(
        page_id="report",
        display_name="Report",
        tier=UiPageTier.EXPERT,
        supported_stages=[],  # Available in all stages
        requires_stage_validation=False,
        max_primary_actions=1,
        description="Detailed research report viewing (expert use)",
        metadata={"audience": "expert"},
    ),
    
    UiPageClassification(
        page_id="audit",
        display_name="Audit",
        tier=UiPageTier.EXPERT,
        supported_stages=[],  # Available in all stages
        requires_stage_validation=False,
        max_primary_actions=1,
        description="System audit and deep dive (expert use)",
        metadata={"audience": "expert"},
    ),
    
    UiPageClassification(
        page_id="registry",
        display_name="Registry",
        tier=UiPageTier.EXPERT,
        supported_stages=[],  # Available in all stages
        requires_stage_validation=False,
        max_primary_actions=1,
        description="Strategy and feature registry (expert use)",
        metadata={"audience": "expert"},
    ),
    
    UiPageClassification(
        page_id="portfolio_admission",
        display_name="Portfolio Admission",
        tier=UiPageTier.EXPERT,
        supported_stages=[
            ResearchStage.DECISION,
        ],
        requires_stage_validation=True,
        max_primary_actions=1,
        description="Portfolio admission decision review (expert use)",
        metadata={"audience": "expert"},
    ),
]


# -----------------------------------------------------------------------------
# Registry Access Functions
# -----------------------------------------------------------------------------

def get_page_classification(page_id: str) -> Optional[UiPageClassification]:
    """
    Get classification for a UI page.
    
    Args:
        page_id: Page identifier
        
    Returns:
        UiPageClassification or None if not found
    """
    for classification in UI_PAGE_CLASSIFICATIONS:
        if classification.page_id == page_id:
            return classification
    return None


def get_all_page_classifications() -> List[UiPageClassification]:
    """
    Get all UI page classifications.
    
    Returns:
        List of all UI page classifications
    """
    return UI_PAGE_CLASSIFICATIONS.copy()


def validate_page_navigation(page_id: str, current_stage: ResearchStage) -> tuple[bool, Optional[str]]:
    """
    Validate navigation to a page from current stage.
    
    Args:
        page_id: Page identifier to navigate to
        current_stage: Current research stage
        
    Returns:
        Tuple of (is_allowed, reason_if_blocked)
    """
    classification = get_page_classification(page_id)
    if not classification:
        return False, f"Page '{page_id}' not found in classification registry"
    
    return classification.validate_navigation(current_stage)


def get_available_pages_for_stage(stage: ResearchStage) -> List[UiPageClassification]:
    """
    Get all pages available in given research stage.
    
    Args:
        stage: Research stage
        
    Returns:
        List of page classifications available in stage
    """
    return [
        classification
        for classification in UI_PAGE_CLASSIFICATIONS
        if classification.is_available_in_stage(stage)
    ]


def get_primary_entry_point() -> UiPageClassification:
    """
    Get the PRIMARY entry point (Research Flow).
    
    Returns:
        UiPageClassification for Research Flow
    """
    for classification in UI_PAGE_CLASSIFICATIONS:
        if classification.tier == UiPageTier.PRIMARY:
            return classification
    
    # This should never happen (constitutional requirement)
    raise RuntimeError("No PRIMARY entry point found in UI page classification registry")


def validate_registry_completeness() -> List[str]:
    """
    Validate that registry is complete (no missing pages).
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check that exactly one PRIMARY page exists
    primary_pages = [
        c for c in UI_PAGE_CLASSIFICATIONS 
        if c.tier == UiPageTier.PRIMARY
    ]
    if len(primary_pages) != 1:
        errors.append(f"Expected exactly 1 PRIMARY page, found {len(primary_pages)}")
    
    # Check that PRIMARY page is Research Flow
    if primary_pages and primary_pages[0].page_id != "research_flow":
        errors.append(f"PRIMARY page must be 'research_flow', found '{primary_pages[0].page_id}'")
    
    # TODO: Add validation for all existing UI pages
    # This would require scanning the codebase for all UI pages
    
    return errors