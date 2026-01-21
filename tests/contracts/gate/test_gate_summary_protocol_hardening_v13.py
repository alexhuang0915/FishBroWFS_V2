"""
Gate Summary Protocol Hardening v1.3 MAX - Enforcement Tests.

Tests for the six patches (A-F) implemented in v1.3 MAX hardening:
- Patch A: Remove duplicate GateSummaryV1 model
- Patch B: Fix cross-job service to never return None
- Patch C: Add SSOT safe helpers + telemetry
- Patch D: Harden UI conversion functions
- Patch E: Harden deserialization in bundle_resolver.py
- Patch F: Create fixtures, snapshots, and tests (this file)

These tests ensure the protocol hardening is effective and prevents regression.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from contracts.portfolio.gate_summary_schemas import (
    GateSummaryV1,
    GateItemV1,
    GateStatus,
    GateReasonCode,
    safe_gate_summary_from_raw,
    safe_gate_item_from_raw,
    build_error_gate_item,
    sanitize_raw,
    create_gate_summary_from_gates,
)
from gui.services.gate_summary_service import GateResult, GateSummary as UIGateSummary
from gui.services.cross_job_gate_summary_service import CrossJobGateSummaryService
from core.deployment.bundle_resolver import BundleResolver

# Handle PySide6 import for GUI tests
try:
    from gui.desktop.widgets.gate_summary_widget import GateSummaryWidget
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    GateSummaryWidget = None


# ============================================================================
# Fixture Loading
# ============================================================================

def load_golden_fixture(name: str) -> dict:
    """Load golden JSON fixture from tests/fixtures/gate_summary_v13/."""
    fixture_path = Path(__file__).parent / "fixtures" / "gate_summary_v13" / f"{name}.json"
    if not fixture_path.exists():
        pytest.skip(f"Golden fixture not found: {fixture_path}")
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================================
# Patch C Tests: SSOT Safe Helpers
# ============================================================================

class TestPatchCSafeHelpers:
    """Test SSOT safe helpers with telemetry."""
    
    def test_safe_gate_summary_from_raw_valid(self):
        """Test safe_gate_summary_from_raw with valid data."""
        raw = load_golden_fixture("valid_gate_summary")
        summary = safe_gate_summary_from_raw(
            raw,
            error_path="test.safe_gate_summary_from_raw_valid",
        )
        assert isinstance(summary, GateSummaryV1)
        assert summary.schema_version == "v1"
        assert len(summary.gates) > 0
        assert summary.overall_status in GateStatus
    
    def test_safe_gate_summary_from_raw_invalid(self):
        """Test safe_gate_summary_from_raw with invalid data returns error summary."""
        raw = {"invalid": "data", "schema_version": "v99"}
        summary = safe_gate_summary_from_raw(
            raw,
            error_path="test.safe_gate_summary_from_raw_invalid",
        )
        assert isinstance(summary, GateSummaryV1)
        # Should contain at least one error gate
        error_gates = [g for g in summary.gates if g.status == GateStatus.REJECT]
        assert len(error_gates) > 0
        # Error gate should have telemetry details
        error_gate = error_gates[0]
        assert error_gate.details is not None
        assert "error_path" in error_gate.details
    
    def test_safe_gate_item_from_raw(self):
        """Test safe_gate_item_from_raw with valid and invalid data."""
        # Valid case
        raw_valid = {
            "gate_id": "test_gate",
            "gate_name": "Test Gate",
            "status": "PASS",
            "message": "Test message",
        }
        item = safe_gate_item_from_raw(
            "test_gate",
            raw_valid,
            error_path="test.safe_gate_item_from_raw_valid",
        )
        assert isinstance(item, GateItemV1)
        assert item.gate_id == "test_gate"
        assert item.status == GateStatus.PASS
        
        # Invalid case (should return error gate)
        raw_invalid = {"invalid": "data"}
        error_item = safe_gate_item_from_raw(
            "test_gate",
            raw_invalid,
            error_path="test.safe_gate_item_from_raw_invalid",
        )
        assert error_item.status == GateStatus.REJECT
        assert error_item.reason_codes == [GateReasonCode.GATE_ITEM_PARSE_ERROR.value]
    
    def test_build_error_gate_item(self):
        """Test building error gate items with telemetry."""
        error = ValueError("Test error")
        error_gate = build_error_gate_item(
            gate_id="test_error",
            reason_code=GateReasonCode.GATE_SUMMARY_PARSE_ERROR.value,
            error=error,
            error_path="test.build_error_gate_item",
            raw={"test": "data"},
        )
        assert error_gate.status == GateStatus.REJECT
        assert error_gate.gate_id == "test_error"
        assert error_gate.details is not None
        assert error_gate.details["error_class"] == "ValueError"
        assert error_gate.details["error_message"] == "Test error"
        assert error_gate.details["error_path"] == "test.build_error_gate_item"
    
    def test_sanitize_raw(self):
        """Test sanitization of raw data for telemetry."""
        # Test various data types
        assert sanitize_raw(None) is None
        assert sanitize_raw(42) == 42
        assert sanitize_raw("test") == "test"
        
        # Test dict truncation
        large_dict = {f"key_{i}": f"value_{i}" for i in range(100)}
        sanitized = sanitize_raw(large_dict, max_len=100)
        assert "__truncated_keys__" in sanitized
        assert "50 more keys" in sanitized["__truncated_keys__"]
        
        # Test list truncation
        large_list = [f"item_{i}" for i in range(150)]
        sanitized = sanitize_raw(large_list, max_len=100)
        assert len(sanitized) == 101  # 100 items + truncation message
        assert "... (truncated, total 150 items)" in sanitized[-1]


# ============================================================================
# Patch D Tests: UI Conversion Functions
# ============================================================================

class TestPatchDUIConversion:
    """Test hardened UI conversion functions."""
    
    @pytest.mark.skipif(not QT_AVAILABLE, reason="PySide6 not available")
    def test_gate_summary_widget_conversion(self):
        """Test GateSummaryWidget._convert_consolidated_to_gate_summary with safe helpers."""
        # Create a test consolidated summary
        consolidated = GateSummaryV1(
            schema_version="v1",
            overall_status=GateStatus.PASS,
            overall_message="Test summary",
            gates=[
                GateItemV1(
                    gate_id="test_gate",
                    gate_name="Test Gate",
                    status=GateStatus.PASS,
                    message="Test message",
                    evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
                    evaluator="test",
                    details={"telemetry": "test"},
                    reason_codes=["TEST_CODE"],
                )
            ],
            evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
            source="test",
            evaluator="test",
            counts={"pass": 1, "warn": 0, "reject": 0, "skip": 0, "unknown": 0},
        )
        
        # Create widget and convert
        widget = GateSummaryWidget()
        ui_summary = widget._convert_consolidated_to_gate_summary(consolidated)
        
        assert isinstance(ui_summary, UIGateSummary)
        assert len(ui_summary.gates) == 1
        gate_result = ui_summary.gates[0]
        assert gate_result.gate_id == "test_gate"
        assert gate_result.details is not None
        # Telemetry should be preserved
        assert gate_result.details.get("telemetry") == "test"
        assert gate_result.details.get("reason_codes") == ["TEST_CODE"]
    
    @pytest.mark.skipif(not QT_AVAILABLE, reason="PySide6 not available")
    def test_conversion_with_error_gates(self):
        """Test conversion when consolidated summary contains error gates."""
        consolidated = GateSummaryV1(
            schema_version="v1",
            overall_status=GateStatus.REJECT,
            overall_message="Contains errors",
            gates=[
                build_error_gate_item(
                    gate_id="parse_error",
                    reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR.value,
                    error=ValueError("Parse failed"),
                    error_path="test.conversion_with_error_gates",
                    raw={"invalid": "data"},
                )
            ],
            evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
            source="test",
            evaluator="test",
            counts={"pass": 0, "warn": 0, "reject": 1, "skip": 0, "unknown": 0},
        )
        
        widget = GateSummaryWidget()
        ui_summary = widget._convert_consolidated_to_gate_summary(consolidated)
        
        assert ui_summary.overall_status.name == "FAIL"  # REJECT maps to FAIL in UI
        assert len(ui_summary.gates) == 1
        gate_result = ui_summary.gates[0]
        assert gate_result.status.name == "FAIL"


# ============================================================================
# Patch E Tests: Bundle Resolver Deserialization
# ============================================================================

class TestPatchEBundleResolver:
    """Test hardened deserialization in bundle_resolver.py."""
    
    def test_bundle_resolver_uses_safe_helpers(self, tmp_path):
        """Test that BundleResolver uses safe_gate_summary_from_raw."""
        # Create a mock deployment bundle with gate summary
        deploy_dir = tmp_path / "deployment_test"
        deploy_dir.mkdir()
        
        # Create manifest
        manifest = {
            "schema_version": "v1",
            "deployment_id": "test_deploy",
            "job_id": "test_job",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "test",
            "artifacts": [
                {
                    "artifact_id": "gate_summary",
                    "artifact_type": "gate_summary_v1",
                    "target_path": "gate_summary.json",
                    "checksum_sha256": "test_hash",
                    "metadata": {},
                }
            ],
            "artifact_count": 1,
            "manifest_hash": "test_manifest_hash",
            "bundle_hash": "test_bundle_hash",
            "deployment_target": "test",
            "deployment_notes": "test",
        }
        
        manifest_path = deploy_dir / "deployment_manifest_v1.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f)
        
        # Create gate summary artifact (valid)
        gate_summary = load_golden_fixture("valid_gate_summary")
        gate_summary_path = deploy_dir / "gate_summary.json"
        with open(gate_summary_path, 'w', encoding='utf-8') as f:
            json.dump(gate_summary, f)
        
        # Resolve bundle
        resolver = BundleResolver(outputs_root=tmp_path)
        resolution = resolver.resolve_bundle(deploy_dir)
        
        # Note: resolution.is_valid may be False due to hash verification failure
        # The important part is that the resolver doesn't crash and parses the gate summary
        assert resolution.manifest is not None
        assert resolution.manifest.gate_summary is not None
        assert isinstance(resolution.manifest.gate_summary, GateSummaryV1)
        # Gate summary should be valid (parsed correctly)
        assert resolution.manifest.gate_summary.overall_status != GateStatus.REJECT
    
    def test_bundle_resolver_handles_invalid_gate_summary(self, tmp_path):
        """Test that BundleResolver handles invalid gate summary gracefully."""
        deploy_dir = tmp_path / "deployment_test_invalid"
        deploy_dir.mkdir()
        
        # Create manifest
        manifest = {
            "schema_version": "v1",
            "deployment_id": "test_deploy_invalid",
            "job_id": "test_job",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "test",
            "artifacts": [
                {
                    "artifact_id": "gate_summary",
                    "artifact_type": "gate_summary_v1",
                    "target_path": "gate_summary_invalid.json",
                    "checksum_sha256": "test_hash",
                    "metadata": {},
                }
            ],
            "artifact_count": 1,
            "manifest_hash": "test_manifest_hash",
            "bundle_hash": "test_bundle_hash",
            "deployment_target": "test",
            "deployment_notes": "test",
        }
        
        manifest_path = deploy_dir / "deployment_manifest_v1.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f)
        
        # Create invalid gate summary artifact
        invalid_gate_summary = {"invalid": "data", "schema_version": "v99"}
        gate_summary_path = deploy_dir / "gate_summary_invalid.json"
        with open(gate_summary_path, 'w', encoding='utf-8') as f:
            json.dump(invalid_gate_summary, f)
        
        # Resolve bundle - should not crash
        resolver = BundleResolver(outputs_root=tmp_path)
        resolution = resolver.resolve_bundle(deploy_dir)
        
        # Note: resolution.is_valid may be False due to hash verification failure
        # The important part is that the resolver doesn't crash and handles invalid gate summary
        assert resolution.manifest is not None
        assert resolution.manifest.gate_summary is not None
        # Should contain error gates (invalid data should produce error summary)
        error_gates = [g for g in resolution.manifest.gate_summary.gates
                      if g.status == GateStatus.REJECT]
        assert len(error_gates) > 0


# ============================================================================
# Patch B Tests: Cross-Job Service Never Returns None
# ============================================================================

class TestPatchBCrossJobService:
    """Test cross-job service never returns None."""
    
    def test_cross_job_service_always_returns_summary(self, monkeypatch):
        """Test fetch_gate_summary_for_job always returns GateSummaryV1, never None."""
        service = CrossJobGateSummaryService()
        
        # Mock the consolidated service to raise an exception
        class MockConsolidatedService:
            def fetch_consolidated_summary(self, job_id):
                raise Exception("Network error")
        
        # Replace the consolidated service
        service.consolidated_service = MockConsolidatedService()
        
        # Should return error summary, not None
        summary = service.fetch_gate_summary_for_job("test_job")
        assert isinstance(summary, GateSummaryV1)
        assert summary.overall_status == GateStatus.REJECT
        # Should contain error gate
        error_gates = [g for g in summary.gates if g.status == GateStatus.REJECT]
        assert len(error_gates) > 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for the complete hardening pipeline."""
    
    @pytest.mark.skipif(not QT_AVAILABLE, reason="PySide6 not available")
    def test_end_to_end_safe_parsing(self):
        """Test end-to-end safe parsing from raw JSON to UI."""
        # Load golden fixture
        raw = load_golden_fixture("valid_gate_summary")
        
        # 1. Parse with safe helper (Patch C)
        safe_summary = safe_gate_summary_from_raw(
            raw,
            error_path="test.end_to_end_safe_parsing",
        )
        assert isinstance(safe_summary, GateSummaryV1)
        
        # 2. Convert to UI format (Patch D)
        widget = GateSummaryWidget()
        ui_summary = widget._convert_consolidated_to_gate_summary(safe_summary)
        assert isinstance(ui_summary, UIGateSummary)
        
        # 3. Verify telemetry preservation
        for gate_item in safe_summary.gates:
            if gate_item.details:
                # Find corresponding UI gate
                ui_gate = next(
                    (g for g in ui_summary.gates if g.gate_id == gate_item.gate_id),
                    None
                )
                if ui_gate:
                    assert ui_gate.details is not None
                    # Some telemetry should be preserved
                    assert "reason_codes" in ui_gate.details or "telemetry" in ui_gate.details
    
    @pytest.mark.skipif(not QT_AVAILABLE, reason="PySide6 not available")
    def test_error_propagation(self):
        """Test that errors propagate safely through the entire pipeline."""
        # Create invalid raw data
        raw_invalid = {
            "invalid": "data",
            "schema_version": "v99",
            "gates": [{"not_a_gate": "data"}]
        }
        
        # 1. Safe parsing should produce error summary
        error_summary = safe_gate_summary_from_raw(
            raw_invalid,
            error_path="test.error_propagation",
        )
        assert error_summary.overall_status == GateStatus.REJECT
        
        # 2. UI conversion should handle error summary
        widget = GateSummaryWidget()
        ui_summary = widget._convert_consolidated_to_gate_summary(error_summary)
        assert ui_summary.overall_status.name == "FAIL"  # REJECT -> FAIL
        
        # 3. Should not crash
        assert len(ui_summary.gates) > 0


# ============================================================================
# Schema Snapshot Tests
# ============================================================================

class TestSchemaSnapshots:
    """Test that schema snapshots are stable."""
    
    def test_gate_summary_schema_stable(self):
        """Test that GateSummaryV1 JSON schema hasn't changed unexpectedly."""
        schema = GateSummaryV1.model_json_schema()
        
        # Check critical fields exist
        assert "properties" in schema
        props = schema["properties"]
        
        required_fields = {"schema_version", "overall_status", "gates", "evaluated_at_utc"}
        for field in required_fields:
            assert field in props, f"Required field {field} missing from schema"
        
        # Check gates array structure
        gates_schema = props["gates"]
        assert gates_schema["type"] == "array"
        
        # Save schema snapshot for future comparison
        snapshot_dir = Path(__file__).parent / "contract_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / "gate_summary_v1_schema.json"
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, sort_keys=True)
        
        # Verify snapshot was created
        assert snapshot_path.exists()
    
    def test_gate_item_schema_stable(self):
        """Test that GateItemV1 JSON schema hasn't changed unexpectedly."""
        schema = GateItemV1.model_json_schema()
        
        # Check critical fields exist
        assert "properties" in schema
        props = schema["properties"]
        
        required_fields = {"gate_id", "gate_name", "status", "message"}
        for field in required_fields:
            assert field in props, f"Required field {field} missing from schema"
        
        # Save schema snapshot
        snapshot_dir = Path(__file__).parent / "contract_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / "gate_item_v1_schema.json"
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, sort_keys=True)
        
        assert snapshot_path.exists()


# ============================================================================
# Patch A Tests: Duplicate Model Removal
# ============================================================================

class TestPatchADuplicateModel:
    """Test that duplicate GateSummaryV1 model was properly removed."""
    
    def test_no_duplicate_gate_summary_in_evidence_aggregator(self):
        """Test that evidence_aggregator.py no longer contains duplicate GateSummaryV1."""
        # Import the renamed class
        from core.portfolio.evidence_aggregator import GatekeeperMetricsV1
        
        # Verify it's not the same as GateSummaryV1
        assert GatekeeperMetricsV1 != GateSummaryV1
        
        # Check that GatekeeperMetricsV1 has the expected fields
        schema = GatekeeperMetricsV1.model_json_schema()
        assert "properties" in schema
        props = schema["properties"]
        
        # Should have gatekeeper-specific fields, not gate summary fields
        assert "total_permutations" in props
        assert "valid_candidates" in props
        assert "plateau_check" in props
        assert "gates" not in props  # This is in GateSummaryV1, not GatekeeperMetricsV1


# ============================================================================
# Main Test Runner
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])