"""
Test pre-flight admission policies.
"""
import tempfile
from pathlib import Path
import json

from control.supervisor.admission import AdmissionController
from control.supervisor.db import SupervisorDB
from control.supervisor.models import JobSpec


def test_duplicate_fingerprint_policy():
    """Test check_duplicate_fingerprint policy."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    try:
        db = SupervisorDB(db_path)
        controller = AdmissionController(db)
        
        # First job should pass
        payload1 = {"strategy_id": "test", "timeframe": 60}
        bundle1 = controller.check("RUN_RESEARCH_V2", payload1)
        
        duplicate_check = next(
            c for c in bundle1.pre_flight_checks 
            if c.policy_name == "check_duplicate_fingerprint"
        )
        assert duplicate_check.passed, "First job should pass duplicate check"
        
        # Submit the job (simulate)
        spec = JobSpec(job_type="RUN_RESEARCH_V2", params=payload1)
        from contracts.supervisor.evidence_schemas import stable_params_hash
        params_hash = stable_params_hash(payload1)
        db.submit_job(spec, params_hash=params_hash, state="QUEUED")
        
        # Second identical job should fail
        payload2 = payload1.copy()  # Same payload
        bundle2 = controller.check("RUN_RESEARCH_V2", payload2)
        
        duplicate_check2 = next(
            c for c in bundle2.pre_flight_checks 
            if c.policy_name == "check_duplicate_fingerprint"
        )
        assert not duplicate_check2.passed, "Duplicate job should fail"
        assert "Duplicate" in duplicate_check2.message
        
        # Different payload should pass
        payload3 = {"strategy_id": "test", "timeframe": 30}  # Different timeframe
        bundle3 = controller.check("RUN_RESEARCH_V2", payload3)
        
        duplicate_check3 = next(
            c for c in bundle3.pre_flight_checks 
            if c.policy_name == "check_duplicate_fingerprint"
        )
        assert duplicate_check3.passed, "Different payload should pass"
        
        print("✓ Duplicate fingerprint policy test passed")
        
    finally:
        db_path.unlink()


def test_timeframe_allowed_policy():
    """Test check_timeframe_allowed policy."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    try:
        db = SupervisorDB(db_path)
        controller = AdmissionController(db)
        
        # Test allowed timeframes
        allowed = [15, 30, 60, 120, 240]
        for timeframe in allowed:
            payload = {"timeframe": timeframe}
            bundle = controller.check("RUN_RESEARCH_V2", payload)
            
            timeframe_check = next(
                c for c in bundle.pre_flight_checks 
                if c.policy_name == "check_timeframe_allowed"
            )
            assert timeframe_check.passed, f"Timeframe {timeframe} should be allowed"
        
        # Test disallowed timeframe
        payload = {"timeframe": 90}
        bundle = controller.check("RUN_RESEARCH_V2", payload)
        
        timeframe_check = next(
            c for c in bundle.pre_flight_checks 
            if c.policy_name == "check_timeframe_allowed"
        )
        assert not timeframe_check.passed, "Timeframe 90 should not be allowed"
        assert "not allowed" in timeframe_check.message.lower()
        
        # Test job type without timeframe requirement
        payload = {"other": "param"}
        bundle = controller.check("BUILD_PORTFOLIO_V2", payload)
        
        timeframe_check = next(
            c for c in bundle.pre_flight_checks 
            if c.policy_name == "check_timeframe_allowed"
        )
        assert timeframe_check.passed, "Non-timeframe job type should pass"
        
        print("✓ Timeframe allowed policy test passed")
        
    finally:
        db_path.unlink()


def test_season_format_policy():
    """Test check_season_format policy."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    try:
        db = SupervisorDB(db_path)
        controller = AdmissionController(db)
        
        # Test valid seasons
        valid_seasons = ["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1"]
        for season in valid_seasons:
            payload = {"season": season}
            bundle = controller.check("RUN_FREEZE_V2", payload)
            
            season_check = next(
                c for c in bundle.pre_flight_checks 
                if c.policy_name == "check_season_format"
            )
            assert season_check.passed, f"Season {season} should be valid"
        
        # Test invalid seasons
        invalid_seasons = [
            "2024Q0",  # Invalid quarter
            "2024Q5",  # Invalid quarter
            "2024q1",  # Lowercase
            "2024-Q1",  # Wrong format
            "24Q1",    # Short year
            "2024Q",   # Missing quarter number
        ]
        for season in invalid_seasons:
            payload = {"season": season}
            bundle = controller.check("RUN_FREEZE_V2", payload)
            
            season_check = next(
                c for c in bundle.pre_flight_checks 
                if c.policy_name == "check_season_format"
            )
            assert not season_check.passed, f"Season {season} should be invalid"
            assert "format" in season_check.message.lower()
        
        # Test job type without season requirement
        payload = {"other": "param"}
        bundle = controller.check("RUN_RESEARCH_V2", payload)
        
        season_check = next(
            c for c in bundle.pre_flight_checks 
            if c.policy_name == "check_season_format"
        )
        assert season_check.passed, "Non-season job type should pass"
        
        print("✓ Season format policy test passed")
        
    finally:
        db_path.unlink()


def test_admission_controller_integration():
    """Test full admission controller integration."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    try:
        db = SupervisorDB(db_path)
        controller = AdmissionController(db)
        
        # Test job that should pass all policies
        payload = {
            "strategy_id": "test",
            "timeframe": 60,
            "season": "2024Q1"
        }
        bundle = controller.check("RUN_FREEZE_V2", payload)
        
        assert len(bundle.pre_flight_checks) == 3
        all_passed = all(check.passed for check in bundle.pre_flight_checks)
        assert all_passed, "All checks should pass for valid payload"
        assert bundle.downstream_admissible
        
        # Test job that should fail (duplicate + invalid timeframe)
        spec = JobSpec(job_type="RUN_FREEZE_V2", params=payload)
        from contracts.supervisor.evidence_schemas import stable_params_hash
        params_hash = stable_params_hash(payload)
        db.submit_job(spec, params_hash=params_hash, state="QUEUED")
        
        # Same payload should fail duplicate check
        bundle2 = controller.check("RUN_FREEZE_V2", payload)
        assert not bundle2.downstream_admissible
        
        failed_checks = [c for c in bundle2.pre_flight_checks if not c.passed]
        assert len(failed_checks) >= 1, "Should have at least one failed check"
        
        print("✓ Admission controller integration test passed")
        
    finally:
        db_path.unlink()


if __name__ == "__main__":
    test_duplicate_fingerprint_policy()
    test_timeframe_allowed_policy()
    test_season_format_policy()
    test_admission_controller_integration()
    print("All pre-flight policy tests passed!")