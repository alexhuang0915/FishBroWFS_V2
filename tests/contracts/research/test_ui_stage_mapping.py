"""
UI Stage Mapping Tests v2.0 - Classification Registry Validation

These tests enforce the UI classification registry governance:
- NO PAGE MAY BE UNTAGGED
- NO PAGE MAY CLAIM PRIMARY EXCEPT RESEARCH FLOW
- All existing UI pages must be properly classified
- Navigation validation must work correctly
"""

import pytest
from typing import List

from contracts.research.ui_stage_mapping import (
    UiPageClassification,
    UiPageTier,
    UI_PAGE_CLASSIFICATIONS,
    get_page_classification,
    validate_page_navigation,
    get_available_pages_for_stage,
    get_primary_entry_point,
    validate_registry_completeness,
)
from contracts.research.research_flow_kernel import ResearchStage


class TestUiPageClassificationRegistry:
    """Test UI page classification registry governance."""
    
    def test_registry_not_empty(self):
        """Test that registry is not empty."""
        assert len(UI_PAGE_CLASSIFICATIONS) > 0
    
    def test_all_classifications_are_valid(self):
        """Test that all classifications are valid UiPageClassification instances."""
        for classification in UI_PAGE_CLASSIFICATIONS:
            assert isinstance(classification, UiPageClassification)
            assert classification.page_id
            assert classification.display_name
            assert classification.tier in UiPageTier
    
    def test_no_duplicate_page_ids(self):
        """Test that no page IDs are duplicated."""
        page_ids = [c.page_id for c in UI_PAGE_CLASSIFICATIONS]
        assert len(page_ids) == len(set(page_ids)), f"Duplicate page IDs found: {page_ids}"
    
    def test_get_page_classification(self):
        """Test get_page_classification function."""
        # Test existing page
        classification = get_page_classification("research_flow")
        assert classification is not None
        assert classification.page_id == "research_flow"
        assert classification.tier == UiPageTier.PRIMARY
        
        # Test non-existent page
        classification = get_page_classification("non_existent_page")
        assert classification is None
    
    def test_validate_registry_completeness(self):
        """Test registry completeness validation."""
        errors = validate_registry_completeness()
        assert errors == [], f"Registry completeness validation failed: {errors}"


class TestPrimaryEntryPointGovernance:
    """Test PRIMARY entry point governance."""
    
    def test_exactly_one_primary_page(self):
        """Test that exactly ONE page is PRIMARY tier."""
        primary_pages = [
            c for c in UI_PAGE_CLASSIFICATIONS 
            if c.tier == UiPageTier.PRIMARY
        ]
        
        assert len(primary_pages) == 1, f"Expected exactly 1 PRIMARY page, found {len(primary_pages)}"
    
    def test_research_flow_is_primary(self):
        """Test that Research Flow is the PRIMARY entry point."""
        primary = get_primary_entry_point()
        assert primary.page_id == "research_flow"
        assert primary.tier == UiPageTier.PRIMARY
    
    def test_no_other_primary_pages(self):
        """Test that no other pages claim PRIMARY tier."""
        for classification in UI_PAGE_CLASSIFICATIONS:
            if classification.page_id != "research_flow":
                assert classification.tier != UiPageTier.PRIMARY, \
                    f"Page {classification.page_id} incorrectly claims PRIMARY tier"


class TestExistingUiPagesAreTagged:
    """Test that all existing UI pages are properly tagged."""
    
    def test_core_ui_pages_are_tagged(self):
        """Test that core UI pages are tagged in registry."""
        # List of known UI pages that MUST be tagged
        known_ui_pages = [
            "research_flow",      # PRIMARY entry point
            "operation",          # Operation tab
            "gate_dashboard",     # Gate Dashboard tab
            "report",             # Report tab
            "allocation",         # Allocation tab
            "audit",              # Audit tab
            "registry",           # Registry tab
            "portfolio_admission", # Portfolio Admission tab
        ]
        
        for page_id in known_ui_pages:
            classification = get_page_classification(page_id)
            assert classification is not None, f"UI page '{page_id}' is not tagged in registry"
            assert classification.page_id == page_id
    
    def test_page_classifications_have_valid_stages(self):
        """Test that page classifications have valid research stages."""
        for classification in UI_PAGE_CLASSIFICATIONS:
            for stage in classification.supported_stages:
                assert stage in ResearchStage, f"Invalid stage {stage} in {classification.page_id}"
    
    def test_tier_classifications_are_valid(self):
        """Test that tier classifications make sense."""
        for classification in UI_PAGE_CLASSIFICATIONS:
            # PRIMARY tier should have research_flow only
            if classification.tier == UiPageTier.PRIMARY:
                assert classification.page_id == "research_flow"
            
            # TOOL tier should have supported_stages
            if classification.tier == UiPageTier.TOOL:
                assert len(classification.supported_stages) > 0, \
                    f"TOOL page {classification.page_id} must have supported_stages"
            
            # EXPERT tier may have empty supported_stages (available in all stages)
            # This is allowed


class TestNavigationValidation:
    """Test navigation validation logic."""
    
    def test_validate_page_navigation_success(self):
        """Test successful navigation validation."""
        # Research Flow should be available in all stages
        for stage in ResearchStage:
            is_allowed, reason = validate_page_navigation("research_flow", stage)
            assert is_allowed is True, f"Research Flow should be available in {stage}: {reason}"
            assert reason is None
        
        # Operation should be available in DATA_READINESS
        is_allowed, reason = validate_page_navigation("operation", ResearchStage.DATA_READINESS)
        assert is_allowed is True, f"Operation should be available in DATA_READINESS: {reason}"
        assert reason is None
        
        # Gate Dashboard should be available in OUTCOME_TRIAGE
        is_allowed, reason = validate_page_navigation("gate_dashboard", ResearchStage.OUTCOME_TRIAGE)
        assert is_allowed is True, f"Gate Dashboard should be available in OUTCOME_TRIAGE: {reason}"
        assert reason is None
    
    def test_validate_page_navigation_blocked(self):
        """Test blocked navigation validation."""
        # Operation should NOT be available in DECISION stage
        is_allowed, reason = validate_page_navigation("operation", ResearchStage.DECISION)
        assert is_allowed is False, f"Operation should NOT be available in DECISION"
        assert reason is not None
        assert "not available" in reason.lower()
        
        # Gate Dashboard should NOT be available in DATA_READINESS
        is_allowed, reason = validate_page_navigation("gate_dashboard", ResearchStage.DATA_READINESS)
        assert is_allowed is False, f"Gate Dashboard should NOT be available in DATA_READINESS"
        assert reason is not None
        assert "not available" in reason.lower()
    
    def test_nonexistent_page_navigation(self):
        """Test navigation to non-existent page."""
        is_allowed, reason = validate_page_navigation("non_existent_page", ResearchStage.DATA_READINESS)
        assert is_allowed is False
        assert "not found" in reason.lower()
    
    def test_is_available_in_stage_method(self):
        """Test is_available_in_stage method."""
        # Get operation classification
        operation_class = get_page_classification("operation")
        assert operation_class is not None
        
        # Should be available in DATA_READINESS
        assert operation_class.is_available_in_stage(ResearchStage.DATA_READINESS) is True
        
        # Should NOT be available in DECISION
        assert operation_class.is_available_in_stage(ResearchStage.DECISION) is False
        
        # Test with empty supported_stages (available in all stages)
        research_flow_class = get_page_classification("research_flow")
        assert research_flow_class is not None
        
        for stage in ResearchStage:
            assert research_flow_class.is_available_in_stage(stage) is True


class TestStageAvailability:
    """Test stage availability logic."""
    
    def test_get_available_pages_for_stage(self):
        """Test get_available_pages_for_stage function."""
        # DATA_READINESS stage
        available_pages = get_available_pages_for_stage(ResearchStage.DATA_READINESS)
        page_ids = [p.page_id for p in available_pages]
        
        # Should include research_flow (PRIMARY, all stages)
        assert "research_flow" in page_ids
        
        # Should include operation (TOOL for DATA_READINESS)
        assert "operation" in page_ids
        
        # Should include report (EXPERT, all stages)
        assert "report" in page_ids
        
        # Should NOT include gate_dashboard (not available in DATA_READINESS)
        assert "gate_dashboard" not in page_ids
        
        # Should NOT include allocation (not available in DATA_READINESS)
        assert "allocation" not in page_ids
    
    def test_all_stages_have_available_pages(self):
        """Test that all stages have at least some available pages."""
        for stage in ResearchStage:
            available_pages = get_available_pages_for_stage(stage)
            assert len(available_pages) > 0, f"No pages available for stage {stage}"
            
            # Research Flow should always be available
            research_flow_pages = [p for p in available_pages if p.page_id == "research_flow"]
            assert len(research_flow_pages) == 1, f"Research Flow not available in stage {stage}"
    
    def test_tier_distribution_per_stage(self):
        """Test tier distribution for each stage."""
        for stage in ResearchStage:
            available_pages = get_available_pages_for_stage(stage)
            
            # Count tiers
            primary_count = len([p for p in available_pages if p.tier == UiPageTier.PRIMARY])
            tool_count = len([p for p in available_pages if p.tier == UiPageTier.TOOL])
            expert_count = len([p for p in available_pages if p.tier == UiPageTier.EXPERT])
            
            # Should have exactly 1 PRIMARY page (Research Flow)
            assert primary_count == 1, f"Stage {stage} should have exactly 1 PRIMARY page"
            
            # Should have at least some TOOL or EXPERT pages
            total_non_primary = tool_count + expert_count
            assert total_non_primary > 0, f"Stage {stage} should have at least one TOOL or EXPERT page"


class TestFrozenModelGovernance:
    """Test frozen model governance for UI classifications."""
    
    def test_classifications_are_frozen(self):
        """Test that UiPageClassification instances are frozen (immutable)."""
        # Get a classification
        classification = get_page_classification("research_flow")
        assert classification is not None
        
        # Attempt to modify should raise Exception (ValidationError for frozen models)
        with pytest.raises(Exception):  # Can be ValidationError or AttributeError
            classification.page_id = "modified"
        
        with pytest.raises(Exception):
            classification.tier = UiPageTier.TOOL
        
        with pytest.raises(Exception):
            classification.supported_stages = [ResearchStage.DATA_READINESS]
    
    def test_registry_is_immutable(self):
        """Test that UI_PAGE_CLASSIFICATIONS list is immutable (cannot add/remove)."""
        # Note: Python lists are mutable, but we test that our functions don't modify it
        original_length = len(UI_PAGE_CLASSIFICATIONS)
        
        # Call functions that use the registry
        get_page_classification("research_flow")
        get_available_pages_for_stage(ResearchStage.DATA_READINESS)
        validate_registry_completeness()
        
        # Registry should still have same length
        assert len(UI_PAGE_CLASSIFICATIONS) == original_length


class TestMetadataAndDescriptions:
    """Test metadata and descriptions."""
    
    def test_all_pages_have_descriptions(self):
        """Test that all pages have descriptions."""
        for classification in UI_PAGE_CLASSIFICATIONS:
            assert classification.description is not None
            assert len(classification.description.strip()) > 0, \
                f"Page {classification.page_id} has empty description"
    
    def test_primary_actions_constraints(self):
        """Test primary actions constraints."""
        for classification in UI_PAGE_CLASSIFICATIONS:
            # PRIMARY pages should have max_primary_actions = 2
            if classification.tier == UiPageTier.PRIMARY:
                assert classification.max_primary_actions == 2, \
                    f"PRIMARY page {classification.page_id} should have max_primary_actions = 2"
            
            # TOOL pages should have reasonable max_primary_actions
            if classification.tier == UiPageTier.TOOL:
                assert 1 <= classification.max_primary_actions <= 3, \
                    f"TOOL page {classification.page_id} has unreasonable max_primary_actions: {classification.max_primary_actions}"
            
            # EXPERT pages may have fewer primary actions
            if classification.tier == UiPageTier.EXPERT:
                assert classification.max_primary_actions >= 0, \
                    f"EXPERT page {classification.page_id} has negative max_primary_actions"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])