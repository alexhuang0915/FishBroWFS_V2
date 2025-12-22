
"""Unit tests for param_grid module (Phase 13)."""

import pytest
from FishBroWFS_V2.control.param_grid import GridMode, ParamGridSpec, values_for_param, count_for_param, validate_grid_for_param


def test_grid_mode_enum():
    """GridMode enum values."""
    assert GridMode.SINGLE.value == "single"
    assert GridMode.RANGE.value == "range"
    assert GridMode.MULTI.value == "multi"


def test_param_grid_spec_single():
    """Single mode spec."""
    spec = ParamGridSpec(mode=GridMode.SINGLE, single_value=42)
    assert spec.mode == GridMode.SINGLE
    assert spec.single_value == 42
    assert spec.range_start is None
    assert spec.range_end is None
    assert spec.range_step is None
    assert spec.multi_values is None


def test_param_grid_spec_range():
    """Range mode spec."""
    spec = ParamGridSpec(mode=GridMode.RANGE, range_start=0, range_end=10, range_step=2)
    assert spec.mode == GridMode.RANGE
    assert spec.range_start == 0
    assert spec.range_end == 10
    assert spec.range_step == 2
    assert spec.single_value is None
    assert spec.multi_values is None


def test_param_grid_spec_multi():
    """Multi mode spec."""
    spec = ParamGridSpec(mode=GridMode.MULTI, multi_values=[1, 2, 3])
    assert spec.mode == GridMode.MULTI
    assert spec.multi_values == [1, 2, 3]
    assert spec.single_value is None
    assert spec.range_start is None


def test_values_for_param_single():
    """Single mode yields single value."""
    spec = ParamGridSpec(mode=GridMode.SINGLE, single_value=5.5)
    vals = list(values_for_param(spec))
    assert vals == [5.5]


def test_values_for_param_range_int():
    """Range mode with integer step."""
    spec = ParamGridSpec(mode=GridMode.RANGE, range_start=0, range_end=5, range_step=1)
    vals = list(values_for_param(spec))
    assert vals == [0, 1, 2, 3, 4, 5]


def test_values_for_param_range_float():
    """Range mode with float step."""
    spec = ParamGridSpec(mode=GridMode.RANGE, range_start=0.0, range_end=1.0, range_step=0.5)
    vals = list(values_for_param(spec))
    assert vals == [0.0, 0.5, 1.0]


def test_values_for_param_multi():
    """Multi mode yields list of values."""
    spec = ParamGridSpec(mode=GridMode.MULTI, multi_values=["a", "b", "c"])
    vals = list(values_for_param(spec))
    assert vals == ["a", "b", "c"]


def test_count_for_param():
    """Count of values."""
    spec_single = ParamGridSpec(mode=GridMode.SINGLE, single_value=1)
    assert count_for_param(spec_single) == 1
    
    spec_range = ParamGridSpec(mode=GridMode.RANGE, range_start=0, range_end=10, range_step=2)
    # 0,2,4,6,8,10 => 6 values
    assert count_for_param(spec_range) == 6
    
    spec_multi = ParamGridSpec(mode=GridMode.MULTI, multi_values=[1, 2, 3, 4])
    assert count_for_param(spec_multi) == 4


def test_validate_grid_for_param_single_ok():
    """Single mode validation passes."""
    spec = ParamGridSpec(mode=GridMode.SINGLE, single_value=100)
    validate_grid_for_param(spec, "int", min=0, max=200)
    # No exception


def test_validate_grid_for_param_single_out_of_range():
    """Single mode value out of range raises."""
    spec = ParamGridSpec(mode=GridMode.SINGLE, single_value=300)
    with pytest.raises(ValueError, match="out of range"):
        validate_grid_for_param(spec, "int", min=0, max=200)


def test_validate_grid_for_param_range_invalid_step():
    """Range mode with zero step raises."""
    spec = ParamGridSpec(mode=GridMode.RANGE, range_start=0, range_end=10, range_step=0)
    with pytest.raises(ValueError, match="step must be positive"):
        validate_grid_for_param(spec, "int", min=0, max=100)


def test_validate_grid_for_param_range_start_gt_end():
    """Range start > end raises."""
    spec = ParamGridSpec(mode=GridMode.RANGE, range_start=10, range_end=0, range_step=1)
    with pytest.raises(ValueError, match="start <= end"):
        validate_grid_for_param(spec, "int", min=0, max=100)


def test_validate_grid_for_param_multi_empty():
    """Multi mode with empty list raises."""
    spec = ParamGridSpec(mode=GridMode.MULTI, multi_values=[])
    with pytest.raises(ValueError, match="at least one value"):
        validate_grid_for_param(spec, "int", min=0, max=100)


def test_validate_grid_for_param_multi_duplicates():
    """Multi mode with duplicates raises."""
    spec = ParamGridSpec(mode=GridMode.MULTI, multi_values=[1, 2, 2, 3])
    with pytest.raises(ValueError, match="duplicate values"):
        validate_grid_for_param(spec, "int", min=0, max=100)


def test_validate_grid_for_param_enum():
    """Enum type validation passes if value in choices."""
    spec = ParamGridSpec(mode=GridMode.SINGLE, single_value="buy")
    validate_grid_for_param(spec, "enum", choices=["buy", "sell", "hold"])
    # No exception


def test_validate_grid_for_param_enum_invalid():
    """Enum value not in choices raises."""
    spec = ParamGridSpec(mode=GridMode.SINGLE, single_value="invalid")
    with pytest.raises(ValueError, match="not in choices"):
        validate_grid_for_param(spec, "enum", choices=["buy", "sell"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


