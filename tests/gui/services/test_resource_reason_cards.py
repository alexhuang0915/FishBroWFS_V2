"""
Unit tests for Resource Reason Cards builder.
"""

import pytest

from gui.services.resource_status import (
    ResourceStatus,
    build_resource_reason_cards,
    RESOURCE_MEMORY_EXCEEDED,
    RESOURCE_WORKER_CRASH,
    RESOURCE_MISSING_ARTIFACT,
    RESOURCE_USAGE_ARTIFACT,
    DEFAULT_MEMORY_WARN_THRESHOLD_MB,
)


def test_missing_artifact_returns_one_card():
    """MISSING status → returns exactly 1 card with code=RESOURCE_MISSING_ARTIFACT."""
    status = ResourceStatus(
        status="MISSING",
        artifact_relpath=RESOURCE_USAGE_ARTIFACT,
        artifact_abspath="/tmp/test/resource_usage.json",
        message="Resource usage artifact not found",
        metrics={},
    )
    
    cards = build_resource_reason_cards(
        job_id="test-job",
        status=status,
        warn_memory_threshold_mb=DEFAULT_MEMORY_WARN_THRESHOLD_MB,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == RESOURCE_MISSING_ARTIFACT
    assert card.title == "Resource Usage Artifact Missing"
    assert card.severity == "WARN"
    assert card.why == "Resource usage artifact not produced by job"
    assert card.impact == "Resource consumption cannot be audited; potential OOM risks unknown"
    assert card.recommended_action == "Ensure job produces resource_usage.json or oom_gate_decision.json"
    assert card.evidence_artifact == RESOURCE_USAGE_ARTIFACT
    assert card.evidence_path == "$"
    assert card.action_target == "/tmp/test/resource_usage.json"


def test_memory_exceeded_returns_card():
    """WARN status with peak_memory_mb > limit_mb → includes MEMORY_EXCEEDED card."""
    status = ResourceStatus(
        status="WARN",
        artifact_relpath=RESOURCE_USAGE_ARTIFACT,
        artifact_abspath="/tmp/test/resource_usage.json",
        message="Peak memory 7000MB exceeded limit 6000MB",
        metrics={
            "peak_memory_mb": 7000,
            "limit_mb": 6000,
            "worker_crash": False,
        },
    )
    
    cards = build_resource_reason_cards(
        job_id="test-job",
        status=status,
        warn_memory_threshold_mb=DEFAULT_MEMORY_WARN_THRESHOLD_MB,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == RESOURCE_MEMORY_EXCEEDED
    assert card.title == "Memory Exceeded"
    assert card.severity == "WARN"
    assert card.why == "Peak memory usage 7000MB exceeded limit 6000MB"
    assert card.impact == "Job execution may terminate early or produce incomplete artifacts"
    assert card.recommended_action == "Reduce batch size, limit features/timeframes, or increase worker memory"
    assert card.evidence_artifact == RESOURCE_USAGE_ARTIFACT
    assert card.evidence_path == "$.peak_memory_mb"
    assert card.action_target == "/tmp/test/resource_usage.json"


def test_worker_crash_returns_card():
    """FAIL status with worker_crash True → includes WORKER_CRASH card."""
    status = ResourceStatus(
        status="FAIL",
        artifact_relpath=RESOURCE_USAGE_ARTIFACT,
        artifact_abspath="/tmp/test/resource_usage.json",
        message="Worker crashed due to resource exhaustion",
        metrics={
            "peak_memory_mb": 8000,
            "limit_mb": 6000,
            "worker_crash": True,
        },
    )
    
    cards = build_resource_reason_cards(
        job_id="test-job",
        status=status,
        warn_memory_threshold_mb=DEFAULT_MEMORY_WARN_THRESHOLD_MB,
    )
    
    # Should have 2 cards: MEMORY_EXCEEDED and WORKER_CRASH (deterministic order)
    assert len(cards) == 2
    assert cards[0].code == RESOURCE_MEMORY_EXCEEDED
    assert cards[1].code == RESOURCE_WORKER_CRASH
    assert cards[1].title == "Worker Crash (OOM-related)"
    assert cards[1].severity == "FAIL"
    assert cards[1].why == "Worker process crashed due to resource exhaustion"
    assert cards[1].impact == "Job execution terminated abruptly; results may be incomplete"
    assert cards[1].recommended_action == "Increase memory limits, reduce workload, or investigate memory leaks"
    assert cards[1].evidence_artifact == RESOURCE_USAGE_ARTIFACT
    assert cards[1].evidence_path == "$.worker_crash"
    assert cards[1].action_target == "/tmp/test/resource_usage.json"


def test_no_warnings_returns_empty_list():
    """OK status with metrics within limits → returns empty list."""
    status = ResourceStatus(
        status="OK",
        artifact_relpath=RESOURCE_USAGE_ARTIFACT,
        artifact_abspath="/tmp/test/resource_usage.json",
        message="Resource usage within limits",
        metrics={
            "peak_memory_mb": 4000,
            "limit_mb": 6000,
            "worker_crash": False,
        },
    )
    
    cards = build_resource_reason_cards(
        job_id="test-job",
        status=status,
        warn_memory_threshold_mb=DEFAULT_MEMORY_WARN_THRESHOLD_MB,
    )
    
    assert len(cards) == 0


def test_missing_artifact_skips_other_checks():
    """MISSING status should return only missing card, not check memory/crash."""
    status = ResourceStatus(
        status="MISSING",
        artifact_relpath=RESOURCE_USAGE_ARTIFACT,
        artifact_abspath="/tmp/test/resource_usage.json",
        message="Resource usage artifact not found",
        metrics={
            "peak_memory_mb": 9999,
            "limit_mb": 1000,
            "worker_crash": True,
        },
    )
    
    cards = build_resource_reason_cards(
        job_id="test-job",
        status=status,
        warn_memory_threshold_mb=DEFAULT_MEMORY_WARN_THRESHOLD_MB,
    )
    
    assert len(cards) == 1
    assert cards[0].code == RESOURCE_MISSING_ARTIFACT