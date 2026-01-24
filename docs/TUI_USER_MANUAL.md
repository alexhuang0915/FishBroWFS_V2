# TUI User Manual

FishBroWFS TUI is a keyboard-first control station for running the local pipeline without HTTP.

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
cd /home/fishbro/FishBroWFS_V2
PYTHONPATH=src python3 -m control.supervisor.worker --max-workers 1 --tick-interval 0.2
```

Terminal B (TUI):
```
cd /home/fishbro/FishBroWFS_V2
PYTHONPATH=src FISHBRO_RAW_ROOT=/home/fishbro/FishBroWFS_V2/FishBroData python3 src/gui/tui/app.py
```

## 3. Global Keys
- `1` BUILD_DATA
- `3` Freeze/Compile
- `4` Monitor (jobs list)
- `5` Runtime Index
- `6` Plateau
- `7` Admin (PING/CLEAN_CACHE)
- `8` WFS (walk-forward)
- `9` Portfolio
- `q` Quit
- `Ctrl+C` Copy
  - If focus is on an input: copy that input value
  - If focus is on a jobs table row: copy that job id
- `Ctrl+V` Paste into focused input

## 4. Default Workflow (CME.MNQ / 60m / 2026Q1)
All form pages are split: left = inputs, right = live job monitor (auto-refresh).

### 4.1 BUILD_DATA
Go to `1`.
- Dataset ID: `CME.MNQ`
- Timeframe (min): `60`
- Mode: `BARS_ONLY` (fast) or `FULL` (bars + features)
- Season: `2026Q1`
Submit.

### 4.2 WFS (Recommended)
Go to `8`.
Defaults are prefilled. Use `Auto Range from Bars` to set start/end from data1 range.
Submit.

### 4.3 Portfolio
Go to `9`.
- Season: `2026Q1`
- Use the dropdown “Recent WFS Jobs”
  - `Add` → append to candidate list
  - `Copy` → copy selected job id
  - `Copy Latest` → copy newest WFS job id
Submit.

### 4.4 Monitor + Artifacts
Go to `4`.
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
`outputs/shared/{season}/{dataset_id}/bars/resampled_{tf}m.npz`

## 6. Troubleshooting
- TUI not starting: install `textual`.
- Copy/paste not working: install `pyperclip`.
- BUILD_DATA fails to find raw file:
  - Ensure `FISHBRO_RAW_ROOT` points to `FishBroData`
  - Raw files must exist under `FishBroData/raw/`
- WFS fails: check `outputs/artifacts/jobs/<job_id>/error.txt`

## 7. Artifacts Paths (SSOT)
- Jobs: `outputs/artifacts/jobs/<job_id>/`
- Bars: `outputs/shared/{season}/{dataset_id}/bars/`
- WFS: `outputs/artifacts/seasons/{season}/wfs/<job_id>/result.json`
- Portfolio: `outputs/artifacts/seasons/{season}/portfolios/<portfolio_id>/`
