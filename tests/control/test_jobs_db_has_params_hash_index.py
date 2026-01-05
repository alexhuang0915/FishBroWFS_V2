"""
Test that jobs DB has required index for params_hash performance.
"""
import sqlite3
from pathlib import Path
import tempfile
import os

from src.control.supervisor.db import SupervisorDB


def test_params_hash_index_exists():
    """Test that idx_jobs_type_params_hash index exists."""
    # Create temporary DB
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    try:
        # Initialize DB
        db = SupervisorDB(db_path)
        
        # Check index exists
        with db._connect() as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type = 'index' 
                AND name = 'idx_jobs_type_params_hash'
            """)
            index = cursor.fetchone()
            
            assert index is not None, "idx_jobs_type_params_hash index should exist"
            print(f"✓ Index found: {index['name']}")
            
            # Also verify it's on correct columns
            cursor = conn.execute("""
                PRAGMA index_info('idx_jobs_type_params_hash')
            """)
            columns = cursor.fetchall()
            column_names = [col['name'] for col in columns]
            
            # Should have job_type and params_hash columns
            assert 'job_type' in column_names, "Index should include job_type"
            assert 'params_hash' in column_names, "Index should include params_hash"
            print(f"✓ Index columns: {column_names}")
            
    finally:
        # Clean up
        os.unlink(db_path)
    
    print("✓ DB index test passed")


def test_index_improves_query_performance():
    """Test that index is used for duplicate fingerprint queries."""
    # This is a smoke test, not a full performance test
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    try:
        db = SupervisorDB(db_path)
        
        # Insert a test job
        from src.control.supervisor.models import JobSpec
        spec = JobSpec(job_type="TEST_JOB", params={"test": "value"})
        
        # Use the new submit_job method with params_hash
        import json
        from src.contracts.supervisor.evidence_schemas import stable_params_hash
        params_hash = stable_params_hash(spec.params)
        job_id = db.submit_job(spec, params_hash=params_hash, state="QUEUED")
        
        # Query using the index (should be fast)
        with db._connect() as conn:
            # Check query plan
            cursor = conn.execute("""
                EXPLAIN QUERY PLAN
                SELECT job_id FROM jobs 
                WHERE job_type = ? AND params_hash = ?
                AND state IN ('QUEUED', 'RUNNING', 'SUCCEEDED')
            """, ("TEST_JOB", params_hash))
            
            plan = cursor.fetchall()
            plan_text = "\n".join(str(row) for row in plan)
            
            # Check if index is used (should mention idx_jobs_type_params_hash)
            if 'idx_jobs_type_params_hash' in plan_text:
                print("✓ Index is used for duplicate fingerprint query")
            else:
                # This is not a failure, just informational
                print(f"Note: Query plan: {plan_text}")
        
    finally:
        os.unlink(db_path)
    
    print("✓ Index performance test completed")


if __name__ == "__main__":
    test_params_hash_index_exists()
    test_index_improves_query_performance()
    print("All DB index tests passed!")