"""
Tests for ExplainExportService (v2.3).

Tests export functionality for research narratives with persona support.
"""

import pytest
import json
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from contracts.research.research_narrative import (
    ResearchNarrativeV1,
    ResearchStage,
    NarrativeActionId,
)
from contracts.research.research_flow_kernel import GateReasonCode
from contracts.research.explain_persona import ExplainPersona
from gui.services.explain_export_service import (
    ExplainExportService,
    ExportFormat,
    ExportContent,
    get_explain_export_service,
)
from gui.services.cross_job_gate_summary_service import JobGateSummary
from contracts.portfolio.gate_summary_schemas import GateSummaryV1, GateStatus, GateItemV1


class TestExplainExportService:
    """Test ExplainExportService functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        # Create temporary export directory
        self.temp_dir = tempfile.mkdtemp()
        self.export_root = Path(self.temp_dir) / "exports"
        
        # Create service with test directory - pass Path object, not string
        self.service = ExplainExportService(export_root=self.export_root)
        
        # Create test narrative
        self.test_narrative = ResearchNarrativeV1(
            version="v2.3",
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Test narrative headline",
            why="Test explanation of why this matters",
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Test developer view with technical details",
            business_view="Test business implications",
            next_step_label="Proceed to next stage",
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            drilldown_actions=[],
        )
        
        # Create test job summary
        self.test_job_summary = JobGateSummary(
            job_id="test_job_123",
            job_data={"test": "data"},
            gate_summary=GateSummaryV1(
                schema_version="v1",
                overall_status=GateStatus.PASS,
                overall_message="All gates passed",
                gates=[
                    GateItemV1(
                        gate_id="test_gate",
                        gate_name="Test Gate",
                        status=GateStatus.PASS,
                        message="Test message",
                        reason_codes=[],
                        evaluated_at_utc="2024-01-01T00:00:00Z",
                        evaluator="test",
                    )
                ],
                evaluated_at_utc="2024-01-01T00:00:00Z",
                evaluator="test",
                source="test",
                counts={"pass": 1, "warn": 0, "reject": 0, "skip": 0, "unknown": 0},
            ),
            fetched_at=datetime(2024, 1, 1, 0, 0, 0)
        )
    
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_export_narrative_json(self):
        """Test exporting narrative as JSON."""
        result = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.TRADER,
            format=ExportFormat.JSON,
            content=ExportContent.NARRATIVE_ONLY,
            include_metadata=True
        )
        
        # Verify result structure
        assert "export_id" in result
        assert "filepath" in result
        assert "format" in result
        assert "size_bytes" in result
        assert result["format"] == ExportFormat.JSON
        
        # Verify file was created
        assert Path(result["filepath"]).exists()
        assert result["size_bytes"] > 0
        
        # Verify JSON content
        with open(result["filepath"], "r") as f:
            data = json.load(f)
        
        assert data["narrative"]["headline"] == self.test_narrative.headline
        assert data["narrative"]["stage"] == self.test_narrative.stage.value
        assert data["metadata"]["persona"] == ExplainPersona.TRADER.value
        assert data["metadata"]["export_version"] == "v2.3"
    
    def test_export_narrative_markdown(self):
        """Test exporting narrative as Markdown."""
        result = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.ENGINEER,
            format=ExportFormat.MARKDOWN,
            content=ExportContent.NARRATIVE_ONLY,
            include_metadata=False  # Test without metadata
        )
        
        assert result["format"] == ExportFormat.MARKDOWN
        assert Path(result["filepath"]).exists()
        
        # Verify Markdown content
        with open(result["filepath"], "r") as f:
            content = f.read()
        
        assert "# Research Narrative" in content
        assert self.test_narrative.headline in content
        assert "## Why" in content
        assert self.test_narrative.why in content
    
    def test_export_narrative_csv(self):
        """Test exporting narrative as CSV."""
        result = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.PM,
            format=ExportFormat.CSV,
            content=ExportContent.NARRATIVE_ONLY
        )
        
        assert result["format"] == ExportFormat.CSV
        assert Path(result["filepath"]).exists()
        
        # Verify CSV content
        with open(result["filepath"], "r") as f:
            content = f.read()
        
        assert "stage,severity,headline" in content
        assert self.test_narrative.stage.value in content
        assert self.test_narrative.severity in content
    
    def test_export_with_gate_summary(self):
        """Test exporting narrative with gate summary."""
        result = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.TRADER,
            format=ExportFormat.JSON,
            content=ExportContent.GATE_SUMMARY,
            job_summary=self.test_job_summary,
            include_metadata=True
        )
        
        # Verify file was created
        assert Path(result["filepath"]).exists()
        
        # Verify content includes gate summary
        with open(result["filepath"], "r") as f:
            data = json.load(f)
        
        assert "gate_summary" in data
        # Note: The gate_summary doesn't contain job_id directly, it's in the gate_summary object
        # The test should check for overall_status instead
        assert data["gate_summary"]["overall_status"] == GateStatus.PASS.value
    
    def test_export_all_content(self):
        """Test exporting all content types."""
        result = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.EXEC,
            format=ExportFormat.JSON,
            content=ExportContent.ALL_CONTENT,
            job_summary=self.test_job_summary,
            include_metadata=True
        )
        
        with open(result["filepath"], "r") as f:
            data = json.load(f)
        
        # Verify all content sections are present
        assert "narrative" in data
        assert "gate_summary" in data
        assert "persona_context" in data
        assert "metadata" in data
        
        # Verify persona context
        assert data["persona_context"]["persona"] == ExplainPersona.EXEC.value
        assert data["persona_context"]["technical_level"] == "low"
        assert data["persona_context"]["content_focus"] == "business_impact"
    
    def test_batch_export(self):
        """Test batch export of multiple narratives."""
        narratives = [self.test_narrative, self.test_narrative]
        personas = [ExplainPersona.TRADER, ExplainPersona.ENGINEER]
        
        result = self.service.export_batch(
            narratives=narratives,
            personas=personas,
            format=ExportFormat.CSV,
            include_metadata=True
        )
        
        assert "export_id" in result
        assert "filepath" in result
        assert "item_count" in result
        assert result["item_count"] == 2
        assert "personas_used" in result
        assert set(result["personas_used"]) == {"TRADER", "ENGINEER"}
        
        # Verify file was created
        assert Path(result["filepath"]).exists()
    
    def test_batch_export_single_persona(self):
        """Test batch export with single persona applied to all narratives."""
        narratives = [self.test_narrative, self.test_narrative]
        personas = [ExplainPersona.QA]  # Single persona
        
        result = self.service.export_batch(
            narratives=narratives,
            personas=personas,
            format=ExportFormat.JSON
        )
        
        assert result["item_count"] == 2
        assert result["personas_used"] == ["QA"]
    
    def test_batch_export_persona_length_mismatch(self):
        """Test batch export with persona/narrative length mismatch."""
        narratives = [self.test_narrative, self.test_narrative]
        personas = [ExplainPersona.TRADER, ExplainPersona.ENGINEER, ExplainPersona.QA]  # Extra persona
        
        with pytest.raises(ValueError, match="Personas list must match narratives length"):
            self.service.export_batch(
                narratives=narratives,
                personas=personas,
                format=ExportFormat.JSON
            )
    
    def test_get_persona_technical_level(self):
        """Test persona technical level mapping."""
        levels = {
            ExplainPersona.EXEC: "low",
            ExplainPersona.PM: "low_medium",
            ExplainPersona.TRADER: "medium",
            ExplainPersona.QA: "medium_high",
            ExplainPersona.ENGINEER: "high",
        }
        
        for persona, expected_level in levels.items():
            level = self.service._get_persona_technical_level(persona)
            assert level == expected_level
    
    def test_get_persona_content_focus(self):
        """Test persona content focus mapping."""
        focuses = {
            ExplainPersona.EXEC: "business_impact",
            ExplainPersona.PM: "timeline_roi",
            ExplainPersona.TRADER: "actionable_insights",
            ExplainPersona.QA: "quality_validation",
            ExplainPersona.ENGINEER: "technical_details",
        }
        
        for persona, expected_focus in focuses.items():
            focus = self.service._get_persona_content_focus(persona)
            assert focus == expected_focus
    
    def test_generate_filename(self):
        """Test filename generation."""
        export_time = "2024-01-01T12:00:00.000000"
        
        filename = self.service._generate_filename(
            narrative=self.test_narrative,
            persona=ExplainPersona.TRADER,
            format=ExportFormat.JSON,
            export_time=export_time
        )
        
        # Verify filename components
        assert "explain" in filename
        assert "data_readiness" in filename  # stage
        assert "trader" in filename  # persona
        assert "2024-01-01_12-00-00-000000" in filename  # cleaned time (T replaced with _)
        assert filename.endswith(".json")
    
    def test_singleton_pattern(self):
        """Test that get_explain_export_service returns singleton."""
        service1 = get_explain_export_service()
        service2 = get_explain_export_service()
        
        assert service1 is service2  # Same instance
    
    def test_export_with_different_personas(self):
        """Test export with different personas produces different content."""
        # Export with TRADER persona
        result_trader = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.TRADER,
            format=ExportFormat.JSON,
            include_metadata=True
        )
        
        # Export with ENGINEER persona
        result_engineer = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.ENGINEER,
            format=ExportFormat.JSON,
            include_metadata=True
        )
        
        # Load both exports
        with open(result_trader["filepath"], "r") as f:
            data_trader = json.load(f)
        
        with open(result_engineer["filepath"], "r") as f:
            data_engineer = json.load(f)
        
        # Verify persona metadata is different
        assert data_trader["metadata"]["persona"] == "TRADER"
        assert data_engineer["metadata"]["persona"] == "ENGINEER"
        
        # Verify persona context is different
        if "persona_context" in data_trader:
            assert data_trader["persona_context"]["technical_level"] == "medium"
            assert data_engineer["persona_context"]["technical_level"] == "high"
    
    def test_export_directory_structure(self):
        """Test that export creates proper directory structure."""
        result = self.service.export_narrative(
            narrative=self.test_narrative,
            persona=ExplainPersona.TRADER,
            format=ExportFormat.JSON
        )
        
        filepath = Path(result["filepath"])
        
        # Verify directory exists
        assert filepath.parent.exists()
        
        # Verify directory name matches format
        assert filepath.parent.name == "json"
        assert filepath.parent.parent.name == "narratives"
        assert filepath.parent.parent.parent == self.export_root


if __name__ == "__main__":
    pytest.main([__file__, "-v"])