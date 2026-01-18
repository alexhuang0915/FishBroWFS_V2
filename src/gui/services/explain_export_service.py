"""
Explain Export Service - v2.3

Service for exporting research narratives and explanations in persona-specific formats.

Supports:
- JSON export of ResearchNarrativeV1 with persona-specific content
- Markdown export for documentation
- CSV export for tabular analysis
- PDF export (future)
"""

import json
import logging
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from enum import Enum

from contracts.research.research_narrative import ResearchNarrativeV1
from contracts.research.explain_persona import ExplainPersona, get_persona_display_name
from contracts.research.research_flow_kernel import ResearchStage, GateReasonCode
from gui.services.cross_job_gate_summary_service import JobGateSummary

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    """Supported export formats."""
    JSON = "json"
    MARKDOWN = "md"
    CSV = "csv"
    # PDF = "pdf"  # Future support


class ExportContent(str, Enum):
    """Content types for export."""
    NARRATIVE_ONLY = "narrative_only"
    FULL_EXPLANATION = "full_explanation"
    GATE_SUMMARY = "gate_summary"
    ALL_CONTENT = "all_content"


class ExplainExportService:
    """
    Service for exporting research narratives and explanations.
    
    Features:
    - Persona-specific content formatting
    - Multiple export formats (JSON, Markdown, CSV)
    - Batch export support
    - Export metadata and audit trail
    """
    
    def __init__(self, export_root: Optional[Path] = None):
        """
        Initialize export service.
        
        Args:
            export_root: Root directory for exports (defaults to outputs/exports/)
        """
        if export_root is None:
            export_root = Path("outputs") / "exports"
        self.export_root = export_root
        self.export_root.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.export_root / "narratives").mkdir(exist_ok=True)
        (self.export_root / "gate_summaries").mkdir(exist_ok=True)
        (self.export_root / "batch_exports").mkdir(exist_ok=True)
    
    def export_narrative(
        self,
        narrative: ResearchNarrativeV1,
        persona: ExplainPersona,
        format: ExportFormat = ExportFormat.JSON,
        content: ExportContent = ExportContent.NARRATIVE_ONLY,
        job_summary: Optional[JobGateSummary] = None,
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Export research narrative in specified format.
        
        Args:
            narrative: ResearchNarrativeV1 to export
            persona: Persona used for content generation
            format: Export format (JSON, Markdown, CSV)
            content: Content type to include
            job_summary: Optional job gate summary for additional context
            include_metadata: Whether to include export metadata
            
        Returns:
            Dictionary with export result (path, content, format, etc.)
        """
        export_time = datetime.utcnow().isoformat()
        export_id = f"explain_export_{narrative.stage.value}_{export_time.replace(':', '-').replace('.', '-')}"
        
        # Build export data
        export_data = self._build_export_data(
            narrative, persona, content, job_summary, include_metadata
        )
        
        # Generate filename
        filename = self._generate_filename(
            narrative, persona, format, export_time
        )
        
        # Export based on format
        if format == ExportFormat.JSON:
            result = self._export_json(export_data, filename)
        elif format == ExportFormat.MARKDOWN:
            result = self._export_markdown(export_data, filename)
        elif format == ExportFormat.CSV:
            result = self._export_csv(export_data, filename)
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        # Add metadata to result
        result.update({
            "export_id": export_id,
            "export_time": export_time,
            "persona": persona.value,
            "persona_display_name": get_persona_display_name(persona),
            "stage": narrative.stage.value,
            "severity": narrative.severity,
        })
        
        logger.info(f"Exported narrative {export_id} in {format.value} format for persona {persona.value}")
        return result
    
    def _build_export_data(
        self,
        narrative: ResearchNarrativeV1,
        persona: ExplainPersona,
        content: ExportContent,
        job_summary: Optional[JobGateSummary],
        include_metadata: bool
    ) -> Dict[str, Any]:
        """Build export data structure."""
        export_data = {}
        
        # Add metadata if requested
        if include_metadata:
            export_data["metadata"] = {
                "export_version": "v2.3",
                "export_timestamp": datetime.utcnow().isoformat(),
                "persona": persona.value,
                "persona_display_name": get_persona_display_name(persona),
                "content_type": content.value,
                "narrative_version": narrative.version,
            }
        
        # Add narrative content (always included)
        export_data["narrative"] = {
            "stage": narrative.stage.value,
            "severity": narrative.severity,
            "headline": narrative.headline,
            "why": narrative.why,
            "primary_reason_code": narrative.primary_reason_code.value if narrative.primary_reason_code else None,
            "developer_view": narrative.developer_view,
            "business_view": narrative.business_view,
            "next_step_action": narrative.next_step_action.value if narrative.next_step_action else None,
            "next_step_label": narrative.next_step_label,
            "drilldown_actions": narrative.drilldown_actions,
            "evidence_refs": narrative.evidence_refs,
        }
        
        # Add additional content based on content type
        if content in [ExportContent.FULL_EXPLANATION, ExportContent.ALL_CONTENT]:
            export_data["persona_context"] = {
                "persona": persona.value,
                "display_name": get_persona_display_name(persona),
                "technical_level": self._get_persona_technical_level(persona),
                "content_focus": self._get_persona_content_focus(persona),
            }
        
        if content in [ExportContent.GATE_SUMMARY, ExportContent.ALL_CONTENT] and job_summary:
            export_data["gate_summary"] = self._format_gate_summary_for_export(job_summary)
        
        if content == ExportContent.ALL_CONTENT and job_summary:
            export_data["job_context"] = {
                "job_id": job_summary.job_id,
                "job_data_summary": self._summarize_job_data(job_summary.job_data),
            }
        
        return export_data
    
    def _get_persona_technical_level(self, persona: ExplainPersona) -> str:
        """Get technical level for persona."""
        levels = {
            ExplainPersona.EXEC: "low",
            ExplainPersona.PM: "low_medium",
            ExplainPersona.TRADER: "medium",
            ExplainPersona.QA: "medium_high",
            ExplainPersona.ENGINEER: "high",
        }
        return levels.get(persona, "medium")
    
    def _get_persona_content_focus(self, persona: ExplainPersona) -> str:
        """Get content focus for persona."""
        focuses = {
            ExplainPersona.EXEC: "business_impact",
            ExplainPersona.PM: "timeline_roi",
            ExplainPersona.TRADER: "actionable_insights",
            ExplainPersona.QA: "quality_validation",
            ExplainPersona.ENGINEER: "technical_details",
        }
        return focuses.get(persona, "general")
    
    def _format_gate_summary_for_export(self, job_summary: JobGateSummary) -> Dict[str, Any]:
        """Format gate summary for export."""
        if not job_summary.gate_summary:
            return {}
        
        gate_summary = job_summary.gate_summary
        return {
            "overall_status": gate_summary.overall_status.value,
            "overall_message": gate_summary.overall_message,
            "total_gates": gate_summary.total_gates,
            "evaluated_at_utc": gate_summary.evaluated_at_utc,
            "counts": gate_summary.counts,
            "gates": [
                {
                    "gate_name": gate.gate_name,
                    "gate_id": gate.gate_id,
                    "status": gate.status.value,
                    "message": gate.message,
                    "reason_codes": gate.reason_codes,
                    "details_count": len(gate.details) if gate.details else 0,
                }
                for gate in gate_summary.gates
            ],
        }
    
    def _summarize_job_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize job data for export."""
        summary = {}
        
        # Extract key fields
        for key in ["job_id", "job_type", "status", "created_at", "completed_at"]:
            if key in job_data:
                summary[key] = job_data[key]
        
        # Count artifacts if present
        if "artifacts" in job_data:
            summary["artifact_count"] = len(job_data["artifacts"])
        
        return summary
    
    def _generate_filename(
        self,
        narrative: ResearchNarrativeV1,
        persona: ExplainPersona,
        format: ExportFormat,
        export_time: str
    ) -> str:
        """Generate filename for export."""
        # Clean time string for filename
        clean_time = export_time.replace(":", "-").replace(".", "-").replace("T", "_")
        
        # Build filename components
        components = [
            "explain",
            narrative.stage.value.lower(),
            persona.value.lower(),
            clean_time,
        ]
        
        filename = f"{'_'.join(components)}.{format.value}"
        
        # Determine directory based on format
        if format == ExportFormat.JSON:
            directory = self.export_root / "narratives" / "json"
        elif format == ExportFormat.MARKDOWN:
            directory = self.export_root / "narratives" / "markdown"
        elif format == ExportFormat.CSV:
            directory = self.export_root / "narratives" / "csv"
        else:
            directory = self.export_root / "narratives"
        
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory / filename)
    
    def _export_json(self, export_data: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """Export data as JSON."""
        filepath = Path(filename)
        
        # Write JSON file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        # Also return content as string
        content = json.dumps(export_data, indent=2, ensure_ascii=False)
        
        return {
            "filepath": str(filepath),
            "content": content,
            "format": ExportFormat.JSON.value,
            "size_bytes": len(content.encode('utf-8')),
        }
    
    def _export_markdown(self, export_data: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """Export data as Markdown."""
        filepath = Path(filename)
        
        # Build Markdown content
        md_content = self._build_markdown_content(export_data)
        
        # Write Markdown file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        return {
            "filepath": str(filepath),
            "content": md_content,
            "format": ExportFormat.MARKDOWN.value,
            "size_bytes": len(md_content.encode('utf-8')),
        }
    
    def _build_markdown_content(self, export_data: Dict[str, Any]) -> str:
        """Build Markdown content from export data."""
        lines = []
        
        # Title
        narrative = export_data.get("narrative", {})
        lines.append(f"# Research Narrative Export")
        lines.append("")
        
        # Metadata section
        if "metadata" in export_data:
            metadata = export_data["metadata"]
            lines.append("## Metadata")
            lines.append("")
            for key, value in metadata.items():
                lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
            lines.append("")
        
        # Narrative section
        lines.append("## Narrative")
        lines.append("")
        
        # Stage and severity
        stage = narrative.get("stage", "UNKNOWN").replace("_", " ").title()
        severity = narrative.get("severity", "UNKNOWN")
        lines.append(f"**Stage**: {stage}")
        lines.append(f"**Severity**: {severity}")
        lines.append("")
        
        # Headline
        lines.append("### Headline")
        lines.append(f"{narrative.get('headline', 'N/A')}")
        lines.append("")
        
        # Why explanation
        lines.append("### Why")
        lines.append(f"{narrative.get('why', 'N/A')}")
        lines.append("")
        
        # Developer view
        lines.append("### Technical Details")
        lines.append(f"{narrative.get('developer_view', 'N/A')}")
        lines.append("")
        
        # Business view
        lines.append("### Business View")
        lines.append(f"{narrative.get('business_view', 'N/A')}")
        lines.append("")
        
        # Next step
        lines.append("### Next Step")
        lines.append(f"{narrative.get('next_step_label', 'N/A')}")
        lines.append("")
        
        # Gate summary section
        if "gate_summary" in export_data:
            gate_summary = export_data["gate_summary"]
            lines.append("## Gate Summary")
            lines.append("")
            lines.append(f"**Overall Status**: {gate_summary.get('overall_status', 'N/A')}")
            lines.append(f"**Total Gates**: {gate_summary.get('total_gates', 0)}")
            lines.append("")
            
            if "gates" in gate_summary:
                lines.append("### Individual Gates")
                lines.append("")
                for i, gate in enumerate(gate_summary["gates"], 1):
                    lines.append(f"{i}. **{gate.get('gate_name', 'Unknown')}**")
                    lines.append(f"   - Status: {gate.get('status', 'N/A')}")
                    lines.append(f"   - Message: {gate.get('message', 'N/A')}")
                    if gate.get("reason_codes"):
                        lines.append(f"   - Reason Codes: {', '.join(gate['reason_codes'])}")
                    lines.append("")
        
        # Footer
        lines.append("---")
        lines.append(f"*Generated by Explain Export Service v2.3*")
        lines.append(f"*Export Time: {datetime.utcnow().isoformat()}*")
        
        return "\n".join(lines)
    
    def _export_csv(self, export_data: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """Export data as CSV (flattened for tabular analysis)."""
        filepath = Path(filename)
        
        # Flatten data for CSV
        csv_rows = self._flatten_for_csv(export_data)
        
        # Write CSV file
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            if csv_rows:
                fieldnames = csv_rows[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)
        
        # Also return content as string
        output = io.StringIO()
        if csv_rows:
            fieldnames = csv_rows[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        
        content = output.getvalue()
        
        return {
            "filepath": str(filepath),
            "content": content,
            "format": ExportFormat.CSV.value,
            "size_bytes": len(content.encode('utf-8')),
        }
    
    def _flatten_for_csv(self, export_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten export data for CSV format."""
        rows = []
        
        # Extract narrative data
        narrative = export_data.get("narrative", {})
        metadata = export_data.get("metadata", {})
        
        # Create base row
        row = {
            "export_timestamp": metadata.get("export_timestamp", ""),
            "persona": metadata.get("persona", ""),
            "stage": narrative.get("stage", ""),
            "severity": narrative.get("severity", ""),
            "headline": narrative.get("headline", ""),
            "why_explanation": narrative.get("why", ""),
            "developer_view": narrative.get("developer_view", ""),
            "business_view": narrative.get("business_view", ""),
            "next_step_label": narrative.get("next_step_label", ""),
            "primary_reason_code": narrative.get("primary_reason_code", ""),
        }
        
        # Add gate summary data if present
        if "gate_summary" in export_data:
            gate_summary = export_data["gate_summary"]
            row.update({
                "gate_overall_status": gate_summary.get("overall_status", ""),
                "gate_total_count": gate_summary.get("total_gates", 0),
                "gate_evaluated_at": gate_summary.get("evaluated_at_utc", ""),
            })
        
        rows.append(row)
        
        # Add separate rows for each gate if present
        if "gate_summary" in export_data and "gates" in export_data["gate_summary"]:
            for i, gate in enumerate(export_data["gate_summary"]["gates"]):
                gate_row = row.copy()
                gate_row.update({
                    "gate_index": i + 1,
                    "gate_name": gate.get("gate_name", ""),
                    "gate_id": gate.get("gate_id", ""),
                    "gate_status": gate.get("status", ""),
                    "gate_message": gate.get("message", ""),
                    "gate_reason_codes": ", ".join(gate.get("reason_codes", [])),
                    "gate_details_count": gate.get("details_count", 0),
                })
                rows.append(gate_row)
        
        return rows
    
    def export_batch(
        self,
        narratives: List[ResearchNarrativeV1],
        personas: List[ExplainPersona],
        format: ExportFormat = ExportFormat.CSV,
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Export multiple narratives in batch.
        
        Args:
            narratives: List of ResearchNarrativeV1 to export
            personas: List of personas (must match narratives length or be single persona for all)
            format: Export format (CSV recommended for batch)
            include_metadata: Whether to include export metadata
            
        Returns:
            Dictionary with batch export result
        """
        if len(personas) == 1:
            personas = personas * len(narratives)
        elif len(personas) != len(narratives):
            raise ValueError("Personas list must match narratives length or be a single persona")
        
        export_time = datetime.utcnow().isoformat()
        export_id = f"batch_export_{export_time.replace(':', '-').replace('.', '-').replace('T', '_')}"
        
        # Build batch data
        batch_data = []
        for i, (narrative, persona) in enumerate(zip(narratives, personas)):
            export_data = self._build_export_data(
                narrative, persona, ExportContent.NARRATIVE_ONLY, None, include_metadata
            )
            batch_data.append(export_data)
        
        # Generate filename
        clean_time = export_time.replace(":", "-").replace(".", "-").replace("T", "_")
        filename = f"batch_export_{clean_time}.{format.value}"
        filepath = self.export_root / "batch_exports" / filename
        
        # Export based on format
        if format == ExportFormat.CSV:
            # Flatten all data for CSV
            all_rows = []
            for data in batch_data:
                all_rows.extend(self._flatten_for_csv(data))
            
            # Write CSV file
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                if all_rows:
                    fieldnames = all_rows[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_rows)
            
            # Get content as string
            output = io.StringIO()
            if all_rows:
                fieldnames = all_rows[0].keys()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            
            content = output.getvalue()
            
            result = {
                "filepath": str(filepath),
                "content": content,
                "format": format.value,
                "size_bytes": len(content.encode('utf-8')),
            }
        else:
            # For non-CSV formats, create a combined JSON
            combined_data = {
                "metadata": {
                    "export_version": "v2.3",
                    "export_timestamp": export_time,
                    "export_type": "batch",
                    "item_count": len(narratives),
                },
                "items": batch_data,
            }
            
            if format == ExportFormat.JSON:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(combined_data, f, indent=2, ensure_ascii=False)
                content = json.dumps(combined_data, indent=2, ensure_ascii=False)
            elif format == ExportFormat.MARKDOWN:
                # Create combined markdown
                md_content = self._build_batch_markdown(combined_data)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                content = md_content
            else:
                raise ValueError(f"Batch export not supported for format: {format}")
            
            result = {
                "filepath": str(filepath),
                "content": content,
                "format": format.value,
                "size_bytes": len(content.encode('utf-8')),
            }
        
        # Add batch metadata
        result.update({
            "export_id": export_id,
            "export_time": export_time,
            "item_count": len(narratives),
            "personas_used": list(set(p.value for p in personas)),
        })
        
        logger.info(f"Exported batch {export_id} with {len(narratives)} items in {format.value} format")
        return result
    
    def _build_batch_markdown(self, batch_data: Dict[str, Any]) -> str:
        """Build Markdown content for batch export."""
        lines = []
        
        metadata = batch_data.get("metadata", {})
        items = batch_data.get("items", [])
        
        # Title
        lines.append(f"# Batch Narrative Export")
        lines.append("")
        
        # Metadata
        lines.append("## Metadata")
        lines.append("")
        for key, value in metadata.items():
            lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
        lines.append("")
        
        # Items
        lines.append("## Items")
        lines.append("")
        
        for i, item in enumerate(items, 1):
            narrative = item.get("narrative", {})
            item_metadata = item.get("metadata", {})
            
            lines.append(f"### Item {i}")
            lines.append("")
            
            # Item metadata
            if item_metadata:
                lines.append("#### Metadata")
                for key, value in item_metadata.items():
                    if key != "export_timestamp":  # Already in main metadata
                        lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
                lines.append("")
            
            # Narrative content
            lines.append("#### Narrative")
            lines.append("")
            lines.append(f"**Stage**: {narrative.get('stage', 'UNKNOWN').replace('_', ' ').title()}")
            lines.append(f"**Severity**: {narrative.get('severity', 'UNKNOWN')}")
            lines.append("")
            lines.append(f"**Headline**: {narrative.get('headline', 'N/A')}")
            lines.append("")
            lines.append(f"**Why**: {narrative.get('why', 'N/A')}")
            lines.append("")
            lines.append(f"**Next Step**: {narrative.get('next_step_label', 'N/A')}")
            lines.append("")
        
        # Footer
        lines.append("---")
        lines.append(f"*Generated by Explain Export Service v2.3*")
        lines.append(f"*Export Time: {datetime.utcnow().isoformat()}*")
        
        return "\n".join(lines)
    
    def get_export_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get export history.
        
        Args:
            limit: Maximum number of exports to return
            
        Returns:
            List of export metadata
        """
        # This is a simplified implementation
        # In production, would read from a database or index file
        exports = []
        
        # Scan export directories
        for format_dir in ["json", "markdown", "csv"]:
            dir_path = self.export_root / "narratives" / format_dir
            if dir_path.exists():
                for file in dir_path.glob(f"*.{format_dir}"):
                    stat = file.stat()
                    exports.append({
                        "filename": file.name,
                        "filepath": str(file),
                        "format": format_dir,
                        "size_bytes": stat.st_size,
                        "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
        
        # Sort by modified time (newest first)
        exports.sort(key=lambda x: x["modified_time"], reverse=True)
        
        return exports[:limit]


# Singleton instance
_explain_export_service_instance: Optional[ExplainExportService] = None


def get_explain_export_service(export_root: Optional[Path] = None) -> ExplainExportService:
    """
    Get singleton ExplainExportService instance.
    
    Args:
        export_root: Optional export root directory
        
    Returns:
        ExplainExportService: Singleton instance
    """
    global _explain_export_service_instance
    
    if _explain_export_service_instance is None:
        _explain_export_service_instance = ExplainExportService(export_root)
    
    return _explain_export_service_instance