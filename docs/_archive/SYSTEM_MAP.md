# System Map (Conceptual, Non-SSOT)

Status: **Guide / Conceptual** (may drift).  
If anything here conflicts with SSOT, prefer:
- `docs/_archive/ARCHITECTURE_SSOT.md`
- `docs/SPEC_ENGINE_V1.md`

## Mainline Flow

`RAW -> BUILD_BARS -> BUILD_FEATURES -> WFS -> artifacts/result.json -> portfolio/decision -> report viewer`

## Key Folders (Physical)
- Raw data: `FishBroData/raw/`
- Shared caches: `cache/shared/<season>/<dataset_id>/...`
- Runtime state: `outputs/runtime/` (DB, indexes)
- Job evidence: `outputs/artifacts/jobs/<job_id>/`
- Season-scoped evidence/results: `outputs/artifacts/seasons/<season>/...`

## The One Rule

UI and scripts should **never** guess paths by scanning directories. They must use:
- evidence/manifest contracts, and
- the path helpers in `core.paths` / `control.job_artifacts`.
