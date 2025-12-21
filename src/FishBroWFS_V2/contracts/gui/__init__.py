"""
GUI payload contracts for Research OS.

These schemas define the allowed shape of GUI-originated requests,
ensuring GUI cannot inject execution semantics or violate governance rules.
"""

from __future__ import annotations

from FishBroWFS_V2.contracts.gui.submit_batch import SubmitBatchPayload
from FishBroWFS_V2.contracts.gui.freeze_season import FreezeSeasonPayload
from FishBroWFS_V2.contracts.gui.export_season import ExportSeasonPayload
from FishBroWFS_V2.contracts.gui.compare_request import CompareRequestPayload

__all__ = [
    "SubmitBatchPayload",
    "FreezeSeasonPayload",
    "ExportSeasonPayload",
    "CompareRequestPayload",
]