"""Timezone database information utilities.

Phase 6.6: Get tzdb provider and version for manifest recording.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Tuple
import zoneinfo


def get_tzdb_info() -> Tuple[str, str]:
    """Get timezone database provider and version.
    
    Phase 6.6: Extract tzdb provider and version for manifest recording.
    
    Strategy:
    1. If tzdata package (PyPI) is installed, use it as provider + version
    2. Otherwise, try to discover tzdata.zi from zoneinfo.TZPATH (module-level)
    
    Returns:
        Tuple of (provider, version)
        - provider: "tzdata" (PyPI package) or "zoneinfo" (standard library)
        - version: Version string from tzdata package or tzdata.zi file, or "unknown" if not found
    """
    provider = "zoneinfo"
    version = "unknown"

    # 1) If tzdata package installed, prefer it as provider + version
    try:
        version = metadata.version("tzdata")
        provider = "tzdata"
        return provider, version
    except metadata.PackageNotFoundError:
        pass

    # 2) Try discover tzdata.zi from zoneinfo.TZPATH (module-level)
    tzpaths = getattr(zoneinfo, "TZPATH", ())
    for p in tzpaths:
        cand = Path(p) / "tzdata.zi"
        if cand.exists():
            # best-effort parse: search a line containing "version"
            try:
                text = cand.read_text(encoding="utf-8", errors="ignore")
                # minimal heuristic: find first token that looks like YYYYx (not strict)
                for line in text.splitlines()[:200]:
                    if "version" in line.lower():
                        version = line.strip().split()[-1].strip('"')
                        break
            except OSError:
                pass
            break

    return provider, version
