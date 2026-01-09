#!/usr/bin/env python3
"""
Tests for the Phase 4-C Titanium Master Wrapper Generator.
"""

import pytest
import tempfile
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from deployment.master_wrapper.generator import (
    PowerLanguageStrategy,
    parse_powerlanguage,
    validate_strategy,
    isolate_namespace,
    MasterWrapperConfig,
    MasterWrapperGenerator,
    generate_master_wrapper,
)


def create_valid_strategy() -> str:
    """Create a valid PowerLanguage strategy for testing."""
    return """// Valid strategy without Set* syntax
Inputs:
    i_Len(18),
    i_Risk(0.5);

Vars:
    v_MA(0),
    v_Upper(0),
    v_Lower(0);

v_MA = Average(Close, i_Len);
v_Upper = Highest(High, i_Len);
v_Lower = Lowest(Low, i_Len);

If MarketPosition = 0 Then Begin
    If Close > v_Upper Then
        Buy Next Bar at Market;
    If Close < v_Lower Then
        SellShort Next Bar at Market;
End;

If MarketPosition > 0 Then Begin
    If Close < v_MA Then
        Sell Next Bar at Market;
End;

If MarketPosition < 0 Then Begin
    If Close > v_MA Then
        BuyToCover Next Bar at Market;
End;
"""


def create_invalid_strategy_with_set() -> str:
    """Create an invalid strategy with Set* syntax."""
    return """// Invalid strategy with SetStopLoss
Inputs:
    i_Len(20);

Vars:
    v_MA(0);

v_MA = Average(Close, i_Len);

If MarketPosition = 0 Then Begin
    If Close > v_MA Then
        Buy Next Bar at Market;
End;

SetStopLoss(100);  // FORBIDDEN
"""


def test_parse_powerlanguage():
    """Test parsing PowerLanguage source code."""
    source = create_valid_strategy()
    strategy = parse_powerlanguage(source, name="TestStrategy")
    
    assert strategy.name == "TestStrategy"
    assert len(strategy.inputs) == 2
    assert "i_Len" in strategy.inputs
    assert "i_Risk" in strategy.inputs
    assert len(strategy.vars) == 3
    assert not strategy.has_set_syntax
    assert not strategy.has_iog
    assert strategy.is_valid()


def test_parse_invalid_strategy():
    """Test parsing invalid strategy with Set* syntax."""
    source = create_invalid_strategy_with_set()
    strategy = parse_powerlanguage(source, name="InvalidStrategy")
    
    assert strategy.has_set_syntax
    assert not strategy.is_valid()


def test_validate_strategy():
    """Test strategy validation."""
    # Valid strategy
    valid_source = create_valid_strategy()
    valid_strategy = parse_powerlanguage(valid_source)
    is_valid, errors = validate_strategy(valid_strategy)
    
    assert is_valid
    assert len(errors) == 0
    
    # Invalid strategy
    invalid_source = create_invalid_strategy_with_set()
    invalid_strategy = parse_powerlanguage(invalid_source)
    is_valid, errors = validate_strategy(invalid_strategy)
    
    assert not is_valid
    assert len(errors) > 0
    assert any("Set*" in error for error in errors)


def test_isolate_namespace():
    """Test namespace isolation with suffix renaming."""
    source = """Vars:
    myVar(10),
    myArray[20];
    
myVar = myVar + 1;"""
    
    strategy = parse_powerlanguage(source, name="Test")
    strategy.vars = {"myVar": "10"}
    strategy.arrays = {"myArray": "20"}
    strategy.logic_blocks = ["myVar = myVar + 1;"]
    
    isolated = isolate_namespace(strategy, 1)
    
    # Check that variables are renamed
    assert "myVar_S01" in isolated.vars
    assert "myArray_S01" in isolated.arrays
    
    # Check that logic is updated
    assert "myVar_S01" in isolated.logic_blocks[0]


def test_generator_single_strategy():
    """Test generating a Master wrapper with a single strategy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "deployments" / "test123"
        
        # Create a valid strategy
        source = create_valid_strategy()
        strategy = parse_powerlanguage(source, name="TestStrategy")
        
        # Generate wrapper
        config = MasterWrapperConfig(
            quarter="2026Q1",
            deploy_id="test123",
            strategies=[strategy],
            output_dir=output_dir,
        )
        
        generator = MasterWrapperGenerator(config)
        parts = generator.generate()
        
        assert len(parts) == 1
        part = parts[0]
        
        # Check generated file
        assert part.part_name == "Titanium_Master_2026Q1_PartA.txt"
        assert len(part.strategies) == 1
        assert part.max_bars_back >= 50
        
        # Check file was written
        output_file = output_dir / part.part_name
        assert output_file.exists()
        
        content = output_file.read_text()
        assert "SetMaxBarsBack" in content
        assert "i_Strategy_ID" in content
        assert "i_Lots" in content
        assert "If i_Strategy_ID = 1 Then Begin" in content


def test_generator_multiple_strategies():
    """Test generating a Master wrapper with multiple strategies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "deployments" / "test456"
        
        # Create multiple strategies
        strategies = []
        for i in range(3):
            source = create_valid_strategy()
            strategy = parse_powerlanguage(source, name=f"Strategy{i+1}")
            strategies.append(strategy)
        
        # Generate wrapper
        config = MasterWrapperConfig(
            quarter="2026Q2",
            deploy_id="test456",
            strategies=strategies,
            output_dir=output_dir,
        )
        
        generator = MasterWrapperGenerator(config)
        parts = generator.generate()
        
        assert len(parts) == 1  # All 3 strategies fit in one part
        part = parts[0]
        
        # Check generated content
        content = (output_dir / part.part_name).read_text()
        assert "If i_Strategy_ID = 1 Then Begin" in content
        assert "Else If i_Strategy_ID = 2 Then Begin" in content
        assert "Else If i_Strategy_ID = 3 Then Begin" in content


def test_generator_auto_split():
    """Test automatic splitting when exceeding max strategies per part."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "deployments" / "test789"
        
        # Create many strategies (more than default max of 50)
        strategies = []
        for i in range(55):  # Exceeds default 50
            source = create_valid_strategy()
            strategy = parse_powerlanguage(source, name=f"Strategy{i+1}")
            strategies.append(strategy)
        
        # Generate wrapper with lower limit for testing
        config = MasterWrapperConfig(
            quarter="2026Q3",
            deploy_id="test789",
            strategies=strategies,
            output_dir=output_dir,
            max_strategies_per_part=10,  # Low limit to force splitting
        )
        
        generator = MasterWrapperGenerator(config)
        parts = generator.generate()
        
        # Should create multiple parts (55 strategies / 10 per part = 6 parts)
        assert len(parts) == 6
        
        # Check part names
        assert parts[0].part_name == "Titanium_Master_2026Q3_PartA.txt"
        assert parts[1].part_name == "Titanium_Master_2026Q3_PartB.txt"
        assert parts[5].part_name == "Titanium_Master_2026Q3_PartF.txt"
        
        # Check strategy counts
        assert len(parts[0].strategies) == 10
        assert len(parts[5].strategies) == 5  # Last part has remainder


def test_high_level_api():
    """Test the high-level generate_master_wrapper function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_output"
        
        # Create strategies
        source = create_valid_strategy()
        strategy = parse_powerlanguage(source, name="TestStrategy")
        
        # Use high-level API
        parts = generate_master_wrapper(
            strategies=[strategy],
            quarter="2026Q4",
            output_dir=output_dir,
        )
        
        assert len(parts) == 1
        assert (output_dir / "Deployment_Guide.html").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])