# TUI User Manual

FishBroWFS TUI is a keyboard-first control station for running the local pipeline without HTTP.

Status: **Guide** (may drift; verify against in-app UI labels if keys change).  
Authoritative specs (fills/costs/result schema) live in:
- `docs/SPEC_ENGINE_V1.md`

## 1. Requirements
- Python venv activated
- Dependencies:
  - `textual`
  - `pyperclip` (for copy/paste)

Install (one-time):
```
. .venv/bin/activate
pip install textual pyperclip
```

## 2. Start the System
Terminal A (Worker Loop, keep running):
```
cd /path/to/FishBroWFS_V2
PYTHONPATH=src python3 -m control.supervisor.worker --max-workers 1 --tick-interval 0.2
```

Terminal B (TUI):
```
cd /path/to/FishBroWFS_V2
PYTHONPATH=src FISHBRO_RAW_ROOT=/path/to/FishBroWFS_V2/FishBroData python3 src/gui/tui/app.py
```

## 3. Global Keys
- `1` Data Prepare (BUILD_BARS / BUILD_FEATURES)
- `2` Monitor (jobs list)
- `3` WFS (walk-forward)
- `4` Portfolio
- `5` System / Runtime Index
- `6` Catalog
- `7` Report
- `8` Admin
- `q` Quit
- `Ctrl+C` Copy
  - If focus is on an input: copy that input value
  - If focus is on a jobs table row: copy that job id
- `Ctrl+V` Paste into focused input

## 4. Default Workflow (CME.MNQ / 60m / 2026Q1)
All form pages are split: left = inputs, right = live job monitor (auto-refresh).

### 4.1 Data Prepare (BUILD_BARS → BUILD_FEATURES)
Go to `1`.
- Dataset ID: `CME.MNQ`
- Timeframes (min): `60` (or `15,60,240`)
- Season: `2026Q1`
Submit **BUILD_BARS** first, then **BUILD_FEATURES**.

Notes:
- BUILD_FEATURES is **prompt-only**: if bars are missing, the TUI shows a message and does not submit the job.
- Feature scope (V1 default): `all_packs` (union of SSOT packs).

### 4.2 WFS (Recommended)
Go to `3`.
Defaults are prefilled. Use `Auto Range from Bars` to set start/end from data1 range.
Submit.

### 4.3 Portfolio
Go to `4`.
- Season: `2026Q1`
- Use the dropdown “Recent WFS Jobs”
  - `Add` → append to candidate list
  - `Copy` → copy selected job id
  - `Copy Latest` → copy newest WFS job id
Submit.

### 4.4 Monitor + Artifacts
Go to `2`.
This page is split:
- Left: artifacts list + log preview for the selected job
- Right: Live Jobs (auto-refresh)

On the right “Live Jobs” table:
- Use arrows to select a row
- Press `Enter` to load that job’s artifacts into the left panel

Logs and receipts live under:
- `outputs/artifacts/jobs/<job_id>/`

## 5. Auto Range from Bars
WFS screen can auto-fill ranges using data1 bars:
- WFS: fills `start_season` / `end_season`

This uses:
`cache/shared/{season}/{dataset_id}/bars/resampled_{tf}m.npz`

## 6. Troubleshooting
- TUI not starting: install `textual`.
- Copy/paste not working: install `pyperclip`.
- BUILD_BARS fails to find raw file:
  - Ensure `FISHBRO_RAW_ROOT` points to `FishBroData`
  - Raw files must exist under `FishBroData/raw/`
- WFS fails: check `outputs/artifacts/jobs/<job_id>/error.txt`

## 7. Artifacts Paths (SSOT)
- Jobs: `outputs/artifacts/jobs/<job_id>/`
- Bars: `cache/shared/{season}/{dataset_id}/bars/`
- WFS: discover via **job evidence** and manifests (do not hardcode paths)
- Portfolio: discover via **job evidence** and manifests (do not hardcode paths)
