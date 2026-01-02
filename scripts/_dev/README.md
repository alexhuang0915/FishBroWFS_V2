# Development Tools Directory

This directory contains reusable debugging and development tools for the FishBroWFS_V2 project.

## Purpose

Tools in this directory are intended for:
- Debugging specific subsystems (Stage2, Phase2 theta, etc.)
- Forensic analysis of kernel behavior
- Performance profiling and optimization
- Test data generation and validation

## Current Tools

### `debug_stage2.py`
- Stage2 kernel debugging and intent/fill analysis
- Helps diagnose entry-fill pipeline issues
- Provides detailed logging of stop-cross mechanics

### `debug_p2_theta.py`
- Phase2 theta parameter debugging
- Analyzes parameter sensitivity and warmup behavior

## Usage Guidelines

1. **Reusability**: Tools should be designed for multiple uses, not one-off debugging sessions
2. **Documentation**: Each tool should have clear docstrings explaining its purpose
3. **Non-invasive**: Tools should not modify production code; use monkeypatching or configuration overrides
4. **Evidence collection**: Tools should output to `outputs/_dp_evidence/` for audit trails

## Adding New Tools

When adding a new tool:
1. Ensure it belongs in `_dev/` (not root)
2. Add a brief description to this README
3. Follow the project's coding standards
4. Include proper error handling and logging

## Cleanup Policy

Tools that become obsolete should be moved to `outputs/_dp_evidence/archive/` rather than deleted, to preserve forensic history.