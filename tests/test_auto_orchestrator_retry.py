import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from control.auto.orchestrator import _run_job_batch_with_retry

class TestAutoOrchestratorRetry(unittest.TestCase):
    def test_run_job_batch_with_retry(self):
        job_configs = [("TEST_JOB", {"param": 1})]
        
        # First attempt: job fails with ORPHANED
        # Second attempt: job succeeds
        
        with patch("control.auto.orchestrator.submit") as mock_submit, \
             patch("control.auto.orchestrator._wait_jobs") as mock_wait:
            
            mock_submit.side_effect = ["job1_initial", "job1_retry"]
            
            # mock_wait.side_effect = [
            #     {"job1_initial": "ORPHANED"},
            #     {"job1_retry": "SUCCEEDED"}
            # ]
            # The current implementation of _run_job_batch_with_retry 
            # updates final_states in each attempt.
            
            def mock_wait_impl(job_ids, **kwargs):
                if "job1_initial" in job_ids:
                    return {"job1_initial": "ORPHANED"}
                if "job1_retry" in job_ids:
                    return {"job1_retry": "SUCCEEDED"}
                return {}
            
            mock_wait.side_effect = mock_wait_impl

            final_states, retry_log = _run_job_batch_with_retry(
                db_path=Path("dummy.db"),
                artifacts_root=Path("dummy_artifacts"),
                max_workers=1,
                timeout_sec=None,
                job_configs=job_configs,
                max_retries=1
            )
            
            self.assertEqual(final_states["job1_initial"], "ORPHANED")
            self.assertEqual(final_states["job1_retry"], "SUCCEEDED")
            self.assertEqual(len(retry_log), 1)
            self.assertEqual(retry_log[0]["action"], "retry")
            self.assertEqual(retry_log[0]["job_id"], "job1_initial")
            self.assertEqual(mock_submit.call_count, 2)

    def test_no_retry_on_failure(self):
        job_configs = [("TEST_JOB", {"param": 1})]
        
        with patch("control.auto.orchestrator.submit") as mock_submit, \
             patch("control.auto.orchestrator._wait_jobs") as mock_wait:
            
            mock_submit.side_effect = ["job1"]
            mock_wait.return_value = {"job1": "FAILED"}

            final_states, retry_log = _run_job_batch_with_retry(
                db_path=Path("dummy.db"),
                artifacts_root=Path("dummy_artifacts"),
                max_workers=1,
                timeout_sec=None,
                job_configs=job_configs,
                max_retries=1
            )
            
            self.assertEqual(final_states["job1"], "FAILED")
            self.assertEqual(len(retry_log), 0)
            self.assertEqual(mock_submit.call_count, 1)

if __name__ == "__main__":
    unittest.main()
