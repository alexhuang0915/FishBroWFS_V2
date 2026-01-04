"""Pages module for Phase 11-12 Constitution UI.

Exports the four constitution-mandated pages:
- OP (Operator Console)
- Registry (Strategy Inventory)
- Allocation (Read-only reality check)
- Audit (Immutable historical record)
"""
from .op import render as op
from .registry import render as registry
from .allocation import render as allocation
from .audit import render as audit

__all__ = ["op", "registry", "allocation", "audit"]