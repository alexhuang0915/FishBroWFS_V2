import pytest
import yaml
from portfolio.loader import load_portfolio_spec

def test_loader_preserves_types(tmp_path):
    """L3-3: Verify portfolio loader preserves int/bool/float types."""
    p = tmp_path / "test_portfolio.yaml"
    
    content = """
portfolio_id: test_port
version: "1.0"
legs:
  - leg_id: leg1
    symbol: TEST
    timeframe_min: 60
    session_profile: 24/7
    strategy_id: strat1
    strategy_version: v1
    params:
      int_param: 20
      float_param: 1.5
      bool_param: true
      str_param: "value"
"""
    p.write_text(content)
    
    spec = load_portfolio_spec(p)
    leg = spec.legs[0]
    
    # Assert types are preserved
    assert isinstance(leg.params["int_param"], int)
    assert leg.params["int_param"] == 20
    
    assert isinstance(leg.params["float_param"], float)
    assert leg.params["float_param"] == 1.5
    
    assert isinstance(leg.params["bool_param"], bool)
    assert leg.params["bool_param"] is True
    
    assert isinstance(leg.params["str_param"], str)
    assert leg.params["str_param"] == "value"
