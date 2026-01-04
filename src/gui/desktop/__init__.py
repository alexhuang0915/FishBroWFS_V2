"""
Desktop GUI module for FishBroWFS Control Station.
"""

import sys

# Use lazy imports to avoid importing PySide6 when not needed (e.g., in tests)
if sys.modules.get(__name__).__dict__.get('__control_station_loaded'):
    # Already loaded
    pass
else:
    # Set flag to prevent recursion
    sys.modules[__name__].__dict__['__control_station_loaded'] = True
    
    # Define lazy import properties
    def __getattr__(name):
        if name == "ControlStation":
            from .control_station import ControlStation
            return ControlStation
        elif name == "BacktestWorker":
            from .worker import BacktestWorker
            return BacktestWorker
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    __all__ = ["ControlStation", "BacktestWorker"]