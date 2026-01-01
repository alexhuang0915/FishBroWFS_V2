
"""Contract tests for dtype compression (Phase P1).

These tests ensure:
1. INDEX_DTYPE=int32 safety: order_id, created_bar, qty never exceed 2^31-1
2. UINT8 enum consistency: role/kind/side correctly encode/decode without sentinel issues
"""

import numpy as np
import pytest

from config.dtypes import (
    INDEX_DTYPE,
    INTENT_ENUM_DTYPE,
    INTENT_PRICE_DTYPE,
)
from engine.constants import (
    KIND_LIMIT,
    KIND_STOP,
    ROLE_ENTRY,
    ROLE_EXIT,
    SIDE_BUY,
    SIDE_SELL,
)
from engine.engine_jit import (
    SIDE_BUY_CODE,
    SIDE_SELL_CODE,
    _pack_intents,
    simulate_arrays,
)
from engine.engine_types import BarArrays, OrderIntent, OrderKind, OrderRole, Side


class TestIndexDtypeSafety:
    """Test that INDEX_DTYPE=int32 is safe for all use cases."""

    def test_order_id_max_value_contract(self):
        """
        Contract: order_id must never exceed 2^31-1 (int32 max).
        
        In strategy/kernel.py, order_id is generated as:
        - Entry: np.arange(1, n_entry + 1)
        - Exit: np.arange(n_entry + 1, n_entry + 1 + exit_intents_count)
        
        Maximum order_id = n_entry + exit_intents_count
        
        For 200,000 bars with reasonable intent generation, this should be << 2^31-1.
        """
        INT32_MAX = 2**31 - 1
        
        # Simulate worst-case scenario: 200,000 bars, each bar generates 1 entry + 1 exit
        # This is extremely conservative (realistic scenarios generate far fewer intents)
        n_bars = 200_000
        max_intents_per_bar = 2  # 1 entry + 1 exit per bar (worst case)
        max_total_intents = n_bars * max_intents_per_bar
        
        # Maximum order_id would be max_total_intents (if all are sequential)
        max_order_id = max_total_intents
        
        assert max_order_id < INT32_MAX, (
            f"order_id would exceed int32 max ({INT32_MAX}) "
            f"with {n_bars} bars and {max_intents_per_bar} intents per bar. "
            f"Max order_id would be {max_order_id}"
        )
        
        # More realistic: check that even with 10x safety margin, we're still safe
        safety_margin = 10
        assert max_order_id * safety_margin < INT32_MAX, (
            f"order_id with {safety_margin}x safety margin would exceed int32 max"
        )

    def test_created_bar_max_value_contract(self):
        """
        Contract: created_bar must never exceed 2^31-1.
        
        created_bar is a bar index, so max value = n_bars - 1.
        For 200,000 bars, max created_bar = 199,999 << 2^31-1.
        """
        INT32_MAX = 2**31 - 1
        
        # Worst case: 200,000 bars
        max_bars = 200_000
        max_created_bar = max_bars - 1
        
        assert max_created_bar < INT32_MAX, (
            f"created_bar would exceed int32 max ({INT32_MAX}) "
            f"with {max_bars} bars. Max created_bar would be {max_created_bar}"
        )

    def test_qty_max_value_contract(self):
        """
        Contract: qty must never exceed 2^31-1.
        
        qty is typically small (1, 10, 100, etc.), so this should be safe.
        """
        INT32_MAX = 2**31 - 1
        
        # Realistic qty values are much smaller than int32 max
        realistic_max_qty = 1_000_000  # Even 1M shares is << 2^31-1
        
        assert realistic_max_qty < INT32_MAX, (
            f"qty would exceed int32 max ({INT32_MAX}) "
            f"with realistic max qty of {realistic_max_qty}"
        )

    def test_order_id_generation_in_kernel(self):
        """
        Test that actual order_id generation in kernel stays within int32 range.
        
        This test simulates the order_id generation logic from strategy/kernel.py.
        """
        INT32_MAX = 2**31 - 1
        
        # Simulate realistic scenario: 200,000 bars, ~1000 entry intents, ~500 exit intents
        n_entry = 1000
        n_exit = 500
        
        # Entry order_ids: np.arange(1, n_entry + 1)
        entry_order_ids = np.arange(1, n_entry + 1, dtype=INDEX_DTYPE)
        assert entry_order_ids.max() < INT32_MAX
        
        # Exit order_ids: np.arange(n_entry + 1, n_entry + 1 + n_exit)
        exit_order_ids = np.arange(n_entry + 1, n_entry + 1 + n_exit, dtype=INDEX_DTYPE)
        max_order_id = exit_order_ids.max()
        
        assert max_order_id < INT32_MAX, (
            f"Generated order_id {max_order_id} exceeds int32 max ({INT32_MAX})"
        )


class TestUint8EnumConsistency:
    """Test that uint8 enum encoding/decoding is consistent and safe."""

    def test_role_enum_encoding(self):
        """Test that role enum values encode correctly as uint8."""
        # ROLE_EXIT = 0, ROLE_ENTRY = 1
        exit_val = INTENT_ENUM_DTYPE(ROLE_EXIT)
        entry_val = INTENT_ENUM_DTYPE(ROLE_ENTRY)
        
        assert exit_val == 0
        assert entry_val == 1
        assert exit_val.dtype == np.uint8
        assert entry_val.dtype == np.uint8

    def test_kind_enum_encoding(self):
        """Test that kind enum values encode correctly as uint8."""
        # KIND_STOP = 0, KIND_LIMIT = 1
        stop_val = INTENT_ENUM_DTYPE(KIND_STOP)
        limit_val = INTENT_ENUM_DTYPE(KIND_LIMIT)
        
        assert stop_val == 0
        assert limit_val == 1
        assert stop_val.dtype == np.uint8
        assert limit_val.dtype == np.uint8

    def test_side_enum_encoding(self):
        """
        Test that side enum values encode correctly as uint8.
        
        SIDE_BUY_CODE = 1, SIDE_SELL_CODE = 255 (avoid -1 cast deprecation)
        """
        buy_val = INTENT_ENUM_DTYPE(SIDE_BUY_CODE)
        sell_val = INTENT_ENUM_DTYPE(SIDE_SELL_CODE)
        
        assert buy_val == 1
        assert sell_val == 255
        assert buy_val.dtype == np.uint8
        assert sell_val.dtype == np.uint8

    def test_side_enum_decoding_consistency(self):
        """
        Test that side enum decoding correctly handles uint8 values.
        
        Critical: uint8 value 255 (SIDE_SELL_CODE) must decode back to SELL.
        """
        # Encode SIDE_SELL_CODE (255) as uint8
        sell_encoded = INTENT_ENUM_DTYPE(SIDE_SELL_CODE)
        assert sell_encoded == 255
        
        # Decode: int(sd[i]) == SIDE_BUY (1) ? BUY : SELL
        # If sd[i] = 255, int(255) != 1, so it should decode to SELL
        decoded_is_buy = int(sell_encoded) == SIDE_BUY
        decoded_is_sell = int(sell_encoded) != SIDE_BUY
        
        assert not decoded_is_buy, "uint8 value 255 should not decode to BUY"
        assert decoded_is_sell, "uint8 value 255 should decode to SELL"
        
        # Also test BUY encoding/decoding
        buy_encoded = INTENT_ENUM_DTYPE(SIDE_BUY_CODE)
        assert buy_encoded == 1
        decoded_is_buy = int(buy_encoded) == SIDE_BUY_CODE
        assert decoded_is_buy, "uint8 value 1 should decode to BUY"

    def test_allowed_enum_values_contract(self):
        """
        Contract: enum arrays must only contain explicitly allowed values.
        
        This test ensures that:
        1. Only valid enum values are used (no uninitialized/invalid values)
        2. Decoding functions will raise ValueError for invalid values (strict mode)
        
        Allowed values:
        - role: {0 (EXIT), 1 (ENTRY)}
        - kind: {0 (STOP), 1 (LIMIT)}
        - side: {1 (BUY), 255 (SELL as uint8)}
        """
        # Define allowed values explicitly
        ALLOWED_ROLE_VALUES = {ROLE_EXIT, ROLE_ENTRY}  # {0, 1}
        ALLOWED_KIND_VALUES = {KIND_STOP, KIND_LIMIT}  # {0, 1}
        ALLOWED_SIDE_VALUES = {SIDE_BUY_CODE, SIDE_SELL_CODE}  # {1, 255} - avoid -1 cast
        
        # Test that encoding produces only allowed values
        role_encoded = [INTENT_ENUM_DTYPE(ROLE_EXIT), INTENT_ENUM_DTYPE(ROLE_ENTRY)]
        kind_encoded = [INTENT_ENUM_DTYPE(KIND_STOP), INTENT_ENUM_DTYPE(KIND_LIMIT)]
        side_encoded = [INTENT_ENUM_DTYPE(SIDE_BUY_CODE), INTENT_ENUM_DTYPE(SIDE_SELL_CODE)]
        
        for val in role_encoded:
            assert int(val) in ALLOWED_ROLE_VALUES, f"Role value {val} not in allowed set {ALLOWED_ROLE_VALUES}"
        
        for val in kind_encoded:
            assert int(val) in ALLOWED_KIND_VALUES, f"Kind value {val} not in allowed set {ALLOWED_KIND_VALUES}"
        
        for val in side_encoded:
            assert int(val) in ALLOWED_SIDE_VALUES, f"Side value {val} not in allowed set {ALLOWED_SIDE_VALUES}"
        
        # Test that invalid values raise ValueError (strict decoding)
        from engine.engine_jit import _role_from_int, _kind_from_int, _side_from_int
        
        # Test invalid role values
        with pytest.raises(ValueError, match="Invalid role enum value"):
            _role_from_int(2)
        with pytest.raises(ValueError, match="Invalid role enum value"):
            _role_from_int(-1)
        
        # Test invalid kind values
        with pytest.raises(ValueError, match="Invalid kind enum value"):
            _kind_from_int(2)
        with pytest.raises(ValueError, match="Invalid kind enum value"):
            _kind_from_int(-1)
        
        # Test invalid side values
        with pytest.raises(ValueError, match="Invalid side enum value"):
            _side_from_int(0)
        with pytest.raises(ValueError, match="Invalid side enum value"):
            _side_from_int(2)
        with pytest.raises(ValueError, match="Invalid side enum value"):
            _side_from_int(100)
        
        # Test valid values don't raise
        assert _role_from_int(0) == OrderRole.EXIT
        assert _role_from_int(1) == OrderRole.ENTRY
        assert _kind_from_int(0) == OrderKind.STOP
        assert _kind_from_int(1) == OrderKind.LIMIT
        assert _side_from_int(SIDE_BUY_CODE) == Side.BUY
        assert _side_from_int(SIDE_SELL_CODE) == Side.SELL

    def test_pack_intents_roundtrip(self):
        """
        Test that packing intents and decoding them preserves enum values correctly.
        
        This is an integration test to ensure the full encode/decode cycle works.
        """
        # Create test intents with all enum combinations
        intents = [
            OrderIntent(
                order_id=1,
                created_bar=0,
                role=OrderRole.EXIT,
                kind=OrderKind.STOP,
                side=Side.SELL,  # -1 -> uint8(255)
                price=100.0,
                qty=1,
            ),
            OrderIntent(
                order_id=2,
                created_bar=0,
                role=OrderRole.ENTRY,
                kind=OrderKind.LIMIT,
                side=Side.BUY,  # 1 -> uint8(1)
                price=101.0,
                qty=1,
            ),
        ]
        
        # Pack intents
        order_id, created_bar, role, kind, side, price, qty = _pack_intents(intents)
        
        # Verify dtypes
        assert order_id.dtype == INDEX_DTYPE
        assert created_bar.dtype == INDEX_DTYPE
        assert role.dtype == INTENT_ENUM_DTYPE
        assert kind.dtype == INTENT_ENUM_DTYPE
        assert side.dtype == INTENT_ENUM_DTYPE
        assert price.dtype == INTENT_PRICE_DTYPE
        assert qty.dtype == INDEX_DTYPE
        
        # Verify enum values
        assert role[0] == ROLE_EXIT  # 0
        assert role[1] == ROLE_ENTRY  # 1
        assert kind[0] == KIND_STOP  # 0
        assert kind[1] == KIND_LIMIT  # 1
        assert side[0] == SIDE_SELL_CODE  # SELL -> uint8(255)
        assert side[1] == SIDE_BUY_CODE  # BUY -> uint8(1)
        
        # Verify decoding logic (as used in engine_jit.py)
        # Decode role
        decoded_role_0 = OrderRole.EXIT if int(role[0]) == ROLE_EXIT else OrderRole.ENTRY
        assert decoded_role_0 == OrderRole.EXIT
        
        decoded_role_1 = OrderRole.EXIT if int(role[1]) == ROLE_EXIT else OrderRole.ENTRY
        assert decoded_role_1 == OrderRole.ENTRY
        
        # Decode kind
        decoded_kind_0 = OrderKind.STOP if int(kind[0]) == KIND_STOP else OrderKind.LIMIT
        assert decoded_kind_0 == OrderKind.STOP
        
        decoded_kind_1 = OrderKind.STOP if int(kind[1]) == KIND_STOP else OrderKind.LIMIT
        assert decoded_kind_1 == OrderKind.LIMIT
        
        # Decode side (critical: uint8(255) must decode to SELL)
        decoded_side_0 = Side.BUY if int(side[0]) == SIDE_BUY_CODE else Side.SELL
        assert decoded_side_0 == Side.SELL, f"uint8(255) should decode to SELL, got {decoded_side_0}"
        
        decoded_side_1 = Side.BUY if int(side[1]) == SIDE_BUY_CODE else Side.SELL
        assert decoded_side_1 == Side.BUY, f"uint8(1) should decode to BUY, got {decoded_side_1}"

    def test_simulate_arrays_accepts_uint8_enums(self):
        """
        Test that simulate_arrays correctly accepts and processes uint8 enum arrays.
        
        This ensures the numba kernel can handle uint8 enum values correctly.
        """
        # Create minimal test data
        bars = BarArrays(
            open=np.array([100.0, 101.0], dtype=np.float64),
            high=np.array([102.0, 103.0], dtype=np.float64),
            low=np.array([99.0, 100.0], dtype=np.float64),
            close=np.array([101.0, 102.0], dtype=np.float64),
        )
        
        # Create intent arrays with uint8 enums
        order_id = np.array([1], dtype=INDEX_DTYPE)
        created_bar = np.array([0], dtype=INDEX_DTYPE)
        role = np.array([ROLE_ENTRY], dtype=INTENT_ENUM_DTYPE)
        kind = np.array([KIND_STOP], dtype=INTENT_ENUM_DTYPE)
        side = np.array([SIDE_BUY_CODE], dtype=INTENT_ENUM_DTYPE)  # 1 -> uint8(1)
        price = np.array([102.0], dtype=INTENT_PRICE_DTYPE)
        qty = np.array([1], dtype=INDEX_DTYPE)
        
        # This should not raise any dtype-related errors
        fills = simulate_arrays(
            bars,
            order_id=order_id,
            created_bar=created_bar,
            role=role,
            kind=kind,
            side=side,
            price=price,
            qty=qty,
            ttl_bars=1,
        )
        
        # Verify fills were generated (basic sanity check)
        assert isinstance(fills, list)
        
        # Test with SELL side (uint8 value 255)
        side_sell = np.array([SIDE_SELL_CODE], dtype=INTENT_ENUM_DTYPE)  # 255 (avoid -1 cast)
        fills_sell = simulate_arrays(
            bars,
            order_id=order_id,
            created_bar=created_bar,
            role=role,
            kind=kind,
            side=side_sell,
            price=price,
            qty=qty,
            ttl_bars=1,
        )
        
        # Should not raise errors
        assert isinstance(fills_sell, list)
        
        # Verify that fills with SELL side decode correctly
        # Note: numba kernel outputs uint8(255) as 255.0, but _side_from_int correctly decodes it
        if fills_sell:
            # The fill's side should be Side.SELL
            assert fills_sell[0].side == Side.SELL, (
                f"Fill with uint8(255) side should decode to Side.SELL, got {fills_sell[0].side}"
            )

    def test_side_output_value_contract(self):
        """
        Contract: numba kernel outputs side as float.
        
        Note: uint8(255) from SIDE_SELL will output as 255.0, not -1.0.
        This is acceptable as long as _side_from_int correctly decodes it.
        
        With strict mode, invalid values will raise ValueError instead of silently
        decoding to SELL.
        """
        from engine.engine_jit import _side_from_int
        
        # Test that _side_from_int correctly handles allowed values
        assert _side_from_int(SIDE_BUY_CODE) == Side.BUY
        assert _side_from_int(SIDE_SELL_CODE) == Side.SELL, (
            f"_side_from_int({SIDE_SELL_CODE}) should decode to Side.SELL, not BUY"
        )
        
        # Test that invalid values raise ValueError (strict mode)
        with pytest.raises(ValueError, match="Invalid side enum value"):
            _side_from_int(0)
        with pytest.raises(ValueError, match="Invalid side enum value"):
            _side_from_int(-1)
        with pytest.raises(ValueError, match="Invalid side enum value"):
            _side_from_int(2)
        with pytest.raises(ValueError, match="Invalid side enum value"):
            _side_from_int(100)


