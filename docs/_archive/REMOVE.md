# REMOVE.md (v2) — Local Research OS Trim Plan

## 1) 前提與邊界
- 系統已裁定為 **Local Research OS**：
  - **No HTTP / No API / No ports**
  - **TUI 為唯一 UI**
  - **Supervisor Core + Worker loop 為唯一執行路徑**
- **不可刪**：`control.supervisor.submit()`、`SupervisorDB.submit_job()`、`jobs_v2.db schema`、主線 handlers（BUILD_BARS / BUILD_FEATURES / BUILD_DATA(legacy) / RUN_RESEARCH_WFS / BUILD_PORTFOLIO_V2）

## 2) 已刪除（無需再動）
以下已從 repo 移除，請勿再列入清單：
- `tests/`（已重建為最小測試集）
- `scripts/`（已移除）
- HTTP API / server 路徑：
  - `src/control/api.py`
  - `src/control/portfolio/api_v1.py`
  - `src/control/explain_service.py`
  - `src/control/lifecycle.py`
  - `src/control/tools/dump_openapi.py`
- Desktop GUI / HTTP client：
  - `src/gui/desktop/`
  - `src/gui/services/`
- 非主線 handlers（已移除）：
  - `src/control/supervisor/handlers/run_research.py` (RUN_RESEARCH_V2)
  - `src/control/supervisor/handlers/generate_reports.py` (GENERATE_REPORTS)

## 3) 建議移除（仍在 repo，且非主線）
### A. Supervisor 非主線 handlers
> 若移除，需同步更新 `src/control/supervisor/__init__.py` 的 register。
- `src/control/supervisor/handlers/ping.py`
- `src/control/supervisor/handlers/clean_cache.py`
- `src/control/supervisor/handlers/run_plateau.py`
- `src/control/supervisor/handlers/run_freeze.py`
- `src/control/supervisor/handlers/run_compile.py`
- `src/control/supervisor/handlers/run_portfolio_admission.py`
- `src/control/supervisor/handlers/run_portfolio_admission_final.py`

**理由**：不在主線 job 清單，Local OS 不需。

### B. Control layer 的 legacy orchestration / API 殘留
- `src/control/batch_api.py`
- `src/control/season_api.py`
- `src/control/prepare_orchestration.py`
- `src/control/season_export.py`
- `src/control/season_export_replay.py`
- `src/control/research_service.py`
- `src/control/research_runner.py`
- `src/control/deploy_package_mc.py`
- `src/control/deploy_txt.py`
- `src/control/strategy_rotation.py`
- `src/control/action_queue.py`

**理由**：皆為過往 API / desktop / external deploy 路徑，主線已不使用。

### C. Contracts 中的 GUI / UI / API 合約
- `src/contracts/gui/`
- `src/contracts/ui/`
- `src/contracts/api.py`
- `src/contracts/ui_action_registry.py`
- `src/contracts/ui_api_coverage.py`
- `src/contracts/ui_governance_state.py`

**理由**：TUI 直連 sqlite + artifacts，不再需要 DTO / API coverage。

### D. Core 中的 API / Deployment / Persona
- `src/core/api/`
- `src/core/deployment/`
- `src/core/artifacts/`  *(注意：此模組目前引用已刪掉的 gui/services，屬於 dead code)*
- `src/core/artifact_writers.py` *(僅服務 deployment/reporting，主線未使用)*

**理由**：都是 API / deploy / 報告路徑，已不在 Local OS 主線。

## 4) 移除前置條件（不可忽略）
### TUI screens 連動刪除
若移除 `run_plateau / run_freeze / run_compile` handlers，請同步：
- `src/gui/tui/app.py`：移除對應 Screen import / 快捷鍵 / install_screen
- `src/gui/tui/screens/plateau.py`
- `src/gui/tui/screens/season_ops.py`

否則會造成 TUI 啟動 ImportError。

## 5) 明確保留但容易被誤刪
- `src/control/shared_build.py` + `src/control/shared_cli.py`  
  BUILD_BARS/BUILD_FEATURES/BUILD_DATA 透過 CLI subprocess 走這條鏈，刪了會讓 data prepare 失效。
- `src/control/bars_store.py`  
  TUI + WFS 讀 bars 必需。
- `src/core/backtest/kernel.py`  
  WFS 現在的 strategy equity 依賴此 kernel。

## 6) 建議執行順序
1) 先移除 C / D（contracts + core legacy）
2) 再移除 B（control legacy orchestration）
3) 最後移除 A（handlers + TUI screens 連動）
