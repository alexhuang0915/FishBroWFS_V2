#!/usr/bin/env python3
"""
Test S1 research runner to see error.
"""
import sys
sys.path.insert(0, 'src')

from config import reset_config_load_records, enable_config_recording
from control.research_runner import run_research
from strategy.registry import load_builtin_strategies

# Clear caches
from config.registry.instruments import load_instruments
from config.registry.timeframes import load_timeframes
from config.registry.datasets import load_datasets
from config.registry.strategy_catalog import load_strategy_catalog
from config.profiles import load_profile
from config.strategies import load_strategy
from config.portfolio import load_portfolio_config

def clear_all_config_caches():
    load_instruments.cache_clear()
    load_timeframes.cache_clear()
    load_datasets.cache_clear()
    load_strategy_catalog.cache_clear()
    load_profile.cache_clear()
    load_strategy.cache_clear()
    load_portfolio_config.cache_clear()

clear_all_config_caches()
reset_config_load_records()
enable_config_recording(True)

load_builtin_strategies()

season = "TEST2026Q1"
dataset_id = "TEST.MNQ"

try:
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id="S1",
        outputs_root="outputs",
        allow_build=False,
        build_ctx=None,
        wfs_config=None,
    )
    print("Success:", report.get('wfs_summary', {}).get('status', 'unknown'))
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()