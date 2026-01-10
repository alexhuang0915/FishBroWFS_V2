#!/usr/bin/env python3
"""
Phase 4-C: Switch-Case Master Wrapper Generator

Core implementation of the Titanium Master Deployment generator that merges
multiple standalone PowerLanguage strategies into a single Master .el file.

Key Constraints:
- NO Set* PowerLanguage syntax (SetStopLoss, SetProfitTarget, etc.)
- IOG = False only (Bar Close semantics)
- Explicit orders only (Buy/Sell/SellShort/BuyToCover)
- No intrabar logic, File IO, DLL, Plot, Text Drawing
- Max 50 strategies per Master file (auto-split if >50)
"""

from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import textwrap


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class PowerLanguageStrategy:
    """Represents a parsed PowerLanguage strategy."""
    
    name: str
    source_code: str
    strategy_id: int = 0
    
    # Parsed components
    inputs: Dict[str, Any] = field(default_factory=dict)
    vars: Dict[str, Any] = field(default_factory=dict)
    arrays: Dict[str, Any] = field(default_factory=dict)
    intrabar_persist: Dict[str, Any] = field(default_factory=dict)
    logic_blocks: List[str] = field(default_factory=list)
    
    # Validation flags
    has_set_syntax: bool = False
    has_iog: bool = False
    has_forbidden: bool = False
    validation_errors: List[str] = field(default_factory=list)
    
    # Lookback analysis
    max_lookback: int = 0
    
    def is_valid(self) -> bool:
        """Check if strategy passes all validation rules."""
        return not (self.has_set_syntax or self.has_iog or self.has_forbidden)


@dataclass
class MasterWrapperConfig:
    """Configuration for generating a Master wrapper."""
    
    quarter: str  # e.g., "2026Q1"
    deploy_id: str
    strategies: List[PowerLanguageStrategy]
    output_dir: Path
    
    # Generation options
    max_strategies_per_part: int = 50
    include_deployment_guide: bool = True
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.deploy_id:
            raise ValueError("deploy_id is required")
        if not self.quarter:
            raise ValueError("quarter is required")
        if not self.strategies:
            raise ValueError("At least one strategy is required")


@dataclass
class GeneratedPart:
    """Represents a generated Master wrapper part."""
    
    part_name: str  # e.g., "Titanium_Master_2026Q1_PartA.txt"
    strategies: List[PowerLanguageStrategy]
    start_id: int = 1
    max_bars_back: int = 0
    source_code: str = ""


# ============================================================================
# Constants & Reserved Words
# ============================================================================

# PowerLanguage reserved words that must NOT be renamed
RESERVED_WORDS = {
    # Built-in functions
    "Close", "High", "Low", "Open", "Volume", "Time", "Date", "BarNumber",
    "MarketPosition", "CurrentContracts", "AvgEntryPrice", "MaxContracts",
    "MaxPositionProfit", "PositionProfit", "TotalTrades", "WinPercent",
    "NetProfit", "GrossProfit", "GrossLoss", "ProfitFactor", "MaxDrawDown",
    "MaxIDDrawDown", "MaxConsecWinners", "MaxConsecLosers",
    
    # Mathematical functions
    "Average", "Highest", "Lowest", "Summation", "StdDev", "Variance",
    "Median", "Mode", "LinearReg", "LinearRegSlope", "LinearRegAngle",
    "LinearRegIntercept", "LinearRegValue", "RSI", "MACD", "Stochastic",
    "BollingerBand", "ATR", "TrueRange", "Momentum", "RateOfChange",
    "Wilders", "XAverage", "WeightedClose",
    
    # Order functions
    "Buy", "Sell", "SellShort", "BuyToCover", "ExitLong", "ExitShort",
    "SetStopLoss", "SetProfitTarget", "SetBreakEven", "SetTrailingStop",
    "SetDollarTrailing", "SetPercentTrailing",
    
    # Control flow
    "If", "Then", "Begin", "End", "Else", "For", "To", "DownTo", "While",
    "Repeat", "Until", "Switch", "Case", "Default",
    
    # Other keywords
    "Inputs", "Vars", "Arrays", "IntrabarPersist", "Once", "Value1", "Value2",
    "Value3", "Value4", "Plot", "Alert", "Text", "File", "DLL",
}

# Forbidden constructs that cause immediate rejection
FORBIDDEN_KEYWORDS = [
    # Set* syntax (absolute prohibition)
    r"SetStopLoss",
    r"SetProfitTarget", 
    r"SetBreakEven",
    r"SetTrailingStop",
    r"SetDollarTrailing",
    r"SetPercentTrailing",
    
    # IOG and intrabar
    r"IOG\s*=\s*True",
    r"IntraBarOrderGeneration\s*=\s*True",
    
    # File/DLL operations
    r"File\(",
    r"DLL\(",
    r"#include",
    
    # Plotting and UI
    r"Plot\(",
    r"Alert\(",
    r"Text\(",
    r"PaintBar",
    
    # Custom functions (not allowed in subset)
    r"Method\s+\w+\s*\(",
    r"Function\s+\w+\s*\(",
]

# Allowed order syntax patterns
# Matches: Buy/Sell/SellShort/BuyToCover/ExitLong/ExitShort with "Next Bar at Market" or "Next Bar at price Stop"
ALLOWED_ORDERS = [
    r"Buy\s+.*Next\s+Bar\s+at\s+(Market|[\w\.]+(?:\s+Stop)?)",
    r"Sell\s+.*Next\s+Bar\s+at\s+(Market|[\w\.]+(?:\s+Stop)?)",
    r"SellShort\s+.*Next\s+Bar\s+at\s+(Market|[\w\.]+(?:\s+Stop)?)",
    r"BuyToCover\s+.*Next\s+Bar\s+at\s+(Market|[\w\.]+(?:\s+Stop)?)",
    r"ExitLong\s+.*Next\s+Bar\s+at\s+(Market|[\w\.]+(?:\s+Stop)?)",
    r"ExitShort\s+.*Next\s+Bar\s+at\s+(Market|[\w\.]+(?:\s+Stop)?)",
]


# ============================================================================
# Parser & Validator
# ============================================================================

def parse_powerlanguage(source_code: str, name: str = "") -> PowerLanguageStrategy:
    """
    Parse PowerLanguage source code into structured components.
    
    This is a simplified parser that extracts key components for the wrapper.
    A full AST parser would be more complex but this handles the essential parts.
    """
    strategy = PowerLanguageStrategy(name=name, source_code=source_code)
    
    # Check for forbidden constructs
    for pattern in FORBIDDEN_KEYWORDS:
        if re.search(pattern, source_code, re.IGNORECASE):
            if pattern.startswith("Set"):
                strategy.has_set_syntax = True
                strategy.validation_errors.append(f"Contains forbidden Set* syntax: {pattern}")
            elif "IOG" in pattern or "IntraBarOrderGeneration" in pattern:
                strategy.has_iog = True
                strategy.validation_errors.append("Contains IOG=True (must be False)")
            else:
                strategy.has_forbidden = True
                strategy.validation_errors.append(f"Contains forbidden construct: {pattern}")
    
    # Extract Inputs section
    inputs_match = re.search(r"Inputs:\s*(.*?)(?=\s*(?:Vars:|Arrays:|IntrabarPersist:|$))", 
                            source_code, re.DOTALL | re.IGNORECASE)
    if inputs_match:
        inputs_text = inputs_match.group(1)
        # Simple parsing of input declarations
        for line in inputs_text.split('\n'):
            line = line.strip()
            if line and not line.startswith('//'):
                # Match pattern like "i_Len(18);"
                match = re.match(r"(\w+)\s*\(\s*([^)]+)\s*\)", line)
                if match:
                    name, value = match.groups()
                    strategy.inputs[name] = value.strip()
    
    # Extract Vars section
    vars_match = re.search(r"Vars:\s*(.*?)(?=\s*(?:Arrays:|IntrabarPersist:|$))", 
                          source_code, re.DOTALL | re.IGNORECASE)
    if vars_match:
        vars_text = vars_match.group(1)
        for line in vars_text.split('\n'):
            line = line.strip()
            if line and not line.startswith('//'):
                match = re.match(r"(\w+)\s*\(\s*([^)]+)\s*\)", line)
                if match:
                    name, value = match.groups()
                    strategy.vars[name] = value.strip()
    
    # Extract Arrays section
    arrays_match = re.search(r"Arrays:\s*(.*?)(?=\s*(?:IntrabarPersist:|$))", 
                            source_code, re.DOTALL | re.IGNORECASE)
    if arrays_match:
        arrays_text = arrays_match.group(1)
        for line in arrays_text.split('\n'):
            line = line.strip()
            if line and not line.startswith('//'):
                match = re.match(r"(\w+)\s*\[\s*([^\]]+)\s*\]", line)
                if match:
                    name, size = match.groups()
                    strategy.arrays[name] = size.strip()
    
    # Extract IntrabarPersist section
    ip_match = re.search(r"IntrabarPersist:\s*(.*?)(?=\s*(?:$))", 
                        source_code, re.DOTALL | re.IGNORECASE)
    if ip_match:
        ip_text = ip_match.group(1)
        for line in ip_text.split('\n'):
            line = line.strip()
            if line and not line.startswith('//'):
                match = re.match(r"(\w+)\s*\(\s*([^)]+)\s*\)", line)
                if match:
                    name, value = match.groups()
                    strategy.intrabar_persist[name] = value.strip()
    
    # Extract main logic (simplified - everything after declarations)
    # This is a placeholder; a real implementation would parse more carefully
    strategy.logic_blocks = [source_code]
    
    # Estimate max lookback (simplified)
    strategy.max_lookback = estimate_max_lookback(source_code)
    
    return strategy


def validate_strategy(strategy: PowerLanguageStrategy) -> Tuple[bool, List[str]]:
    """
    Validate a PowerLanguage strategy against the Phase 4-C constraints.
    
    Returns (is_valid, error_messages)
    """
    errors = []
    
    # Check for Set* syntax
    if strategy.has_set_syntax:
        errors.append("Strategy contains Set* syntax which is forbidden")
    
    # Check for IOG
    if strategy.has_iog:
        errors.append("Strategy has IOG=True (must be False)")
    
    # Check for other forbidden constructs
    if strategy.has_forbidden:
        errors.append("Strategy contains forbidden constructs")
    
    # Check for explicit orders (simplified check)
    has_explicit_orders = False
    for pattern in ALLOWED_ORDERS:
        if re.search(pattern, strategy.source_code, re.IGNORECASE):
            has_explicit_orders = True
            break
    
    if not has_explicit_orders:
        errors.append("Strategy must use explicit order syntax (Buy/Sell at Market/Stop)")
    
    # Check for intrabar logic (simplified)
    if "IntrabarOrderGeneration" in strategy.source_code:
        errors.append("Intrabar logic is not allowed")
    
    return (len(errors) == 0, errors)


def estimate_max_lookback(source_code: str) -> int:
    """
    Estimate maximum lookback required by the strategy.
    
    This is a simplified implementation that looks for common indicators
    with lookback periods. A real implementation would need to parse
    all function calls and track dependencies.
    """
    max_lookback = 50  # Default buffer
    
    # Look for common indicator patterns
    patterns = [
        (r"Average\s*\(\s*Close\s*,\s*(\d+)\s*\)", 1),
        (r"Highest\s*\(\s*High\s*,\s*(\d+)\s*\)", 1),
        (r"Lowest\s*\(\s*Low\s*,\s*(\d+)\s*\)", 1),
        (r"StdDev\s*\(\s*Close\s*,\s*(\d+)\s*\)", 1),
        (r"RSI\s*\(\s*Close\s*,\s*(\d+)\s*\)", 1),
        (r"ATR\s*\(\s*(\d+)\s*\)", 1),
    ]
    
    for pattern, group_idx in patterns:
        matches = re.findall(pattern, source_code, re.IGNORECASE)
        for match in matches:
            try:
                if isinstance(match, tuple):
                    value = int(match[group_idx])
                else:
                    value = int(match)
                max_lookback = max(max_lookback, value)
            except (ValueError, IndexError):
                pass
    
    return max_lookback


# ============================================================================
# Namespace Isolation & Transformation
# ============================================================================

def isolate_namespace(strategy: PowerLanguageStrategy, strategy_id: int) -> PowerLanguageStrategy:
    """
    Apply namespace isolation by suffixing all strategy-specific identifiers.
    
    Creates a new strategy with renamed variables, arrays, etc.
    """
    # Create a copy with the new ID
    isolated = PowerLanguageStrategy(
        name=f"{strategy.name}_S{strategy_id:02d}",
        source_code=strategy.source_code,
        strategy_id=strategy_id,
    )
    
    # Build mapping of old names to new names
    rename_map = {}
    
    # Rename variables (but not reserved words)
    for var_name in strategy.vars:
        if var_name not in RESERVED_WORDS:
            new_name = f"{var_name}_S{strategy_id:02d}"
            rename_map[var_name] = new_name
            isolated.vars[new_name] = strategy.vars[var_name]
        else:
            isolated.vars[var_name] = strategy.vars[var_name]
    
    # Rename arrays
    for array_name in strategy.arrays:
        if array_name not in RESERVED_WORDS:
            new_name = f"{array_name}_S{strategy_id:02d}"
            rename_map[array_name] = new_name
            isolated.arrays[new_name] = strategy.arrays[array_name]
        else:
            isolated.arrays[array_name] = strategy.arrays[array_name]
    
    # Rename intrabar persist
    for ip_name in strategy.intrabar_persist:
        if ip_name not in RESERVED_WORDS:
            new_name = f"{ip_name}_S{strategy_id:02d}"
            rename_map[ip_name] = new_name
            isolated.intrabar_persist[new_name] = strategy.intrabar_persist[ip_name]
        else:
            isolated.intrabar_persist[ip_name] = strategy.intrabar_persist[ip_name]
    
    # Apply renaming to logic blocks (simplified)
    # In a real implementation, this would need to be more sophisticated
    # to avoid renaming reserved words within strings or comments
    isolated.logic_blocks = []
    for block in strategy.logic_blocks:
        transformed = block
        for old_name, new_name in rename_map.items():
            # Use word boundaries to avoid partial matches
            transformed = re.sub(rf'\b{old_name}\b', new_name, transformed)
        isolated.logic_blocks.append(transformed)
    
    return isolated


# ============================================================================
# Master Wrapper Generator
# ============================================================================

class MasterWrapperGenerator:
    """Main generator class for creating Titanium Master wrapper files."""
    
    def __init__(self, config: MasterWrapperConfig):
        self.config = config
        self.parts: List[GeneratedPart] = []
        
    def generate(self) -> List[GeneratedPart]:
        """Generate all Master wrapper parts."""
        # Validate all strategies
        for i, strategy in enumerate(self.config.strategies):
            is_valid, errors = validate_strategy(strategy)
            if not is_valid:
                raise ValueError(f"Strategy {i+1} ({strategy.name}) invalid: {errors}")
        
        # Split strategies into parts if needed
        max_per_part = self.config.max_strategies_per_part
        strategy_groups = []
        
        if len(self.config.strategies) <= max_per_part:
            strategy_groups = [self.config.strategies]
        else:
            # Split into multiple parts
            for i in range(0, len(self.config.strategies), max_per_part):
                group = self.config.strategies[i:i + max_per_part]
                strategy_groups.append(group)
        
        # Generate each part
        self.parts = []
        for part_idx, strategy_group in enumerate(strategy_groups):
            part = self._generate_part(part_idx, strategy_group)
            self.parts.append(part)
            
            # Write part to file
            self._write_part(part)
        
        # Generate deployment guide if requested
        if self.config.include_deployment_guide:
            self._generate_deployment_guide()
        
        return self.parts
    
    def _generate_part(self, part_idx: int, strategies: List[PowerLanguageStrategy]) -> GeneratedPart:
        """Generate a single Master wrapper part."""
        # Determine part suffix (A, B, C, ...)
        suffix = chr(ord('A') + part_idx)
        part_name = f"Titanium_Master_{self.config.quarter}_Part{suffix}.txt"
        
        # Apply namespace isolation to each strategy
        isolated_strategies = []
        for i, strategy in enumerate(strategies):
            strategy_id = i + 1  # 1-based IDs within part
            isolated = isolate_namespace(strategy, strategy_id)
            isolated.strategy_id = strategy_id
            isolated_strategies.append(isolated)
        
        # Calculate MaxBarsBack for this part
        max_bars_back = self._calculate_max_bars_back(isolated_strategies)
        
        # Generate the Master wrapper source code
        source_code = self._generate_master_source(isolated_strategies, max_bars_back, part_name)
        
        return GeneratedPart(
            part_name=part_name,
            strategies=isolated_strategies,
            start_id=1,
            max_bars_back=max_bars_back,
            source_code=source_code,
        )
    
    def _calculate_max_bars_back(self, strategies: List[PowerLanguageStrategy]) -> int:
        """Calculate MaxBarsBack value for a set of strategies."""
        max_lookback = 0
        for strategy in strategies:
            max_lookback = max(max_lookback, strategy.max_lookback)
        
        # Add buffer (≥50 bars as per spec)
        return max(max_lookback + 50, 100)  # Minimum 100 bars for safety
    
    def _generate_master_source(self, strategies: List[PowerLanguageStrategy],
                               max_bars_back: int, part_name: str) -> str:
        """Generate the Master wrapper source code."""
        # Header
        lines = [
            "// ========================================",
            f"// Titanium Master Deployment",
            f"// Quarter: {self.config.quarter}",
            f"// Part: {part_name.split('_')[-1].replace('.txt', '')}",
            f"// Generator Version: 1.0.0",
            f"// Deploy Hash: {self.config.deploy_id[:8]}",
            f"// ========================================",
            "",
            f"SetMaxBarsBack({max_bars_back});",
            "",
            "Inputs:",
            "    i_Strategy_ID(0),",
            "    i_Lots(1);",
            "",
            "Vars:",
        ]
        
        # Collect all variable declarations
        var_lines = []
        for strategy in strategies:
            # Add strategy-specific variables
            for var_name, var_value in strategy.vars.items():
                var_lines.append(f"    // --- Strategy {strategy.strategy_id:02d} ---")
                var_lines.append(f"    {var_name}({var_value}),")
            
            # Add arrays
            for array_name, array_size in strategy.arrays.items():
                var_lines.append(f"    {array_name}[{array_size}],")
            
            # Add intrabar persist
            for ip_name, ip_value in strategy.intrabar_persist.items():
                var_lines.append(f"    {ip_name}({ip_value}),")
        
        # Add shared variables
        var_lines.append("    // --- Shared ---")
        var_lines.append("    v_MP(0);")
        
        # Remove duplicate consecutive comments
        unique_var_lines = []
        for i, line in enumerate(var_lines):
            if i == 0 or line != var_lines[i-1] or "---" not in line:
                unique_var_lines.append(line)
        
        lines.extend(unique_var_lines)
        lines.append("")
        
        # Market position tracking
        lines.extend([
            "v_MP = MarketPosition;",
            "",
        ])
        
        # Generate switch-case logic
        lines.append("If i_Strategy_ID = 1 Then Begin")
        if strategies:
            # Add first strategy's logic
            strategy = strategies[0]
            for block in strategy.logic_blocks:
                # Indent the logic
                for logic_line in block.split('\n'):
                    if logic_line.strip():
                        lines.append(f"    {logic_line}")
        lines.append("End")
        
        # Add remaining strategies
        for i, strategy in enumerate(strategies[1:], start=2):
            lines.append(f"Else If i_Strategy_ID = {i} Then Begin")
            for block in strategy.logic_blocks:
                for logic_line in block.split('\n'):
                    if logic_line.strip():
                        lines.append(f"    {logic_line}")
            lines.append("End")
        
        # Add safety no-op for invalid IDs
        lines.extend([
            "Else Begin",
            "    // Safety no-op",
            "End;",
            "",
        ])
        
        return '\n'.join(lines)
    
    def _write_part(self, part: GeneratedPart) -> None:
        """Write a generated part to disk."""
        output_path = self.config.output_dir / part.part_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(part.source_code)
        
        print(f"Generated: {output_path}")
    
    def _generate_deployment_guide(self) -> None:
        """Generate Deployment_Guide.html."""
        guide_path = self.config.output_dir / "Deployment_Guide.html"
        
        html_content = self._create_deployment_guide_html()
        
        with open(guide_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Generated: {guide_path}")
    
    def _create_deployment_guide_html(self) -> str:
        """Create HTML deployment guide."""
        parts_info = []
        for part in self.parts:
            for strategy in part.strategies:
                parts_info.append({
                    'part': part.part_name.replace('.txt', ''),
                    'strategy_id': strategy.strategy_id,
                    'name': strategy.name,
                    'logic_hash': hashlib.md5(strategy.source_code.encode()).hexdigest()[:4],
                })
        
        # Create HTML table rows
        table_rows = []
        for info in parts_info:
            table_rows.append(f"""
            <tr>
                <td>{info['part']}</td>
                <td>{info['strategy_id']}</td>
                <td>Symbol</td>
                <td>Timeframe</td>
                <td>{info['name']}</td>
                <td>Suggested Contracts</td>
                <td>{info['logic_hash']}</td>
            </tr>
            """)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Titanium Master Deployment Guide - {self.config.quarter}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .footer {{ margin-top: 40px; font-size: 0.9em; color: #666; }}
    </style>
</head>
<body>
    <h1>Titanium Master Deployment Guide</h1>
    <p><strong>Quarter:</strong> {self.config.quarter}</p>
    <p><strong>Deploy ID:</strong> {self.config.deploy_id}</p>
    <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <h2>Strategy Assignment Table</h2>
    <table>
        <thead>
            <tr>
                <th>Part</th>
                <th>Strategy_ID</th>
                <th>Symbol</th>
                <th>Timeframe</th>
                <th>Source Strategy Name</th>
                <th>Suggested Contracts</th>
                <th>Logic Hash</th>
            </tr>
        </thead>
        <tbody>
            {''.join(table_rows)}
        </tbody>
    </table>
    
    <div class="footer">
        <p><strong>Deployment Instructions:</strong></p>
        <ol>
            <li>Import the Master .el file into MultiCharts Portfolio Trader</li>
            <li>Compile once (F3 should pass)</li>
            <li>Assign different i_Strategy_ID per symbol</li>
            <li>Set i_Lots according to position sizing requirements</li>
            <li>Verify trade list matches standalone strategy semantics</li>
        </ol>
        <p><strong>Constraints:</strong> IOG=False, Bar Close semantics only. No Set* syntax.</p>
    </div>
</body>
</html>"""
        
        return html


# ============================================================================
# Public API
# ============================================================================

def generate_master_wrapper(
    strategies: List[PowerLanguageStrategy],
    quarter: str,
    deploy_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> List[GeneratedPart]:
    """
    High-level function to generate Titanium Master wrapper.
    
    Args:
        strategies: List of parsed PowerLanguage strategies
        quarter: Quarter identifier (e.g., "2026Q1")
        deploy_id: Deployment ID (auto-generated if None)
        output_dir: Output directory (default: outputs/jobs/{deploy_id}/deployments/)
    
    Returns:
        List of generated parts
    """
    if deploy_id is None:
        deploy_id = hashlib.md5(f"{quarter}_{datetime.now().isoformat()}".encode()).hexdigest()[:8]
    
    if output_dir is None:
        output_dir = Path("outputs") / "jobs" / deploy_id / "deployments"
    
    config = MasterWrapperConfig(
        quarter=quarter,
        deploy_id=deploy_id,
        strategies=strategies,
        output_dir=output_dir,
    )
    
    generator = MasterWrapperGenerator(config)
    return generator.generate()