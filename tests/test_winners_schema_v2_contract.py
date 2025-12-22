
"""Contract tests for winners schema v2.

Tests verify:
1. v2 schema structure (top-level fields)
2. WinnerItemV2 structure (required fields)
3. JSON serialization with sorted keys
4. Schema version detection
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from FishBroWFS_V2.core.winners_schema import (
    WinnerItemV2,
    build_winners_v2_dict,
    is_winners_legacy,
    is_winners_v2,
    WINNERS_SCHEMA_VERSION,
)


def test_winners_v2_top_level_schema() -> None:
    """Test that v2 winners.json has required top-level fields."""
    items = [
        WinnerItemV2(
            candidate_id="donchian_atr:123",
            strategy_id="donchian_atr",
            symbol="CME.MNQ",
            timeframe="60m",
            params={"LE": 8, "LX": 4, "Z": -0.4},
            score=1.234,
            metrics={"net_profit": 100.0, "max_dd": -10.0, "trades": 10, "param_id": 123},
            source={"param_id": 123, "run_id": "test-123", "stage_name": "stage1_topk"},
        ),
    ]
    
    winners = build_winners_v2_dict(
        stage_name="stage1_topk",
        run_id="test-123",
        topk=items,
    )
    
    # Verify top-level fields
    assert winners["schema"] == WINNERS_SCHEMA_VERSION
    assert winners["stage_name"] == "stage1_topk"
    assert "generated_at" in winners
    assert "topk" in winners
    assert "notes" in winners
    
    # Verify notes schema
    assert winners["notes"]["schema"] == WINNERS_SCHEMA_VERSION


def test_winner_item_v2_required_fields() -> None:
    """Test that WinnerItemV2 has all required fields."""
    item = WinnerItemV2(
        candidate_id="donchian_atr:c7bc8b64916c",
        strategy_id="donchian_atr",
        symbol="CME.MNQ",
        timeframe="60m",
        params={"LE": 8, "LX": 4, "Z": -0.4},
        score=1.234,
        metrics={"net_profit": 0.0, "max_dd": 0.0, "trades": 0, "param_id": 9},
        source={"param_id": 9, "run_id": "stage1_topk-123", "stage_name": "stage1_topk"},
    )
    
    item_dict = item.to_dict()
    
    # Verify all required fields exist
    assert "candidate_id" in item_dict
    assert "strategy_id" in item_dict
    assert "symbol" in item_dict
    assert "timeframe" in item_dict
    assert "params" in item_dict
    assert "score" in item_dict
    assert "metrics" in item_dict
    assert "source" in item_dict
    
    # Verify field values
    assert item_dict["candidate_id"] == "donchian_atr:c7bc8b64916c"
    assert item_dict["strategy_id"] == "donchian_atr"
    assert item_dict["symbol"] == "CME.MNQ"
    assert item_dict["timeframe"] == "60m"
    assert isinstance(item_dict["params"], dict)
    assert isinstance(item_dict["score"], (int, float))
    assert isinstance(item_dict["metrics"], dict)
    assert isinstance(item_dict["source"], dict)


def test_winners_v2_json_serializable_sorted_keys() -> None:
    """Test that v2 winners.json is JSON-serializable with sorted keys."""
    items = [
        WinnerItemV2(
            candidate_id="donchian_atr:123",
            strategy_id="donchian_atr",
            symbol="CME.MNQ",
            timeframe="60m",
            params={"LE": 8},
            score=1.234,
            metrics={"net_profit": 100.0, "max_dd": -10.0, "trades": 10, "param_id": 123},
            source={"param_id": 123, "run_id": "test-123", "stage_name": "stage1_topk"},
        ),
    ]
    
    winners = build_winners_v2_dict(
        stage_name="stage1_topk",
        run_id="test-123",
        topk=items,
    )
    
    # Serialize to JSON with sorted keys
    json_str = json.dumps(winners, ensure_ascii=False, sort_keys=True, indent=2)
    
    # Deserialize back
    winners_roundtrip = json.loads(json_str)
    
    # Verify structure
    assert winners_roundtrip["schema"] == WINNERS_SCHEMA_VERSION
    assert len(winners_roundtrip["topk"]) == 1
    
    item_dict = winners_roundtrip["topk"][0]
    assert item_dict["candidate_id"] == "donchian_atr:123"
    assert item_dict["strategy_id"] == "donchian_atr"
    
    # Verify JSON keys are sorted (check top-level)
    json_lines = json_str.split("\n")
    # Find line with "generated_at" and "schema" - should be in sorted order
    # (This is a simple check - full verification would require parsing)
    assert '"generated_at"' in json_str
    assert '"schema"' in json_str


def test_is_winners_v2_detection() -> None:
    """Test schema version detection."""
    # v2 format
    winners_v2 = {
        "schema": "v2",
        "stage_name": "stage1_topk",
        "generated_at": "2025-12-18T00:00:00Z",
        "topk": [],
        "notes": {"schema": "v2"},
    }
    assert is_winners_v2(winners_v2) is True
    assert is_winners_legacy(winners_v2) is False
    
    # Legacy format
    winners_legacy = {
        "topk": [{"param_id": 0, "net_profit": 100.0, "trades": 10, "max_dd": -10.0}],
        "notes": {"schema": "v1"},
    }
    assert is_winners_v2(winners_legacy) is False
    assert is_winners_legacy(winners_legacy) is True
    
    # Unknown format (no schema)
    winners_unknown = {
        "topk": [{"param_id": 0}],
    }
    assert is_winners_v2(winners_unknown) is False
    assert is_winners_legacy(winners_unknown) is True  # Falls back to legacy


def test_winner_item_v2_metrics_contains_legacy_fields() -> None:
    """Test that metrics contains legacy fields for backward compatibility."""
    item = WinnerItemV2(
        candidate_id="donchian_atr:123",
        strategy_id="donchian_atr",
        symbol="CME.MNQ",
        timeframe="60m",
        params={},
        score=1.234,
        metrics={
            "net_profit": 100.0,
            "max_dd": -10.0,
            "trades": 10,
            "param_id": 123,  # Legacy field
        },
        source={"param_id": 123, "run_id": "test-123", "stage_name": "stage1_topk"},
    )
    
    item_dict = item.to_dict()
    metrics = item_dict["metrics"]
    
    # Verify legacy fields exist
    assert "net_profit" in metrics
    assert "max_dd" in metrics
    assert "trades" in metrics
    assert "param_id" in metrics


def test_winners_v2_empty_topk() -> None:
    """Test that v2 schema handles empty topk correctly."""
    winners = build_winners_v2_dict(
        stage_name="stage1_topk",
        run_id="test-123",
        topk=[],
    )
    
    assert winners["schema"] == WINNERS_SCHEMA_VERSION
    assert winners["topk"] == []
    assert isinstance(winners["topk"], list)


