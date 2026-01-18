"""
Tests for Gate Dependency Graph v1.5 Governance Trust Lock.
"""

import pytest

from src.contracts.portfolio.gate_summary_schemas import (
    GateItemV1,
    GateStatus,
    GateReasonCode,
    compute_gate_dependency_flags,
    create_gate_summary_from_gates,
)


class TestGateDependencyGraph:
    """Test gate dependency graph computation."""
    
    def create_gate(self, gate_id, status=GateStatus.PASS, depends_on=None):
        """Helper to create a gate."""
        return GateItemV1(
            gate_id=gate_id,
            gate_name=f"Gate {gate_id}",
            status=status,
            message=f"Message for {gate_id}",
            depends_on=depends_on or [],
        )
    
    def test_no_dependencies(self):
        """Test gates without dependencies."""
        gates = [
            self.create_gate("g1", GateStatus.PASS),
            self.create_gate("g2", GateStatus.WARN),
            self.create_gate("g3", GateStatus.REJECT),
        ]
        
        result = compute_gate_dependency_flags(gates)
        
        # Should have same number of gates
        assert len(result) == len(gates)
        
        # Check flags
        g1 = next(g for g in result if g.gate_id == "g1")
        g2 = next(g for g in result if g.gate_id == "g2")
        g3 = next(g for g in result if g.gate_id == "g3")
        
        # Only g3 is failed (REJECT)
        assert not g1.is_primary_fail and not g1.is_propagated_fail
        assert not g2.is_primary_fail and not g2.is_propagated_fail
        assert g3.is_primary_fail and not g3.is_propagated_fail  # No dependencies
    
    def test_simple_dependency_chain(self):
        """Test simple dependency chain."""
        gates = [
            self.create_gate("g1", GateStatus.REJECT),  # Root failure
            self.create_gate("g2", GateStatus.REJECT, depends_on=["g1"]),  # Depends on g1
            self.create_gate("g3", GateStatus.PASS, depends_on=["g2"]),  # Passes despite dependency
        ]
        
        result = compute_gate_dependency_flags(gates)
        
        g1 = next(g for g in result if g.gate_id == "g1")
        g2 = next(g for g in result if g.gate_id == "g2")
        g3 = next(g for g in result if g.gate_id == "g3")
        
        # g1 is primary fail (no dependencies)
        assert g1.is_primary_fail and not g1.is_propagated_fail
        
        # g2 is propagated fail (depends on failed g1)
        assert not g2.is_primary_fail and g2.is_propagated_fail
        
        # g3 passes, so no failure flags
        assert not g3.is_primary_fail and not g3.is_propagated_fail
    
    def test_multiple_independent_failures(self):
        """Test multiple independent failure roots."""
        gates = [
            self.create_gate("g1", GateStatus.REJECT),
            self.create_gate("g2", GateStatus.REJECT),  # Independent of g1
            self.create_gate("g3", GateStatus.REJECT, depends_on=["g1"]),  # Depends on g1
            self.create_gate("g4", GateStatus.REJECT, depends_on=["g2"]),  # Depends on g2
        ]
        
        result = compute_gate_dependency_flags(gates)
        
        g1 = next(g for g in result if g.gate_id == "g1")
        g2 = next(g for g in result if g.gate_id == "g2")
        g3 = next(g for g in result if g.gate_id == "g3")
        g4 = next(g for g in result if g.gate_id == "g4")
        
        # g1 and g2 are primary fails
        assert g1.is_primary_fail and not g1.is_propagated_fail
        assert g2.is_primary_fail and not g2.is_propagated_fail
        
        # g3 and g4 are propagated fails
        assert not g3.is_primary_fail and g3.is_propagated_fail
        assert not g4.is_primary_fail and g4.is_propagated_fail
    
    def test_transitive_dependencies(self):
        """Test transitive dependency propagation."""
        gates = [
            self.create_gate("g1", GateStatus.REJECT),
            self.create_gate("g2", GateStatus.REJECT, depends_on=["g1"]),
            self.create_gate("g3", GateStatus.REJECT, depends_on=["g2"]),  # Transitive through g2
        ]
        
        result = compute_gate_dependency_flags(gates)
        
        g1 = next(g for g in result if g.gate_id == "g1")
        g2 = next(g for g in result if g.gate_id == "g2")
        g3 = next(g for g in result if g.gate_id == "g3")
        
        # Only g1 is primary
        assert g1.is_primary_fail and not g1.is_propagated_fail
        
        # g2 and g3 are propagated
        assert not g2.is_primary_fail and g2.is_propagated_fail
        assert not g3.is_primary_fail and g3.is_propagated_fail
    
    def test_cycle_detection(self):
        """Test detection of dependency cycles."""
        gates = [
            self.create_gate("g1", GateStatus.PASS, depends_on=["g3"]),  # g1 -> g3
            self.create_gate("g2", GateStatus.PASS, depends_on=["g1"]),  # g2 -> g1
            self.create_gate("g3", GateStatus.PASS, depends_on=["g2"]),  # g3 -> g2 (cycle)
        ]
        
        result = compute_gate_dependency_flags(gates)
        
        # Should have 4 gates (original 3 + cycle error gate)
        assert len(result) == 4
        
        # Find cycle error gate
        cycle_gates = [g for g in result if g.gate_id == "gate_dependency_cycle"]
        assert len(cycle_gates) == 1
        
        cycle_gate = cycle_gates[0]
        assert cycle_gate.status == GateStatus.REJECT
        assert GateReasonCode.GATE_DEPENDENCY_CYCLE.value in cycle_gate.reason_codes
        
        # Should have telemetry details
        assert cycle_gate.details is not None
        # cycle_path is in details["raw"]["cycle_path"]
        assert "raw" in cycle_gate.details
        assert "cycle_path" in cycle_gate.details["raw"]
    
    def test_warn_threshold(self):
        """Test with WARN as failure threshold."""
        gates = [
            self.create_gate("g1", GateStatus.WARN),
            self.create_gate("g2", GateStatus.REJECT, depends_on=["g1"]),
            self.create_gate("g3", GateStatus.WARN, depends_on=["g2"]),
        ]
        
        # Default threshold is REJECT, so only g2 is failed
        result_default = compute_gate_dependency_flags(gates)
        g1_default = next(g for g in result_default if g.gate_id == "g1")
        g2_default = next(g for g in result_default if g.gate_id == "g2")
        g3_default = next(g for g in result_default if g.gate_id == "g3")
        
        assert not g1_default.is_primary_fail  # WARN not failed at REJECT threshold
        assert g2_default.is_primary_fail  # REJECT is failed
        assert not g3_default.is_primary_fail  # WARN not failed
        
        # With WARN threshold, both WARN and REJECT are failures
        result_warn = compute_gate_dependency_flags(gates, fail_threshold=GateStatus.WARN)
        g1_warn = next(g for g in result_warn if g.gate_id == "g1")
        g2_warn = next(g for g in result_warn if g.gate_id == "g2")
        g3_warn = next(g for g in result_warn if g.gate_id == "g3")
        
        assert g1_warn.is_primary_fail  # WARN is failed at WARN threshold
        assert not g2_warn.is_primary_fail and g2_warn.is_propagated_fail  # Depends on g1
        assert not g3_warn.is_primary_fail and g3_warn.is_propagated_fail  # Depends on g2
    
    def test_integration_with_create_gate_summary(self):
        """Test dependency computation integrated with gate summary creation."""
        gates = [
            self.create_gate("g1", GateStatus.REJECT),
            self.create_gate("g2", GateStatus.REJECT, depends_on=["g1"]),
            self.create_gate("g3", GateStatus.PASS),
        ]
        
        # Create summary with dependency computation
        summary = create_gate_summary_from_gates(
            gates=gates,
            source="test",
            evaluator="test",
            compute_dependencies=True,
        )
        
        assert len(summary.gates) == 3
        
        # Find gates in summary
        g1 = next(g for g in summary.gates if g.gate_id == "g1")
        g2 = next(g for g in summary.gates if g.gate_id == "g2")
        g3 = next(g for g in summary.gates if g.gate_id == "g3")
        
        # Dependency flags should be computed
        assert g1.is_primary_fail and not g1.is_propagated_fail
        assert not g2.is_primary_fail and g2.is_propagated_fail
        assert not g3.is_primary_fail and not g3.is_propagated_fail
    
    def test_create_gate_summary_without_dependencies(self):
        """Test gate summary creation without dependency computation."""
        gates = [
            self.create_gate("g1", GateStatus.REJECT),
            self.create_gate("g2", GateStatus.REJECT, depends_on=["g1"]),
        ]
        
        # Create summary without dependency computation
        summary = create_gate_summary_from_gates(
            gates=gates,
            source="test",
            evaluator="test",
            compute_dependencies=False,
        )
        
        # Dependency flags should not be computed (default values)
        g1 = next(g for g in summary.gates if g.gate_id == "g1")
        g2 = next(g for g in summary.gates if g.gate_id == "g2")
        
        assert not g1.is_primary_fail and not g1.is_propagated_fail
        assert not g2.is_primary_fail and not g2.is_propagated_fail
    
    def test_missing_dependency(self):
        """Test gates with dependencies to non-existent gates."""
        gates = [
            self.create_gate("g1", GateStatus.REJECT, depends_on=["missing"]),
            self.create_gate("g2", GateStatus.REJECT),
        ]
        
        result = compute_gate_dependency_flags(gates)
        
        g1 = next(g for g in result if g.gate_id == "g1")
        g2 = next(g for g in result if g.gate_id == "g2")
        
        # g1 depends on missing gate, but missing gate is not failed
        # So g1 should be primary fail
        assert g1.is_primary_fail and not g1.is_propagated_fail
        
        # g2 is independent primary fail
        assert g2.is_primary_fail and not g2.is_propagated_fail


class TestGateDependencyGoldenFixtures:
    """Test golden fixtures for gate dependency graph."""
    
    def test_golden_fixture_structure(self):
        """Verify golden fixture has expected structure."""
        gates = [
            GateItemV1(
                gate_id="data_alignment",
                gate_name="Data Alignment",
                status=GateStatus.REJECT,
                message="Data misaligned",
                reason_codes=["DATA_MISALIGNED"],
                depends_on=[],  # No dependencies
                is_primary_fail=True,
                is_propagated_fail=False,
                evaluated_at_utc="2026-01-17T12:00:00Z",
                evaluator="test",
            ),
            GateItemV1(
                gate_id="correlation_threshold",
                gate_name="Correlation Threshold",
                status=GateStatus.REJECT,
                message="Correlation exceeds threshold",
                reason_codes=["CORR_0.8_EXCEEDED"],
                depends_on=["data_alignment"],  # Depends on failed gate
                is_primary_fail=False,
                is_propagated_fail=True,
                evaluated_at_utc="2026-01-17T12:00:00Z",
                evaluator="test",
            ),
        ]
        
        # Verify structure
        for gate in gates:
            data = gate.model_dump()
            assert "gate_id" in data
            assert "gate_name" in data
            assert "status" in data
            assert "depends_on" in data
            assert "is_primary_fail" in data
            assert "is_propagated_fail" in data
            
            # depends_on should be list of strings
            assert isinstance(data["depends_on"], list)
            if data["depends_on"]:
                assert all(isinstance(dep, str) for dep in data["depends_on"])
            
            # Flags should be booleans
            assert isinstance(data["is_primary_fail"], bool)
            assert isinstance(data["is_propagated_fail"], bool)
            
            # Mutual exclusion: cannot be both primary and propagated
            if data["is_primary_fail"]:
                assert not data["is_propagated_fail"]