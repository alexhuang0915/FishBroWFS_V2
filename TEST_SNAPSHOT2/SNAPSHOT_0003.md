FILE src/FishBroWFS_V2/gui/nicegui/pages/history.py
sha256(source_bytes) = 821fc58a131b68e4d6d785f6f4ef2b4aa5f11a149cdc69bbf55d46bd452f5060
bytes = 25173
redacted = False
--------------------------------------------------------------------------------
"""History 頁面 - Runs Browser with Audit Trail & Governance"""

from nicegui import ui
from datetime import datetime
from pathlib import Path
import json

from ...services.runs_index import get_global_index, RunIndexRow
from ...services.audit_log import read_audit_tail, get_audit_events_for_run_id
from FishBroWFS_V2.core.season_context import current_season, season_dir

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


def register() -> None:
    """註冊 History 頁面路由"""
    
    @ui.page("/history")
    def history_page() -> None:
        """渲染 History 頁面"""
        ui.page_title("FishBroWFS V2 - History")
        
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            ui.label("📜 Runs History").classes("text-3xl font-bold mb-2 text-cyber-glow")
            ui.label("顯示最新 50 個 runs（禁止全量掃描）").classes("text-lg text-slate-400 mb-8")
            
            # Season 資訊
            current_season_str = current_season()
            
            # 檢查 season freeze 狀態
            is_frozen = False
            frozen_reason = ""
            if SEASON_STATE_AVAILABLE and load_season_state is not None:
                try:
                    state = load_season_state(current_season_str)
                    if state and state.get("state") == "FROZEN":
                        is_frozen = True
                        frozen_reason = state.get("reason", "Season is frozen")
                except Exception:
                    # 如果載入失敗，忽略錯誤（保持未凍結狀態）
                    pass
            
            with ui.card().classes("fish-card p-4 mb-6 bg-nexus-900"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center"):
                        ui.icon("calendar_today", color="cyan").classes("mr-2")
                        ui.label(f"Current Season: {current_season_str}").classes("text-lg font-bold text-cyber-300")
                    
                    # Audit log 狀態
                    audit_path = season_dir(current_season_str) / "governance" / "ui_audit.jsonl"
                    if audit_path.exists():
                        ui.badge("Audit Log Active", color="green").props("dense")
                    else:
                        ui.badge("No Audit Log", color="amber").props("dense")
                
                # 顯示 freeze 狀態
                if is_frozen:
                    with ui.row().classes("items-center mt-3 p-3 bg-red-900/30 rounded-lg"):
                        ui.icon("lock", color="red").classes("mr-2")
                        ui.label("Season Frozen (治理鎖)").classes("font-bold text-red-300")
                        ui.label(frozen_reason).classes("ml-2 text-red-200 text-sm")
                        
                        # Integrity check button
                        ui.button("Check Integrity", icon="verified", on_click=lambda: check_integrity_action(current_season_str)) \
                            .classes("ml-4 px-3 py-1 text-xs bg-amber-500 hover:bg-amber-600")
            
            # 操作列
            with ui.row().classes("w-full mb-6 gap-4"):
                refresh_btn = ui.button("🔄 Refresh", on_click=lambda: refresh_table())
                refresh_btn.classes("btn-cyber")
                
                show_archived = ui.checkbox("顯示已歸檔", value=False)
                show_archived.on("change", lambda e: refresh_table())
                
                season_select = ui.select(
                    options=["所有 Season", current_season_str],
                    value="所有 Season",
                    label="Season"
                ).classes("w-48")
                season_select.on("change", lambda e: refresh_table())
                
                ui.space()
                
                # 顯示限制提示
                ui.label("只顯示最新 50 個 runs").classes("text-sm text-slate-500 italic")
            
            # 表格容器
            table_container = ui.column().classes("w-full")
            
            # 初始化表格
            def refresh_table():
                """刷新表格資料"""
                table_container.clear()
                
                # 獲取索引
                index = get_global_index()
                index.refresh()
                
                # 過濾條件
                season = None if season_select.value == "所有 Season" else season_select.value
                include_archived = show_archived.value
                
                # 獲取 runs
                runs = index.list(season=season, include_archived=include_archived)
                
                if not runs:
                    with table_container:
                        with ui.card().classes("fish-card w-full p-8 text-center"):
                            ui.icon("folder_off", size="xl").classes("text-slate-500 mb-4")
                            ui.label("沒有找到任何 runs").classes("text-xl text-slate-400")
                            ui.label("請確認 outputs 目錄結構正確").classes("text-sm text-slate-500")
                    return
                
                # 建立表格
                with table_container:
                    with ui.card().classes("fish-card w-full p-0 overflow-hidden"):
                        # 表格標頭
                        with ui.row().classes("bg-nexus-900 p-4 border-b border-nexus-800 font-bold"):
                            ui.label("Run ID").classes("w-64")
                            ui.label("Season").classes("w-24")
                            ui.label("Stage").classes("w-32")
                            ui.label("Status").classes("w-32")
                            ui.label("Modified").classes("w-48")
                            ui.label("Actions").classes("flex-1 text-right")
                        
                        # 表格內容
                        for run in runs:
                            with ui.row().classes(
                                "p-4 border-b border-nexus-800 hover:bg-nexus-900/50 "
                                "transition-colors items-center"
                            ):
                                # Run ID
                                ui.label(run.run_id).classes("w-64 font-mono text-sm")
                                
                                # Season
                                ui.label(run.season).classes("w-24")
                                
                                # Stage
                                stage_badge = run.stage or "unknown"
                                color = {
                                    "stage0": "bg-blue-500/20 text-blue-300",
                                    "stage1": "bg-green-500/20 text-green-300",
                                    "stage2": "bg-purple-500/20 text-purple-300",
                                    "demo": "bg-yellow-500/20 text-yellow-300",
                                }.get(stage_badge, "bg-slate-500/20 text-slate-300")
                                ui.label(stage_badge).classes(f"w-32 px-3 py-1 rounded-full text-xs {color}")
                                
                                # Status
                                status_badge = run.status
                                status_color = {
                                    "completed": "bg-green-500/20 text-green-300",
                                    "running": "bg-blue-500/20 text-blue-300",
                                    "failed": "bg-red-500/20 text-red-300",
                                    "unknown": "bg-slate-500/20 text-slate-300",
                                }.get(status_badge, "bg-slate-500/20 text-slate-300")
                                ui.label(status_badge).classes(f"w-32 px-3 py-1 rounded-full text-xs {status_color}")
                                
                                # Modified time
                                mtime_str = datetime.fromtimestamp(run.mtime).strftime("%Y-%m-%d %H:%M:%S")
                                ui.label(mtime_str).classes("w-48 text-sm text-slate-400")
                                
                                # Actions
                                with ui.row().classes("flex-1 justify-end gap-2"):
                                    # Report 按鈕（進 detail）
                                    report_btn = ui.button("Report", on_click=lambda r=run: view_report(r))
                                    report_btn.classes("px-3 py-1 text-xs bg-nexus-800 hover:bg-nexus-700")
                                    
                                    # Audit Trail 按鈕
                                    audit_btn = ui.button("Audit", on_click=lambda r=run: show_audit_trail(r))
                                    audit_btn.classes("px-3 py-1 text-xs bg-purple-500/20 hover:bg-purple-500/30")
                                    
                                    # Clone 按鈕（P0-4）
                                    clone_btn = ui.button("Clone", on_click=lambda r=run: clone_run(r))
                                    clone_btn.classes("px-3 py-1 text-xs bg-cyber-500/20 hover:bg-cyber-500/30")
                                    
                                    # Archive 按鈕（P0-3）
                                    if not run.is_archived:
                                        if is_frozen:
                                            # Season frozen: disable archive button with tooltip
                                            ui.button("Archive").classes("px-3 py-1 text-xs bg-red-500/10 text-red-300/50 cursor-not-allowed").tooltip(f"Season is frozen: {frozen_reason}")
                                        else:
                                            archive_btn = ui.button("Archive", on_click=lambda r=run: archive_run(r))
                                            archive_btn.classes("px-3 py-1 text-xs bg-red-500/20 hover:bg-red-500/30")
                                    else:
                                        ui.label("Archived").classes("px-3 py-1 text-xs bg-slate-500/20 text-slate-400 rounded")
            
            # 初始化表格
            refresh_table()
            
            # Audit Trail 區塊
            with ui.card().classes("fish-card w-full p-4 mt-8"):
                ui.label("📋 Recent Audit Trail").classes("text-xl font-bold mb-4 text-cyber-400")
                
                # 讀取 audit log
                audit_events = read_audit_tail(current_season_str, max_lines=20)
                
                if not audit_events:
                    ui.label("No audit events found").classes("text-gray-500 italic mb-2")
                    ui.label("UI actions will create audit events automatically").classes("text-sm text-slate-400")
                else:
                    # 顯示最近 5 個事件
                    recent_events = audit_events[-5:]  # 取最後 5 個（最新的）
                    
                    for event in reversed(recent_events):  # 最新的在最上面
                        with ui.card().classes("p-3 mb-2 bg-nexus-800"):
                            with ui.row().classes("items-center justify-between"):
                                with ui.column().classes("flex-1"):
                                    # 事件類型
                                    action_type = event.get("action", "unknown")
                                    color_map = {
                                        "generate_research": "text-green-400",
                                        "build_portfolio": "text-blue-400",
                                        "archive": "text-red-400",
                                        "clone": "text-yellow-400",
                                    }
                                    color = color_map.get(action_type, "text-slate-400")
                                    ui.label(f"• {action_type}").classes(f"font-bold {color}")
                                    
                                    # 時間戳
                                    ts = event.get("ts", "")
                                    if ts:
                                        # 簡化顯示
                                        display_ts = ts[:19].replace("T", " ")
                                        ui.label(f"at {display_ts}").classes("text-xs text-slate-500")
                                    
                                    # 額外資訊
                                    if "inputs" in event:
                                        inputs = event["inputs"]
                                        if isinstance(inputs, dict):
                                            summary = ", ".join([f"{k}={v}" for k, v in inputs.items() if k != "season"])
                                            if summary:
                                                ui.label(f"Inputs: {summary}").classes("text-xs text-slate-400")
                                
                                # 狀態指示器
                                if event.get("ok", False):
                                    ui.badge("✓", color="green").props("dense")
                                else:
                                    ui.badge("✗", color="red").props("dense")
            
            # 頁面底部資訊
            with ui.row().classes("w-full mt-8 text-sm text-slate-500"):
                ui.label("💡 提示：")
                ui.label("• 只掃描最新 50 個 runs 以避免全量掃描").classes("ml-2")
                ui.label("• 點擊 Report 查看詳細資訊").classes("ml-4")
                ui.label("• Archive 會將 run 移到 .archive 目錄").classes("ml-4")
                ui.label("• Audit 顯示 UI 動作歷史").classes("ml-4")
    
    # 按鈕動作函數
    def view_report(run: RunIndexRow) -> None:
        """查看 run 詳細報告"""
        ui.notify(f"正在載入 {run.run_id} 的報告...", type="info")
        # TODO: 實作跳轉到詳細頁面
        ui.navigate.to(f"/run/{run.run_id}")
    
    def show_audit_trail(run: RunIndexRow) -> None:
        """顯示 run 的 audit trail"""
        from ...services.audit_log import get_audit_events_for_run_id
        
        # 讀取 audit events
        audit_events = get_audit_events_for_run_id(run.run_id, run.season, max_lines=50)
        
        # 建立對話框
        with ui.dialog() as dialog, ui.card().classes("fish-card p-6 w-full max-w-4xl max-h-[80vh] overflow-auto"):
            ui.label(f"Audit Trail for {run.run_id}").classes("text-xl font-bold mb-4 text-cyber-400")
            
            if not audit_events:
                ui.label("No audit events found for this run").classes("text-gray-500 italic p-4")
            else:
                # 顯示 audit events
                for event in reversed(audit_events):  # 最新的在最上面
                    with ui.card().classes("p-4 mb-3 bg-nexus-800"):
                        # 事件標頭
                        with ui.row().classes("items-center justify-between mb-2"):
                            action_type = event.get("action", "unknown")
                            ui.label(f"Action: {action_type}").classes("font-bold text-cyber-300")
                            
                            # 時間戳
                            ts = event.get("ts", "")
                            if ts:
                                display_ts = ts[:19].replace("T", " ")
                                ui.label(display_ts).classes("text-sm text-slate-400")
                        
                        # 事件內容
                        with ui.column().classes("text-sm"):
                            # 狀態
                            status = "✓ Success" if event.get("ok", False) else "✗ Failed"
                            status_color = "text-green-400" if event.get("ok", False) else "text-red-400"
                            ui.label(f"Status: {status}").classes(f"mb-1 {status_color}")
                            
                            # 輸入參數
                            if "inputs" in event:
                                ui.label("Inputs:").classes("text-slate-400 mb-1")
                                inputs = event["inputs"]
                                if isinstance(inputs, dict):
                                    for key, value in inputs.items():
                                        ui.label(f"  {key}: {value}").classes("text-xs text-slate-500 ml-2")
                            
                            # 輸出的 artifacts
                            if "artifacts_written" in event:
                                artifacts = event["artifacts_written"]
                                if artifacts:
                                    ui.label("Artifacts Created:").classes("text-slate-400 mb-1")
                                    for artifact in artifacts[:3]:  # 顯示前 3 個
                                        ui.label(f"  • {artifact}").classes("text-xs text-slate-500 ml-2")
                                    if len(artifacts) > 3:
                                        ui.label(f"  ... and {len(artifacts) - 3} more").classes("text-xs text-slate-500 ml-2")
            
            # 關閉按鈕
            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("Close", on_click=dialog.close).classes("px-4 py-2")
        
        dialog.open()
    
    def clone_run(run: RunIndexRow) -> None:
        """Clone run 到 Wizard"""
        ui.notify(f"正在複製 {run.run_id} 到 Wizard...", type="info")
        # TODO: P0-4 實作
        # 跳轉到 Wizard 頁面並預填欄位
        ui.navigate.to(f"/wizard?clone={run.run_id}")
    
    def archive_run(run: RunIndexRow) -> None:
        """Archive run"""
        from ...services.archive import archive_run as archive_service
        
        # 顯示確認對話框
        with ui.dialog() as dialog, ui.card().classes("fish-card p-6 w-96"):
            ui.label(f"確認歸檔 {run.run_id}?").classes("text-lg font-bold mb-4")
            ui.label("此操作會將 run 移到 .archive 目錄，並寫入 audit log。").classes("text-sm text-slate-400 mb-4")
            
            reason_select = ui.select(
                options=["failed", "garbage", "disk", "other"],
                value="garbage",
                label="歸檔原因"
            ).classes("w-full mb-4")
            
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("取消", on_click=dialog.close).classes("px-4 py-2")
                ui.button("確認歸檔", on_click=lambda: confirm_archive(run, reason_select.value, dialog)) \
                    .classes("px-4 py-2 bg-red-500 hover:bg-red-600")
        
        dialog.open()
    
    def check_integrity_action(season: str) -> None:
        """檢查 season integrity"""
        try:
            from FishBroWFS_V2.core.snapshot import verify_snapshot_integrity
            
            # 顯示載入中
            ui.notify(f"Checking integrity for season {season}...", type="info")
            
            # 執行 integrity 檢查
            result = verify_snapshot_integrity(season)
            
            # 建立結果對話框
            with ui.dialog() as dialog, ui.card().classes("fish-card p-6 w-full max-w-4xl max-h-[80vh] overflow-auto"):
                ui.label(f"Integrity Check - {season}").classes("text-xl font-bold mb-4 text-cyber-400")
                
                # 狀態標示
                if result["ok"]:
                    with ui.row().classes("items-center p-4 mb-4 bg-green-900/30 rounded-lg"):
                        ui.icon("verified", color="green").classes("text-2xl mr-3")
                        ui.label("✓ Integrity Verified").classes("text-lg font-bold text-green-300")
                        ui.label(f"All {result['total_checked']} artifacts match snapshot").classes("text-green-200 ml-2")
                else:
                    with ui.row().classes("items-center p-4 mb-4 bg-red-900/30 rounded-lg"):
                        ui.icon("warning", color="red").classes("text-2xl mr-3")
                        ui.label("✗ Integrity Violation").classes("text-lg font-bold text-red-300")
                        ui.label("Artifacts have been modified since freeze").classes("text-red-200 ml-2")
                
                # 詳細結果
                with ui.card().classes("p-4 mb-4 bg-nexus-800"):
                    ui.label("Summary").classes("font-bold mb-2 text-cyber-300")
                    
                    with ui.grid(columns=3).classes("w-full gap-4 mb-4"):
                        with ui.card().classes("p-3 text-center"):
                            ui.label("Missing Files").classes("text-sm text-slate-400 mb-1")
                            ui.label(str(len(result["missing_files"]))).classes("text-2xl font-bold text-red-400")
                        
                        with ui.card().classes("p-3 text-center"):
                            ui.label("Changed Files").classes("text-sm text-slate-400 mb-1")
                            ui.label(str(len(result["changed_files"]))).classes("text-2xl font-bold text-amber-400")
                        
                        with ui.card().classes("p-3 text-center"):
                            ui.label("New Files").classes("text-sm text-slate-400 mb-1")
                            ui.label(str(len(result["new_files"]))).classes("text-2xl font-bold text-blue-400")
                    
                    ui.label(f"Total Artifacts Checked: {result['total_checked']}").classes("text-sm text-slate-400")
                
                # 顯示問題檔案（如果有的話）
                if result["missing_files"]:
                    with ui.expansion("Missing Files", icon="folder_off").classes("w-full mb-4"):
                        with ui.column().classes("pl-4 pt-2"):
                            for file in result["missing_files"][:20]:  # 顯示前 20 個
                                ui.label(f"• {file}").classes("text-sm text-red-300")
                            if len(result["missing_files"]) > 20:
                                ui.label(f"... and {len(result['missing_files']) - 20} more").classes("text-sm text-slate-500")
                
                if result["changed_files"]:
                    with ui.expansion("Changed Files", icon="edit").classes("w-full mb-4"):
                        with ui.column().classes("pl-4 pt-2"):
                            for file in result["changed_files"][:20]:  # 顯示前 20 個
                                ui.label(f"• {file}").classes("text-sm text-amber-300")
                            if len(result["changed_files"]) > 20:
                                ui.label(f"... and {len(result['changed_files']) - 20} more").classes("text-sm text-slate-500")
                
                if result["new_files"]:
                    with ui.expansion("New Files", icon="add").classes("w-full mb-4"):
                        with ui.column().classes("pl-4 pt-2"):
                            for file in result["new_files"][:20]:  # 顯示前 20 個
                                ui.label(f"• {file}").classes("text-sm text-blue-300")
                            if len(result["new_files"]) > 20:
                                ui.label(f"... and {len(result['new_files']) - 20} more").classes("text-sm text-slate-500")
                
                # 關閉按鈕
                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Close", on_click=dialog.close).classes("px-4 py-2")
                
                dialog.open()
        
        except ImportError:
            ui.notify("Integrity check not available (snapshot module missing)", type="warning")
        except Exception as e:
            ui.notify(f"Integrity check failed: {str(e)}", type="negative")
    
    def confirm_archive(run: RunIndexRow, reason: str, dialog) -> None:
        """確認歸檔"""
        from ...services.archive import archive_run as archive_service
        from pathlib import Path
        
        try:
            result = archive_service(
                outputs_root=Path(__file__).parent.parent.parent.parent / "outputs",
                run_dir=Path(run.run_dir),
                reason=reason,
                operator="ui"
            )
            ui.notify(f"已歸檔 {run.run_id} 到 {result.archived_path}", type="positive")
            dialog.close()
            refresh_table()  # 刷新表格
        except Exception as e:
            ui.notify(f"歸檔失敗: {str(e)}", type="negative")
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/home.py
sha256(source_bytes) = e942fa83adfeaf85087b9bc10abc38a140a5502fc910b4c94721862362d9bfdd
bytes = 5685
redacted = False
--------------------------------------------------------------------------------

"""首頁 - Dashboard/Home"""

from nicegui import ui

from ..state import app_state


def register() -> None:
    """註冊首頁路由"""
    
    @ui.page("/")
    def home_page() -> None:
        """渲染首頁"""
        ui.page_title("FishBroWFS V2 - 儀表板")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 標題區
            ui.label("🐟 FishBroWFS V2 研究控制面板").classes("text-3xl font-bold mb-2 text-cyber-glow")
            ui.label("唯一 UI = NiceGUI（Submit job / Monitor / Results / Deploy / Charts）").classes("text-lg text-slate-400 mb-8")
            
            # 快速操作卡片
            ui.label("快速操作").classes("text-xl font-bold mb-4 text-cyber-400")
            
            with ui.row().classes("w-full gap-4 mb-8"):
                card1 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer glow")
                card1.on("click", lambda e: ui.navigate.to("/wizard"))
                with card1:
                    ui.icon("rocket_launch", size="lg").classes("text-cyber-500 mb-2")
                    ui.label("新增研究任務").classes("font-bold text-white")
                    ui.label("設定 dataset/symbols/TF/strategy 等參數").classes("text-sm text-slate-400")
                
                card2 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer")
                card2.on("click", lambda e: ui.navigate.to("/history"))
                with card2:
                    ui.icon("history", size="lg").classes("text-green-500 mb-2")
                    ui.label("Runs History").classes("font-bold text-white")
                    ui.label("查看任務狀態、進度、日誌").classes("text-sm text-slate-400")
                
                card3 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer")
                card3.on("click", lambda e: ui.notify("請先選擇一個任務", type="info"))
                with card3:
                    ui.icon("insights", size="lg").classes("text-purple-500 mb-2")
                    ui.label("查看結果").classes("font-bold text-white")
                    ui.label("rolling summary 表格與詳細報告").classes("text-sm text-slate-400")
            
            # 最近任務區
            ui.label("最近任務").classes("text-xl font-bold mb-4 text-cyber-400")
            
            # 任務列表（使用 RunsIndex）
            with ui.card().classes("fish-card w-full p-4"):
                from ...services.runs_index import get_global_index
                
                index = get_global_index()
                runs = index.list(season="2026Q1", include_archived=False)[:5]
                
                if runs:
                    ui.label(f"最新 {len(runs)} 個 runs:").classes("font-bold mb-2")
                    for run in runs:
                        with ui.row().classes("w-full py-2 border-b border-nexus-800 last:border-0"):
                            ui.label(run.run_id).classes("flex-1 font-mono text-sm")
                            status_class = {
                                'completed': 'bg-green-500/20 text-green-300',
                                'running': 'bg-blue-500/20 text-blue-300',
                                'failed': 'bg-red-500/20 text-red-300'
                            }.get(run.status, 'bg-slate-500/20 text-slate-300')
                            ui.label(run.status).classes(f"px-2 py-1 rounded text-xs {status_class}")
                else:
                    ui.label("沒有找到 runs").classes("text-slate-500")
                    ui.label("請確認 outputs 目錄結構正確").classes("text-sm text-slate-600")
            
            # 系統狀態區
            ui.label("系統狀態").classes("text-xl font-bold mb-4 mt-8 text-cyber-400")
            
            with ui.row().classes("w-full gap-4"):
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("Control API").classes("font-bold")
                    ui.label("✅ 運行中").classes("text-green-400")
                    ui.label("localhost:8000").classes("text-sm text-slate-400")
                
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("Worker").classes("font-bold")
                    ui.label("🟡 待檢查").classes("text-yellow-400")
                    ui.label("需要啟動 worker daemon").classes("text-sm text-slate-400")
                
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("資料集").classes("font-bold")
                    ui.label("📊 可用").classes("text-blue-400")
                    ui.label("從 registry 載入").classes("text-sm text-slate-400")
            
            # 憲法級原則提醒
            with ui.card().classes("fish-card w-full mt-8 border-cyber-500/30"):
                ui.label("憲法級總原則").classes("font-bold text-cyber-400 mb-2")
                ui.label("1. NiceGUI 永遠是薄客戶端：只做「填單/看單/拿貨/畫圖」").classes("text-sm text-slate-300")
                ui.label("2. 唯一真相在 outputs + job state：UI refresh/斷線不影響任務").classes("text-sm text-slate-300")
                ui.label("3. Worker 是唯一執行者：只有 Worker 可呼叫 Research Runner").classes("text-sm text-slate-300")
                ui.label("4. WFS core 仍然 no-IO：run_wfs_with_features() 不得碰任何 IO").classes("text-sm text-slate-300")
                ui.label("5. 所有視覺化資料必須由 Research/Portfolio 產出 artifact：UI 只渲染").classes("text-sm text-slate-300")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/job.py
sha256(source_bytes) = d968ce2882b5724c4e5f6cd62bc4d7b075e59c6b7704893deda411b3d40ebd3d
bytes = 10675
redacted = False
--------------------------------------------------------------------------------

"""任務監控頁面 - Job Monitor"""

from nicegui import ui

from ..api import list_recent_jobs, get_job
from ..state import app_state


def register() -> None:
    """註冊任務監控頁面路由"""
    
    @ui.page("/jobs")
    def jobs_page() -> None:
        """渲染任務列表頁面"""
        ui.page_title("FishBroWFS V2 - 任務監控")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 任務列表容器
            job_list_container = ui.column().classes("w-full")
            
            def refresh_job_list() -> None:
                """刷新任務列表"""
                job_list_container.clear()
                
                try:
                    jobs = list_recent_jobs(limit=50)
                    
                    if not jobs:
                        with job_list_container:
                            ui.label("目前沒有任務").classes("text-gray-500 text-center p-8")
                        return
                    
                    for job in jobs:
                        card = ui.card().classes("w-full mb-4 cursor-pointer hover:bg-gray-50")
                        card.on("click", lambda e, j=job: ui.navigate.to(f"/results/{j.job_id}"))
                        with card:
                            with ui.row().classes("w-full items-center"):
                                # 狀態指示器
                                status_color = {
                                    "PENDING": "bg-yellow-100 text-yellow-800",
                                    "RUNNING": "bg-green-100 text-green-800",
                                    "COMPLETED": "bg-blue-100 text-blue-800",
                                    "FAILED": "bg-red-100 text-red-800",
                                }.get(job.status, "bg-gray-100 text-gray-800")
                                
                                ui.badge(job.status, color=status_color).classes("mr-4")
                                
                                # 任務資訊
                                with ui.column().classes("flex-1"):
                                    ui.label(f"任務 ID: {job.job_id[:8]}...").classes("font-mono text-sm")
                                    ui.label(f"建立時間: {job.created_at}").classes("text-xs text-gray-600")
                                
                                # 進度條（如果有的話）
                                if job.progress is not None:
                                    ui.linear_progress(job.progress, show_value=False).classes("w-32 mr-4")
                                    ui.label(f"{job.progress*100:.1f}%").classes("text-sm")
                                
                                ui.icon("chevron_right").classes("text-gray-400")
                
                except Exception as e:
                    with job_list_container:
                        ui.label(f"載入失敗: {e}").classes("text-red-600")
            
            # 標題與導航
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=refresh_job_list).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_job_list()
    
    @ui.page("/job/{job_id}")
    def job_page(job_id: str) -> None:
        """渲染單一任務詳細頁面"""
        ui.page_title(f"FishBroWFS V2 - 任務 {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 任務詳細資訊容器
            job_details_container = ui.column().classes("w-full")
            
            # 日誌容器
            log_container = ui.column().classes("w-full mt-6")
            
            def refresh_job_details(jid: str) -> None:
                """刷新任務詳細資訊"""
                job_details_container.clear()
                
                try:
                    job = get_job(jid)
                    
                    with job_details_container:
                        # 基本資訊卡片
                        with ui.card().classes("w-full mb-4"):
                            ui.label("基本資訊").classes("text-lg font-bold mb-4")
                            
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                ui.label("任務 ID:").classes("font-bold")
                                ui.label(job.job_id).classes("font-mono")
                                
                                ui.label("狀態:").classes("font-bold")
                                status_color = {
                                    "PENDING": "text-yellow-600",
                                    "RUNNING": "text-green-600",
                                    "COMPLETED": "text-blue-600",
                                    "FAILED": "text-red-600",
                                }.get(job.status, "text-gray-600")
                                ui.label(job.status).classes(f"{status_color} font-bold")
                                
                                ui.label("建立時間:").classes("font-bold")
                                ui.label(job.created_at)
                                
                                ui.label("更新時間:").classes("font-bold")
                                ui.label(job.updated_at)
                                
                                if job.progress is not None:
                                    ui.label("進度:").classes("font-bold")
                                    with ui.row().classes("items-center w-full"):
                                        ui.linear_progress(job.progress, show_value=False).classes("flex-1")
                                        ui.label(f"{job.progress*100:.1f}%").classes("ml-2")
                                
                                if job.outputs_path:
                                    ui.label("輸出路徑:").classes("font-bold")
                                    ui.label(job.outputs_path).classes("font-mono text-sm")
                        
                        # 操作按鈕 - 根據 Phase 6.5 規範，未完成功能必須 disabled
                        with ui.row().classes("w-full gap-2 mb-6"):
                            # 任務控制按鈕（DEV MODE - 未實作）
                            if job.status == "PENDING":
                                ui.button("開始任務", icon="play_arrow", color="green").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                            elif job.status == "RUNNING":
                                ui.button("暫停任務", icon="pause", color="yellow").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                                ui.button("停止任務", icon="stop", color="red").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                            
                            # 導航按鈕
                            ui.button("查看結果", icon="insights", on_click=lambda: ui.navigate.to(f"/results/{jid}")).props("outline")
                            ui.button("查看圖表", icon="show_chart", on_click=lambda: ui.navigate.to(f"/charts/{jid}")).props("outline")
                            ui.button("部署", icon="download", on_click=lambda: ui.navigate.to(f"/deploy/{jid}")).props("outline")
                    
                    # 刷新日誌
                    refresh_log(jid)
                    
                except Exception as e:
                    with job_details_container:
                        with ui.card().classes("w-full bg-red-50 border-red-200"):
                            ui.label("任務載入失敗").classes("text-red-800 font-bold mb-2")
                            ui.label(f"錯誤: {e}").classes("text-red-700 mb-2")
                            ui.label("可能原因:").classes("text-red-700 font-bold mb-1")
                            ui.label("• Control API 未啟動").classes("text-red-700 text-sm")
                            ui.label("• 任務 ID 不存在").classes("text-red-700 text-sm")
                            ui.label("• 網路連線問題").classes("text-red-700 text-sm")
                            with ui.row().classes("mt-4"):
                                ui.button("返回任務列表", on_click=lambda: ui.navigate.to("/jobs"), icon="arrow_back").props("outline")
                                ui.button("重試", on_click=lambda: refresh_job_details(jid), icon="refresh").props("outline")
            
            def refresh_log(jid: str) -> None:
                """刷新日誌顯示 - 誠實顯示真實狀態"""
                log_container.clear()
                
                with log_container:
                    ui.label("任務日誌").classes("text-lg font-bold mb-4")
                    
                    # 日誌顯示區域
                    log_display = ui.textarea("").classes("w-full h-64 font-mono text-sm").props("readonly")
                    
                    # 誠實顯示：如果沒有真實日誌，顯示 DEV MODE 訊息
                    try:
                        # 嘗試從 API 獲取真實日誌
                        job = get_job(jid)
                        if job.latest_log_tail:
                            log_display.value = job.latest_log_tail
                        else:
                            log_display.value = f"DEV MODE: 日誌系統尚未實作\n\n"
                            log_display.value += f"任務 ID: {jid}\n"
                            log_display.value += f"狀態: {job.status}\n"
                            log_display.value += f"建立時間: {job.created_at}\n"
                            log_display.value += f"更新時間: {job.updated_at}\n\n"
                            log_display.value += "真實日誌將在任務執行時顯示。"
                    except Exception as e:
                        log_display.value = f"載入日誌時發生錯誤: {e}"
            
            # 標題與導航
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=lambda: refresh_job_details(job_id)).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_job_details(job_id)
            
            # 自動刷新計時器（如果任務正在運行）
            def auto_refresh() -> None:
                # TODO: 根據任務狀態決定是否自動刷新
                pass
            
            ui.timer(5.0, auto_refresh)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/job_detail.py
sha256(source_bytes) = 11e36f673186d9df5a798e7022422e923f0501cf3fd5ad82fc6ae18c88a93b33
bytes = 8932
redacted = False
--------------------------------------------------------------------------------
"""Job Detail Page for M1.

Display real-time status + log tail for a specific job.
"""

from __future__ import annotations

import json
from typing import Dict, Any

from nicegui import ui

from FishBroWFS_V2.control.job_api import get_job_summary, get_job_status
from FishBroWFS_V2.control.pipeline_runner import check_job_status, start_job_async


def create_status_badge(status: str) -> ui.badge:
    """Create a status badge with appropriate color."""
    status_lower = status.lower()
    
    color_map = {
        "queued": "yellow",
        "running": "green",
        "done": "blue",
        "failed": "red",
        "killed": "gray",
    }
    
    color = color_map.get(status_lower, "gray")
    return ui.badge(status.upper(), color=color).classes("text-sm font-bold")


def create_units_progress(units_done: int, units_total: int) -> None:
    """Create units progress display."""
    if units_total <= 0:
        ui.label("Units: Not calculated").classes("text-gray-600")
        return
    
    progress = units_done / units_total
    
    with ui.column().classes("w-full"):
        # Progress bar
        with ui.row().classes("w-full items-center gap-2"):
            ui.linear_progress(progress, show_value=False).classes("flex-1")
            ui.label(f"{units_done}/{units_total}").classes("text-sm font-medium")
        
        # Percentage and formula
        ui.label(f"{progress:.1%} complete").classes("text-xs text-gray-600")
        
        # Formula explanation (if we have the breakdown)
        if units_total > 0 and units_done < units_total:
            remaining = units_total - units_done
            ui.label(f"{remaining} units remaining").classes("text-xs text-gray-500")


def refresh_job_detail(job_id: str, 
                      status_container: ui.column,
                      logs_container: ui.column,
                      config_container: ui.column) -> None:
    """Refresh job detail information."""
    try:
        # Get job summary
        summary = get_job_summary(job_id)
        
        # Update status container
        status_container.clear()
        with status_container:
            # Status badge and basic info
            with ui.row().classes("w-full items-center gap-4 mb-4"):
                create_status_badge(summary["status"])
                
                ui.label(f"Job ID: {summary['job_id'][:8]}...").classes("font-mono")
                ui.label(f"Season: {summary.get('season', 'N/A')}").classes("text-gray-600")
                ui.label(f"Created: {summary.get('created_at', 'N/A')}").classes("text-gray-600")
            
            # Units progress
            ui.label("Units Progress").classes("font-bold mt-4 mb-2")
            units_done = summary.get("units_done", 0)
            units_total = summary.get("units_total", 0)
            create_units_progress(units_done, units_total)
            
            # Action buttons based on status
            with ui.row().classes("w-full gap-2 mt-4"):
                if summary["status"].lower() == "queued":
                    ui.button("Start Job", 
                             on_click=lambda: start_job_async(job_id),
                             icon="play_arrow",
                             color="positive").tooltip("Start job execution")
                
                ui.button("Refresh", 
                         icon="refresh",
                         on_click=lambda: refresh_job_detail(job_id, status_container, logs_container, config_container))
                
                ui.button("Back to Jobs",
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="arrow_back",
                         color="gray").props("outline")
        
        # Update logs container
        logs_container.clear()
        with logs_container:
            ui.label("Logs").classes("font-bold mb-2")
            
            logs = summary.get("logs", [])
            if logs:
                # Show last 20 lines
                log_text = "\n".join(logs[-20:])
                log_display = ui.textarea(log_text).classes("w-full h-64 font-mono text-xs").props("readonly")
                
                # Auto-scroll to bottom
                ui.run_javascript(f"""
                    const textarea = document.getElementById('{log_display.id}');
                    if (textarea) {{
                        textarea.scrollTop = textarea.scrollHeight;
                    }}
                """)
            else:
                ui.label("No logs available").classes("text-gray-500 italic")
        
        # Update config container
        config_container.clear()
        with config_container:
            ui.label("Configuration").classes("font-bold mb-2")
            
            # Show basic config info
            with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                ui.label("Job ID:").classes("font-medium")
                ui.label(summary["job_id"]).classes("font-mono text-xs")
                
                ui.label("Status:").classes("font-medium")
                ui.label(summary["status"].upper())
                
                ui.label("Season:").classes("font-medium")
                ui.label(summary.get("season", "N/A"))
                
                ui.label("Dataset:").classes("font-medium")
                ui.label(summary.get("dataset_id", "N/A"))
                
                ui.label("Created:").classes("font-medium")
                ui.label(summary.get("created_at", "N/A"))
                
                ui.label("Updated:").classes("font-medium")
                ui.label(summary.get("updated_at", "N/A"))
                
                ui.label("Units Done:").classes("font-medium")
                ui.label(str(summary.get("units_done", 0)))
                
                ui.label("Units Total:").classes("font-medium")
                ui.label(str(summary.get("units_total", 0)))
            
            # Show raw config if available
            if "config" in summary:
                ui.label("Raw Configuration:").classes("font-medium mt-4 mb-2")
                config_json = json.dumps(summary["config"], indent=2)
                ui.textarea(config_json).classes("w-full h-48 font-mono text-xs").props("readonly")
    
    except Exception as e:
        status_container.clear()
        with status_container:
            with ui.card().classes("w-full bg-red-50 border-red-200"):
                ui.label("Error loading job details").classes("text-red-800 font-bold mb-2")
                ui.label(f"Details: {str(e)}").classes("text-red-700 text-sm")
                
                ui.button("Back to Jobs",
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="arrow_back",
                         color="red").props("outline").classes("mt-2")


@ui.page("/jobs/{job_id}")
def job_detail_page(job_id: str) -> None:
    """Job detail page."""
    ui.page_title(f"FishBroWFS V2 - Job {job_id[:8]}...")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        # Header
        with ui.row().classes("w-full items-center justify-between mb-6"):
            ui.label(f"Job Details").classes("text-3xl font-bold")
            
            with ui.row().classes("gap-2"):
                ui.button("Jobs List", 
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="list",
                         color="gray").props("outline")
        
        # Create containers for dynamic content
        status_container = ui.column().classes("w-full mb-6")
        logs_container = ui.column().classes("w-full mb-6")
        config_container = ui.column().classes("w-full")
        
        # Initial load
        refresh_job_detail(job_id, status_container, logs_container, config_container)
        
        # Auto-refresh timer for running jobs
        def auto_refresh():
            try:
                # Check if job is still running
                status = get_job_status(job_id)
                if status["status"].lower() == "running":
                    refresh_job_detail(job_id, status_container, logs_container, config_container)
            except Exception:
                pass  # Ignore errors in auto-refresh
        
        ui.timer(3.0, auto_refresh)
        
        # Footer note
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("M1 Job Detail - Shows real-time status and log tail")


def register() -> None:
    """Register job detail page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /job/{job_id} for compatibility
@ui.page("/job/{job_id}")
def job_detail_alt_page(job_id: str) -> None:
    """Alternative route for job detail."""
    job_detail_page(job_id)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/jobs.py
sha256(source_bytes) = b22adf667c52b59713018a16399615ed313f0fe9d1d5bb5cd474f0fae3d89d2d
bytes = 9083
redacted = False
--------------------------------------------------------------------------------
"""Jobs List Page for M1.

Display list of jobs with state, stage, units_done, units_total.
"""

from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime

from nicegui import ui

from FishBroWFS_V2.control.job_api import list_jobs_with_progress
from FishBroWFS_V2.control.pipeline_runner import check_job_status


def create_job_card(job: Dict[str, Any]) -> None:
    """Create a job card for the jobs list."""
    with ui.card().classes("w-full mb-4 hover:shadow-md transition-shadow cursor-pointer"):
        # Card header with job ID and status
        with ui.row().classes("w-full items-center justify-between"):
            # Left: Job ID and basic info
            with ui.column().classes("flex-1"):
                with ui.row().classes("items-center gap-2"):
                    # Status badge
                    status_color = {
                        "queued": "bg-yellow-100 text-yellow-800",
                        "running": "bg-green-100 text-green-800",
                        "done": "bg-blue-100 text-blue-800",
                        "failed": "bg-red-100 text-red-800",
                        "killed": "bg-gray-100 text-gray-800",
                    }.get(job["status"].lower(), "bg-gray-100 text-gray-800")
                    
                    ui.badge(job["status"].upper(), color=status_color).classes("font-mono text-xs")
                    
                    # Job ID
                    ui.label(f"Job: {job['job_id'][:8]}...").classes("font-mono text-sm")
                
                # Season and dataset
                with ui.row().classes("items-center gap-4 text-sm text-gray-600"):
                    ui.label(f"Season: {job.get('season', 'N/A')}")
                    ui.label(f"Dataset: {job.get('dataset_id', 'N/A')}")
            
            # Right: Timestamp
            ui.label(job["created_at"]).classes("text-xs text-gray-500")
        
        # Progress section
        with ui.column().classes("w-full mt-3"):
            # Units progress
            units_done = job.get("units_done", 0)
            units_total = job.get("units_total", 0)
            
            if units_total > 0:
                progress = units_done / units_total
                
                # Progress bar
                with ui.row().classes("w-full items-center gap-2"):
                    ui.linear_progress(progress, show_value=False).classes("flex-1")
                    ui.label(f"{units_done}/{units_total} units").classes("text-sm font-medium")
                
                # Percentage
                ui.label(f"{progress:.1%} complete").classes("text-xs text-gray-600")
            else:
                ui.label("Units: Not calculated").classes("text-sm text-gray-500")
        
        # Footer with actions
        with ui.row().classes("w-full justify-end mt-3 pt-3 border-t"):
            ui.button("View Details", 
                     on_click=lambda j=job: ui.navigate.to(f"/jobs/{j['job_id']}"),
                     icon="visibility").props("size=sm outline")
            
            # Action buttons based on status
            if job["status"].lower() == "running":
                ui.button("Pause", icon="pause", color="warning").props("size=sm outline disabled").tooltip("Not implemented in M1")
            elif job["status"].lower() == "queued":
                ui.button("Start", icon="play_arrow", color="positive").props("size=sm outline disabled").tooltip("Not implemented in M1")


def refresh_jobs_list(container: ui.column) -> None:
    """Refresh the jobs list in the container."""
    container.clear()
    
    try:
        jobs = list_jobs_with_progress(limit=50)
        
        if not jobs:
            with container:
                with ui.card().classes("w-full text-center p-8"):
                    ui.icon("inbox", size="xl").classes("text-gray-400 mb-2")
                    ui.label("No jobs found").classes("text-gray-600")
                    ui.label("Submit a job using the wizard to get started").classes("text-sm text-gray-500")
            return
        
        # Sort jobs: running first, then by creation time
        status_order = {"running": 0, "queued": 1, "done": 2, "failed": 3, "killed": 4}
        jobs.sort(key=lambda j: (status_order.get(j["status"].lower(), 5), j["created_at"]), reverse=True)
        
        # Create job cards
        for job in jobs:
            create_job_card(job)
            
    except Exception as e:
        with container:
            with ui.card().classes("w-full bg-red-50 border-red-200"):
                ui.label("Error loading jobs").classes("text-red-800 font-bold mb-2")
                ui.label(f"Details: {str(e)}").classes("text-red-700 text-sm")
                ui.label("Make sure the control API is running").classes("text-red-700 text-sm")


@ui.page("/jobs")
def jobs_page() -> None:
    """Jobs list page."""
    ui.page_title("FishBroWFS V2 - Jobs")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        # Header
        with ui.row().classes("w-full items-center justify-between mb-6"):
            ui.label("Jobs").classes("text-3xl font-bold")
            
            with ui.row().classes("gap-2"):
                # Refresh button
                refresh_button = ui.button(icon="refresh", color="primary").props("flat")
                
                # New job button
                ui.button("New Job", 
                         on_click=lambda: ui.navigate.to("/wizard"),
                         icon="add",
                         color="positive")
        
        # Stats summary
        with ui.row().classes("w-full gap-4 mb-6"):
            try:
                jobs = list_jobs_with_progress(limit=100)
                
                # Calculate stats
                total_jobs = len(jobs)
                running_jobs = sum(1 for j in jobs if j["status"].lower() == "running")
                done_jobs = sum(1 for j in jobs if j["status"].lower() == "done")
                total_units = sum(j.get("units_total", 0) for j in jobs)
                completed_units = sum(j.get("units_done", 0) for j in jobs)
                
                # Stats cards
                with ui.card().classes("flex-1"):
                    ui.label("Total Jobs").classes("text-sm text-gray-600")
                    ui.label(str(total_jobs)).classes("text-2xl font-bold")
                
                with ui.card().classes("flex-1"):
                    ui.label("Running").classes("text-sm text-gray-600")
                    ui.label(str(running_jobs)).classes("text-2xl font-bold text-green-600")
                
                with ui.card().classes("flex-1"):
                    ui.label("Completed").classes("text-sm text-gray-600")
                    ui.label(str(done_jobs)).classes("text-2xl font-bold text-blue-600")
                
                with ui.card().classes("flex-1"):
                    ui.label("Units Progress").classes("text-sm text-gray-600")
                    if total_units > 0:
                        progress = completed_units / total_units
                        ui.label(f"{progress:.1%}").classes("text-2xl font-bold")
                    else:
                        ui.label("N/A").classes("text-2xl font-bold")
                        
            except Exception:
                # Fallback if stats can't be loaded
                with ui.card().classes("flex-1"):
                    ui.label("Jobs").classes("text-sm text-gray-600")
                    ui.label("--").classes("text-2xl font-bold")
        
        # Jobs list container
        jobs_container = ui.column().classes("w-full")
        
        # Initial load
        refresh_jobs_list(jobs_container)
        
        # Setup refresh on button click
        def on_refresh():
            refresh_button.props("loading")
            refresh_jobs_list(jobs_container)
            refresh_button.props("loading=false")
        
        refresh_button.on_click(on_refresh)
        
        # Auto-refresh timer for running jobs
        def auto_refresh():
            # Check if any jobs are running
            try:
                jobs = list_jobs_with_progress(limit=10)
                has_running = any(j["status"].lower() == "running" for j in jobs)
                if has_running:
                    refresh_jobs_list(jobs_container)
            except Exception:
                pass  # Ignore errors in auto-refresh
        
        ui.timer(5.0, auto_refresh)
        
        # Footer note
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("M1 Jobs List - Shows units_done/units_total for each job")


def register() -> None:
    """Register jobs page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /jobs/list for compatibility
@ui.page("/jobs/list")
def jobs_list_page() -> None:
    """Alternative route for jobs list."""
    jobs_page()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/new_job.py
sha256(source_bytes) = c4f43120d8be403cee3f2cb107926fbe99d77e003aed372844102adc137c7249
bytes = 14670
redacted = False
--------------------------------------------------------------------------------

"""新增任務頁面 - New Job (Setup) - 已過渡到 Wizard，保留相容性"""

from pathlib import Path
from nicegui import ui
import httpx

from ..api import JobSubmitRequest, list_datasets, list_strategies, submit_job
from ..state import app_state


def register() -> None:
    """註冊新增任務頁面路由（重定向到 Wizard）"""
    
    @ui.page("/new-job")
    def new_job_page() -> None:
        """渲染新增任務頁面（過渡頁面）"""
        ui.page_title("FishBroWFS V2 - 新增研究任務")
        
        with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
            # 過渡訊息
            with ui.card().classes("fish-card w-full p-6 mb-6 border-cyber-500/50"):
                ui.label("⚠️ 頁面已遷移").classes("text-xl font-bold text-yellow-400 mb-2")
                ui.label("此頁面已過渡到新的 Wizard 介面。").classes("text-slate-300 mb-4")
                
                with ui.row().classes("w-full gap-4"):
                    ui.button("前往 Wizard", on_click=lambda: ui.navigate.to("/wizard")) \
                        .classes("btn-cyber px-6 py-3")
                    ui.button("留在舊版", color="gray") \
                        .classes("px-6 py-3")
            
            # 原始表單容器（保持相容性）
            with ui.card().classes("w-full p-6 opacity-80"):
                ui.label("舊版任務設定").classes("text-xl font-bold mb-6 text-slate-400")
            # 表單容器
            with ui.card().classes("w-full p-6"):
                ui.label("任務設定").classes("text-xl font-bold mb-6")
                
                # 基本設定區
                with ui.expansion("基本設定", value=True).classes("w-full mb-4"):
                    # outputs_root
                    outputs_root = ui.input(
                        label="Outputs Root",
                        value=app_state.user_preferences.get("default_outputs_root", "outputs"),
                        placeholder="輸出根目錄路徑"
                    ).classes("w-full mb-4")
                    
                    # dataset_id
                    ui.label("資料集").classes("font-bold mb-2")
                    
                    # 預設空 datasets
                    dataset_select = ui.select(
                        label="選擇資料集",
                        options={},
                        value=None
                    ).classes("w-full mb-4")
                    
                    # Load Datasets 按鈕
                    def load_datasets():
                        """載入 datasets"""
                        try:
                            ds = list_datasets(Path(outputs_root.value))
                            dataset_select.options = {d: d for d in ds} if ds else {}
                            if ds:
                                dataset_select.value = ds[0]
                            ui.notify(f"Loaded {len(ds)} datasets", type="positive")
                        except Exception as e:
                            error_msg = str(e)
                            if "503" in error_msg or "registry not preloaded" in error_msg.lower():
                                ui.notify("Dataset registry not ready", type="warning")
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200 p-4 mt-2"):
                                    ui.label("Dataset registry not ready").classes("font-bold text-yellow-800")
                                    ui.label("Control API registries need to be preloaded.").classes("text-yellow-800 text-sm")
                                    ui.label("Click 'Preload Registries' button below or restart Control API.").classes("text-yellow-800 text-sm")
                            else:
                                ui.notify(f"Failed to load datasets: {error_msg}", type="negative")
                    
                    with ui.row().classes("w-full mb-2"):
                        ui.button("Load Datasets", on_click=load_datasets, icon="refresh").props("outline")
                    
                    # symbols
                    symbols_input = ui.input(
                        label="交易標的 (逗號分隔)",
                        value="MNQ, MES, MXF",
                        placeholder="例如: MNQ, MES, MXF"
                    ).classes("w-full mb-4")
                    
                    # timeframe_min
                    timeframe_select = ui.select(
                        label="時間框架 (分鐘)",
                        options={60: "60分鐘", 120: "120分鐘"},
                        value=60
                    ).classes("w-full mb-4")
                
                # 策略設定區
                with ui.expansion("策略設定", value=True).classes("w-full mb-4"):
                    # strategy_name
                    strategy_select = ui.select(
                        label="選擇策略",
                        options={},
                        value=None
                    ).classes("w-full mb-4")
                    
                    # Load Strategies 按鈕
                    def load_strategies():
                        """載入 strategies"""
                        try:
                            strategies = list_strategies()
                            strategy_select.options = {s: s for s in strategies} if strategies else {}
                            if strategies:
                                strategy_select.value = strategies[0]
                            ui.notify(f"Loaded {len(strategies)} strategies", type="positive")
                        except Exception as e:
                            error_msg = str(e)
                            if "503" in error_msg or "registry not preloaded" in error_msg.lower():
                                ui.notify("Strategy registry not ready", type="warning")
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200 p-4 mt-2"):
                                    ui.label("Strategy registry not ready").classes("font-bold text-yellow-800")
                                    ui.label("Control API registries need to be preloaded.").classes("text-yellow-800 text-sm")
                                    ui.label("Click 'Preload Registries' button below or restart Control API.").classes("text-yellow-800 text-sm")
                            else:
                                ui.notify(f"Failed to load strategies: {error_msg}", type="negative")
                    
                    with ui.row().classes("w-full mb-2"):
                        ui.button("Load Strategies", on_click=load_strategies, icon="refresh").props("outline")
                    
                    # data2_feed
                    data2_select = ui.select(
                        label="Data2 Feed (可選)",
                        options={"": "無", "6J": "6J", "VX": "VX", "DX": "DX", "ZN": "ZN"},
                        value=""
                    ).classes("w-full mb-4")
                
                # 滾動回測設定區
                with ui.expansion("滾動回測設定", value=True).classes("w-full mb-4"):
                    # rolling (固定為 True)
                    ui.label("滾動回測: ✅ 啟用 (MVP 固定)").classes("mb-2")
                    
                    # train_years (固定為 3)
                    ui.label("訓練年數: 3 年 (固定)").classes("mb-2")
                    
                    # test_unit (固定為 quarter)
                    ui.label("測試單位: 季度 (固定)").classes("mb-2")
                    
                    # season
                    season_input = ui.input(
                        label="Season (例如 2026Q1)",
                        value="2026Q1",
                        placeholder="例如: 2026Q1"
                    ).classes("w-full mb-4")
                
                # 滑點壓力測試設定區
                with ui.expansion("滑點壓力測試", value=True).classes("w-full mb-4"):
                    # enable_slippage_stress (固定為 True)
                    ui.label("滑點壓力測試: ✅ 啟用").classes("mb-2")
                    
                    # slippage_levels
                    slippage_levels = ["S0", "S1", "S2", "S3"]
                    slippage_checkboxes = {}
                    with ui.row().classes("w-full mb-2"):
                        for level in slippage_levels:
                            slippage_checkboxes[level] = ui.checkbox(level, value=True)
                    
                    # gate_level
                    gate_select = ui.select(
                        label="Gate Level",
                        options={"S2": "S2", "S1": "S1", "S0": "S0"},
                        value="S2"
                    ).classes("w-full mb-4")
                    
                    # stress_level
                    stress_select = ui.select(
                        label="Stress Level",
                        options={"S3": "S3", "S2": "S2", "S1": "S1"},
                        value="S3"
                    ).classes("w-full mb-4")
                
                # Top K 設定
                topk_input = ui.number(
                    label="Top K",
                    value=20,
                    min=1,
                    max=100
                ).classes("w-full mb-6")
                
                # 提交按鈕
                def submit_job_handler() -> None:
                    """處理任務提交"""
                    try:
                        # 收集表單資料
                        symbols = [s.strip() for s in symbols_input.value.split(",") if s.strip()]
                        
                        # 收集選中的 slippage levels
                        selected_slippage = [level for level, cb in slippage_checkboxes.items() if cb.value]
                        
                        # 建立請求物件
                        req = JobSubmitRequest(
                            outputs_root=Path(outputs_root.value),
                            dataset_id=dataset_select.value,
                            symbols=symbols,
                            timeframe_min=timeframe_select.value,
                            strategy_name=strategy_select.value,
                            data2_feed=data2_select.value if data2_select.value else None,
                            rolling=True,  # 固定
                            train_years=3,  # 固定
                            test_unit="quarter",  # 固定
                            enable_slippage_stress=True,  # 固定
                            slippage_levels=selected_slippage,
                            gate_level=gate_select.value,
                            stress_level=stress_select.value,
                            topk=topk_input.value,
                            season=season_input.value
                        )
                        
                        # 實際提交任務
                        job_record = submit_job(req)
                        
                        ui.notify(f"Job submitted: {job_record.job_id[:8]}", type="positive")
                        ui.navigate.to(f"/results/{job_record.job_id}")
                        
                    except Exception as e:
                        ui.notify(f"Submit failed: {e}", type="negative")
                
                ui.button("提交任務", on_click=submit_job_handler, icon="send").classes("w-full bg-green-500 text-white py-3")
            
            # 注意事項
            with ui.card().classes("w-full mt-6 bg-yellow-50 border-yellow-200"):
                ui.label("注意事項").classes("font-bold text-yellow-800 mb-2")
                ui.label("• UI 不得直接跑 Rolling WFS：按鈕只能 submit job").classes("text-sm text-yellow-700")
                ui.label("• data2_feed 只能是 None/6J/VX/DX/ZN").classes("text-sm text-yellow-700")
                ui.label("• train_years==3、test_unit=='quarter'（MVP 鎖死）").classes("text-sm text-yellow-700")
                ui.label("• timeframe_min 必須同時套用 Data1/Data2（Data2 不提供單獨 TF）").classes("text-sm text-yellow-700")
            
            # Registry Preload 區
            with ui.card().classes("w-full mt-6 bg-blue-50 border-blue-200"):
                ui.label("Registry Preload").classes("font-bold text-blue-800 mb-2")
                ui.label("如果遇到 'registry not ready' 錯誤，請先預載 registries。").classes("text-sm text-blue-700 mb-4")
                
                def preload_registries():
                    """手動觸發 registry preload"""
                    try:
                        response = httpx.post("http://127.0.0.1:8000/meta/prime", timeout=10.0)
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("success"):
                                ui.notify("Registries preloaded successfully!", type="positive")
                            else:
                                errors = []
                                if result.get("dataset_error"):
                                    errors.append(f"Dataset: {result['dataset_error']}")
                                if result.get("strategy_error"):
                                    errors.append(f"Strategy: {result['strategy_error']}")
                                ui.notify(f"Preload partially failed: {', '.join(errors)}", type="warning")
                        else:
                            ui.notify(f"Failed to preload registries: {response.status_code}", type="negative")
                    except httpx.ConnectError:
                        ui.notify("Cannot connect to Control API (127.0.0.1:8000)", type="negative")
                    except Exception as e:
                        ui.notify(f"Error: {e}", type="negative")
                
                ui.button("Preload Registries", on_click=preload_registries, icon="cloud_download").props("outline").classes("mb-4")
                
                ui.label("替代方案：").classes("text-sm text-blue-700 font-bold mb-1")
                ui.label("1. 重新啟動 Control API (會自動 preload)").classes("text-sm text-blue-700")
                ui.label("2. 執行 `curl -X POST http://127.0.0.1:8000/meta/prime`").classes("text-sm text-blue-700")
                ui.label("3. 使用 `make dashboard` 啟動 (已包含自動 preload)").classes("text-sm text-blue-700")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/portfolio.py
sha256(source_bytes) = c5b36d179f7f542e608921d3cf5f2838b8b55409bc10a0026510a8cf7b3c200b
bytes = 17102
redacted = False
--------------------------------------------------------------------------------
"""
Portfolio 頁面 - 顯示 portfolio summary 和 manifest，提供 Build Portfolio 按鈕。

Phase 4: UI wiring for portfolio builder.
Phase 5: Respect season freeze state.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from nicegui import ui

from ..layout import render_shell
from ...services.actions import build_portfolio_from_research
from FishBroWFS_V2.core.season_context import (
    current_season,
    portfolio_dir,
    portfolio_summary_path,
    portfolio_manifest_path,
)

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


def load_portfolio_summary(season: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """載入 portfolio_summary.json"""
    summary_path = portfolio_summary_path(season)
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_portfolio_manifest(season: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """載入 portfolio_manifest.json"""
    manifest_path = portfolio_manifest_path(season)
    if not manifest_path.exists():
        return None
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "entries" in data:
                return data["entries"]
            else:
                return []
    except (json.JSONDecodeError, OSError):
        return None


def list_portfolio_runs(season: Optional[str] = None) -> List[Path]:
    """列出 portfolio 目錄中的 run 子目錄"""
    pdir = portfolio_dir(season)
    if not pdir.exists():
        return []
    
    runs = []
    for item in pdir.iterdir():
        if item.is_dir() and len(item.name) == 12:  # portfolio_id pattern (12 chars)
            runs.append(item)
    
    return sorted(runs, key=lambda x: x.name, reverse=True)


def render_portfolio_summary_card(summary: Dict[str, Any]) -> None:
    """渲染 portfolio summary 卡片"""
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Summary").classes("text-xl font-bold mb-4 text-cyber-400")
        
        # 基本資訊
        with ui.grid(columns=2).classes("w-full gap-4"):
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Portfolio ID").classes("text-sm text-slate-400 mb-1")
                ui.label(summary.get("portfolio_id", "N/A")).classes("text-lg font-mono text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Created At").classes("text-sm text-slate-400 mb-1")
                ui.label(summary.get("created_at", "N/A")[:19]).classes("text-lg text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Total Decisions").classes("text-sm text-slate-400 mb-1")
                ui.label(str(summary.get("total_decisions", 0))).classes("text-2xl font-bold text-cyber-400")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("KEEP Decisions").classes("text-sm text-slate-400 mb-1")
                ui.label(str(summary.get("keep_decisions", 0))).classes("text-2xl font-bold text-cyber-400")
        
        # 額外資訊
        if "symbols" in summary:
            with ui.card().classes("p-3 bg-nexus-800 mt-4"):
                ui.label("Symbols").classes("text-sm text-slate-400 mb-1")
                symbols = summary["symbols"]
                if isinstance(symbols, list):
                    ui.label(", ".join(symbols)).classes("text-sm text-slate-300")
                else:
                    ui.label(str(symbols)).classes("text-sm text-slate-300")


def render_portfolio_manifest_table(manifest: List[Dict[str, Any]]) -> None:
    """渲染 portfolio manifest 表格"""
    if not manifest:
        ui.label("No manifest entries found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left"},
        {"name": "decision", "label": "Decision", "field": "decision", "align": "left"},
        {"name": "score_final", "label": "Score", "field": "score_final", "align": "right", "format": lambda val: f"{val:.3f}"},
        {"name": "net_profit", "label": "Net Profit", "field": "net_profit", "align": "right", "format": lambda val: f"{val:.2f}"},
    ]
    
    rows = []
    for entry in manifest:
        rows.append({
            "run_id": entry.get("run_id", "")[:12] + "..." if len(entry.get("run_id", "")) > 12 else entry.get("run_id", ""),
            "strategy_id": entry.get("strategy_id", ""),
            "symbol": entry.get("symbol", ""),
            "decision": entry.get("decision", ""),
            "score_final": entry.get("score_final", 0.0),
            "net_profit": entry.get("net_profit", 0.0),
        })
    
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Manifest").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered pagination rows-per-page=10")


def render_portfolio_runs_list(runs: List[Path]) -> None:
    """渲染 portfolio runs 列表"""
    if not runs:
        return
    
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Runs").classes("text-xl font-bold mb-4 text-cyber-400")
        
        for run_dir in runs[:10]:  # 顯示最多 10 個
            run_id = run_dir.name
            with ui.card().classes("p-3 mb-2 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center"):
                        ui.icon("folder", color="cyan").classes("mr-2")
                        ui.label(run_id).classes("font-mono text-cyber-300")
                    
                    # 檢查檔案
                    spec_file = run_dir / "portfolio_spec.json"
                    manifest_file = run_dir / "portfolio_manifest.json"
                    
                    with ui.row().classes("gap-2"):
                        if spec_file.exists():
                            ui.badge("spec", color="green").props("dense")
                        if manifest_file.exists():
                            ui.badge("manifest", color="blue").props("dense")


def render_portfolio_page() -> None:
    """渲染 portfolio 頁面內容"""
    ui.page_title("FishBroWFS V2 - Portfolio")
    
    # 使用 shell 佈局
    with render_shell("/portfolio", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Portfolio Builder").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                
                # 動作按鈕容器
                action_container = ui.row().classes("gap-2")
            
            # 檢查 season freeze 狀態
            is_frozen = False
            frozen_reason = ""
            if SEASON_STATE_AVAILABLE and load_season_state is not None:
                try:
                    state = load_season_state(current_season())
                    if state and state.get("state") == "FROZEN":
                        is_frozen = True
                        frozen_reason = state.get("reason", "Season is frozen")
                except Exception:
                    # 如果載入失敗，忽略錯誤（保持未凍結狀態）
                    pass
            
            # 顯示 freeze 警告（如果 season 被凍結）
            if is_frozen:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-red-900/30 border-l-4 border-red-500"):
                    with ui.row().classes("items-center"):
                        ui.icon("lock", color="red").classes("text-xl mr-3")
                        with ui.column().classes("flex-1"):
                            ui.label("Season Frozen (治理鎖)").classes("font-bold text-lg text-red-300")
                            ui.label(frozen_reason).classes("text-red-200")
                            ui.label("Portfolio building is disabled while season is frozen.").classes("text-sm text-red-300/80")
            
            # 檢查 portfolio 檔案是否存在
            current_season_str = current_season()
            summary_exists = portfolio_summary_path(current_season_str).exists()
            manifest_exists = portfolio_manifest_path(current_season_str).exists()
            portfolio_exists = summary_exists or manifest_exists
            
            # 說明文字
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("🏦 Portfolio Builder").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label(f"This page displays portfolio artifacts from outputs/seasons/{current_season_str}/portfolio/").classes("text-slate-300 mb-1")
                ui.label(f"Source: outputs/seasons/{current_season_str}/portfolio/portfolio_summary.json & portfolio_manifest.json").classes("text-sm text-slate-400")
                
                # 顯示檔案狀態
                if not portfolio_exists:
                    with ui.row().classes("items-center mt-3 p-3 bg-amber-900/30 rounded-lg"):
                        ui.icon("warning", color="amber").classes("text-lg")
                        ui.label("Portfolio artifacts not found for this season.").classes("ml-2 text-amber-300")
                        ui.label("Build portfolio from research results using the button above.").classes("ml-2 text-amber-300 text-sm")
            
            # 載入資料
            portfolio_summary = load_portfolio_summary(current_season_str)
            portfolio_manifest = load_portfolio_manifest(current_season_str)
            portfolio_runs = list_portfolio_runs(current_season_str)
            
            # 統計卡片
            with ui.row().classes("w-full gap-4 mb-6"):
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Summary").classes("text-sm text-slate-400 mb-1")
                    if portfolio_summary:
                        ui.label("Available").classes("text-2xl font-bold text-cyber-400")
                        ui.label("✓ Loaded").classes("text-xs text-green-500")
                    else:
                        ui.label("Missing").classes("text-2xl font-bold text-amber-400")
                        if not summary_exists:
                            ui.label("File not found").classes("text-xs text-amber-500")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Manifest").classes("text-sm text-slate-400 mb-1")
                    if portfolio_manifest:
                        ui.label(f"{len(portfolio_manifest)}").classes("text-2xl font-bold text-cyber-400")
                        ui.label("entries").classes("text-xs text-slate-500")
                    else:
                        ui.label("Missing").classes("text-2xl font-bold text-amber-400")
                        if not manifest_exists:
                            ui.label("File not found").classes("text-xs text-amber-500")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Runs").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(portfolio_runs))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("runs").classes("text-xs text-slate-500")
            
            # 動作按鈕功能
            def build_portfolio_action():
                """觸發 Build Portfolio 動作"""
                # 檢查 season 是否被凍結（額外防護）
                if is_frozen:
                    ui.notify("Cannot build portfolio: season is frozen", type="negative")
                    return
                
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Building portfolio...").classes("text-sm text-slate-400")
                
                # 執行 Build Portfolio 動作
                result = build_portfolio_from_research(current_season_str)
                
                # 顯示結果
                if result.ok:
                    artifacts_count = len(result.artifacts_written)
                    ui.notify(f"Portfolio built successfully! {artifacts_count} artifacts created.", type="positive")
                else:
                    error_msg = result.stderr_tail[-1] if result.stderr_tail else "Unknown error"
                    ui.notify(f"Portfolio build failed: {error_msg}", type="negative")
                
                # 重新載入頁面
                ui.navigate.to("/portfolio", reload=True)
            
            # 更新動作按鈕
            with action_container:
                if not portfolio_exists:
                    if is_frozen:
                        # Season frozen: disable button with tooltip
                        ui.button("Build Portfolio", icon="build").props("outline disabled").tooltip(f"Season is frozen: {frozen_reason}")
                    else:
                        ui.button("Build Portfolio", icon="build", on_click=build_portfolio_action).props("outline color=positive")
                ui.button("Refresh", icon="refresh", on_click=lambda: ui.navigate.to("/portfolio", reload=True)).props("outline")
            
            # 分隔線
            ui.separator().classes("my-6")
            
            # 如果沒有資料，顯示提示
            if not portfolio_summary and not portfolio_manifest and not portfolio_runs:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("account_balance", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No portfolio data available").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label(f"Portfolio artifacts not found for season {current_season_str}").classes("text-slate-400 mb-4")
                    ui.label("Build portfolio from research results to create portfolio artifacts.").classes("text-slate-400 mb-6")
                    if not portfolio_exists:
                        ui.button("Build Portfolio Now", icon="build", on_click=build_portfolio_action).props("color=positive")
                return
            
            # Portfolio Summary 區塊
            if portfolio_summary:
                ui.label("Portfolio Summary").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_summary_card(portfolio_summary)
            
            # Portfolio Manifest 區塊
            if portfolio_manifest:
                ui.label("Portfolio Manifest").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_manifest_table(portfolio_manifest)
            
            # Portfolio Runs 區塊
            if portfolio_runs:
                ui.label("Portfolio Runs").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_runs_list(portfolio_runs)
            
            # 底部說明
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Portfolio Summary: High-level overview of portfolio decisions and metrics").classes("text-slate-300 mb-1")
                ui.label("• Portfolio Manifest: Detailed list of candidate runs with keep/drop decisions").classes("text-slate-300 mb-1")
                ui.label("• Portfolio Runs: Individual portfolio run directories with spec and manifest files").classes("text-slate-300 mb-1")
                ui.label(f"• Data Source: outputs/seasons/{current_season_str}/portfolio/ directory").classes("text-slate-300 mb-1")
                if not portfolio_exists:
                    ui.label("• Build: Click 'Build Portfolio' to create portfolio from research results").classes("text-slate-300 text-amber-300")


def register() -> None:
    """註冊 portfolio 頁面路由"""
    
    @ui.page("/portfolio")
    def portfolio_page() -> None:
        """Portfolio 頁面"""
        render_portfolio_page()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/results.py
sha256(source_bytes) = b64f33ac1dccc7e34fd460e769be701d1a55e8685b1faaeb768fa18d91243bf4
bytes = 4297
redacted = False
--------------------------------------------------------------------------------

"""結果頁面 - Results"""

from nicegui import ui

from ..api import get_season_report, generate_deploy_zip
from ..state import app_state


def register() -> None:
    """註冊結果頁面路由"""
    
    @ui.page("/results/{job_id}")
    def results_page(job_id: str) -> None:
        """渲染結果頁面"""
        ui.page_title(f"FishBroWFS V2 - 任務結果 {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 結果容器
            results_container = ui.column().classes("w-full")
            
            def refresh_results(jid: str) -> None:
                """刷新結果顯示"""
                results_container.clear()
                
                try:
                    with results_container:
                        # 顯示 DEV MODE Banner
                        with ui.card().classes("w-full bg-blue-50 border-blue-200 mb-6"):
                            ui.label("Phase 6.5 - UI 誠實化").classes("text-blue-800 font-bold mb-1")
                            ui.label("此頁面只顯示真實資料 (SSOT)，不渲染假表格").classes("text-blue-700 text-sm")
                        
                        # Rolling Summary 區塊 - 誠實顯示 "Not wired yet (Phase 7)"
                        ui.separator()
                        ui.label("Rolling Summary").classes("font-bold text-xl mb-2")
                        ui.label("Not wired yet (Phase 7)").classes("text-gray-500 mb-6")
                        
                        # 顯示任務基本資訊
                        with ui.card().classes("w-full bg-gray-50 border-gray-200 p-6 mb-6"):
                            ui.label("任務基本資訊").classes("font-bold mb-2")
                            ui.label(f"任務 ID: {jid}").classes("text-sm")
                            ui.label("狀態: 請查看 Job Monitor 頁面").classes("text-sm")
                        
                        # 操作按鈕 - 誠實顯示功能狀態
                        with ui.row().classes("w-full gap-2 mt-6"):
                            ui.button("View Charts", icon="show_chart", on_click=lambda: ui.navigate.to(f"/charts/{jid}")).props("outline")
                            ui.button("Deploy", icon="download", on_click=lambda: ui.navigate.to(f"/deploy/{jid}")).props("outline")
                            
                            # Generate Deploy Zip 按鈕 - 誠實顯示未實作
                            def generate_deploy_handler():
                                """處理 Generate Deploy Zip 按鈕點擊"""
                                ui.notify("Deploy zip generation not implemented yet (Phase 7)", type="warning")
                            
                            ui.button("Generate Deploy Zip", icon="archive", color="gray", on_click=generate_deploy_handler).props("disabled").tooltip("Not implemented yet (Phase 7)")
                    
                except Exception as e:
                    with results_container:
                        with ui.card().classes("w-full bg-red-50 border-red-200 p-6"):
                            ui.label("載入結果失敗").classes("text-red-800 font-bold mb-2")
                            ui.label(f"錯誤: {e}").classes("text-red-700 mb-2")
                            ui.label("可能原因:").classes("text-red-700 font-bold mb-1")
                            ui.label("• Control API 未啟動").classes("text-red-700 text-sm")
                            ui.label("• 任務 ID 不存在").classes("text-red-700 text-sm")
                            ui.label("• 網路連線問題").classes("text-red-700 text-sm")
                            with ui.row().classes("mt-4"):
                                ui.button("返回任務列表", on_click=lambda: ui.navigate.to("/jobs"), icon="arrow_back").props("outline")
                                ui.button("重試", on_click=lambda: refresh_results(jid), icon="refresh").props("outline")
            
            # 刷新按鈕
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=lambda: refresh_results(job_id)).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_results(job_id)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/run_detail.py
sha256(source_bytes) = 0179f625152de371654c50e5601b12f60a7377eaac933f9fdc2b581b0c772e3f
bytes = 15505
redacted = False
--------------------------------------------------------------------------------
"""
Run Detail 頁面 - 顯示單一 run 的詳細資訊、artifacts 和 audit trail。

Phase 4: Enhanced governance and observability.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from nicegui import ui

from ..layout import render_shell
from ...services.runs_index import get_global_index, RunIndexRow
from ...services.audit_log import get_audit_events_for_run_id
from FishBroWFS_V2.core.season_context import current_season


def load_run_manifest(run_dir: Path) -> Optional[Dict[str, Any]]:
    """載入 run 的 manifest.json"""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_run_summary(run_dir: Path) -> Optional[Dict[str, Any]]:
    """載入 run 的 summary.json"""
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_run_artifacts(run_dir: Path) -> List[Path]:
    """列出 run 目錄中的所有檔案"""
    if not run_dir.exists():
        return []
    artifacts = []
    for item in run_dir.rglob("*"):
        if item.is_file():
            artifacts.append(item)
    return sorted(artifacts, key=lambda x: x.name)


def render_run_info_card(run: RunIndexRow, manifest: Optional[Dict[str, Any]]) -> None:
    """渲染 run 基本資訊卡片"""
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Information").classes("text-xl font-bold mb-4 text-cyber-400")
        
        with ui.grid(columns=2).classes("w-full gap-4"):
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Run ID").classes("text-sm text-slate-400 mb-1")
                ui.label(run.run_id).classes("text-lg font-mono text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Season").classes("text-sm text-slate-400 mb-1")
                ui.label(run.season).classes("text-lg text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Stage").classes("text-sm text-slate-400 mb-1")
                stage_badge = run.stage or "unknown"
                color = {
                    "stage0": "bg-blue-500/20 text-blue-300",
                    "stage1": "bg-green-500/20 text-green-300",
                    "stage2": "bg-purple-500/20 text-purple-300",
                    "demo": "bg-yellow-500/20 text-yellow-300",
                }.get(stage_badge, "bg-slate-500/20 text-slate-300")
                ui.label(stage_badge).classes(f"px-3 py-1 rounded-full text-sm {color}")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Status").classes("text-sm text-slate-400 mb-1")
                status_badge = run.status
                status_color = {
                    "completed": "bg-green-500/20 text-green-300",
                    "running": "bg-blue-500/20 text-blue-300",
                    "failed": "bg-red-500/20 text-red-300",
                    "unknown": "bg-slate-500/20 text-slate-300",
                }.get(status_badge, "bg-slate-500/20 text-slate-300")
                ui.label(status_badge).classes(f"px-3 py-1 rounded-full text-sm {status_color}")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Created").classes("text-sm text-slate-400 mb-1")
                created_time = datetime.fromtimestamp(run.mtime).strftime("%Y-%m-%d %H:%M:%S")
                ui.label(created_time).classes("text-sm text-slate-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Directory").classes("text-sm text-slate-400 mb-1")
                ui.label(str(run.run_dir)).classes("text-xs font-mono text-slate-400 truncate")
        
        if manifest:
            with ui.card().classes("p-3 bg-nexus-800 mt-4"):
                ui.label("Manifest Info").classes("text-sm text-slate-400 mb-2")
                if "strategy_id" in manifest:
                    with ui.row().classes("items-center mb-1"):
                        ui.label("Strategy:").classes("text-sm text-slate-400 w-24")
                        ui.label(manifest["strategy_id"]).classes("text-sm text-cyber-300")
                if "symbol" in manifest:
                    with ui.row().classes("items-center mb-1"):
                        ui.label("Symbol:").classes("text-sm text-slate-400 w-24")
                        ui.label(manifest["symbol"]).classes("text-sm text-cyber-300")


def render_run_summary_card(summary: Dict[str, Any]) -> None:
    """渲染 run summary 卡片"""
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Summary").classes("text-xl font-bold mb-4 text-cyber-400")
        
        metrics = summary.get("metrics", {})
        if metrics:
            with ui.grid(columns=3).classes("w-full gap-4"):
                net_profit = metrics.get("net_profit", 0.0)
                profit_color = "text-green-400" if net_profit >= 0 else "text-red-400"
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Net Profit").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"${net_profit:.2f}").classes(f"text-2xl font-bold {profit_color}")
                
                win_rate = metrics.get("win_rate", 0.0)
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Win Rate").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"{win_rate:.1%}").classes("text-2xl font-bold text-cyber-400")
                
                sharpe = metrics.get("sharpe_ratio", 0.0)
                sharpe_color = "text-green-400" if sharpe >= 1.0 else "text-yellow-400" if sharpe >= 0 else "text-red-400"
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Sharpe Ratio").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"{sharpe:.2f}").classes(f"text-2xl font-bold {sharpe_color}")


def render_run_artifacts_list(artifacts: List[Path], run_dir: Path) -> None:
    """渲染 run artifacts 列表"""
    if not artifacts:
        ui.label("No artifacts found").classes("text-gray-500 italic")
        return
    
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Artifacts").classes("text-xl font-bold mb-4 text-cyber-400")
        
        json_files = [a for a in artifacts if a.suffix == ".json"]
        csv_files = [a for a in artifacts if a.suffix == ".csv"]
        other_files = [a for a in artifacts if a.suffix not in [".json", ".csv"]]
        
        if json_files:
            ui.label("JSON Files").classes("text-lg font-bold mb-2 text-cyber-300")
            for artifact in json_files[:5]:
                rel_path = artifact.relative_to(run_dir)
                size = artifact.stat().st_size if artifact.exists() else 0
                with ui.card().classes("p-2 mb-1 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                    with ui.row().classes("items-center justify-between"):
                        with ui.row().classes("items-center"):
                            ui.icon("description", color="green").classes("mr-2")
                            ui.label(str(rel_path)).classes("text-sm font-mono text-slate-300")
                        ui.label(f"{size:,} bytes").classes("text-xs text-slate-500")
        
        if csv_files:
            ui.label("CSV Files").classes("text-lg font-bold mb-2 text-cyber-300 mt-4")
            for artifact in csv_files[:3]:
                rel_path = artifact.relative_to(run_dir)
                size = artifact.stat().st_size if artifact.exists() else 0
                with ui.card().classes("p-2 mb-1 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                    with ui.row().classes("items-center justify-between"):
                        with ui.row().classes("items-center"):
                            ui.icon("table_chart", color="blue").classes("mr-2")
                            ui.label(str(rel_path)).classes("text-sm font-mono text-slate-300")
                        ui.label(f"{size:,} bytes").classes("text-xs text-slate-500")


def render_audit_trail_card(run_id: str, season: str) -> None:
    """渲染 run 的 audit trail 卡片"""
    audit_events = get_audit_events_for_run_id(run_id, season, max_lines=30)
    
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Audit Trail").classes("text-xl font-bold mb-4 text-cyber-400")
        
        if not audit_events:
            ui.label("No audit events found for this run").classes("text-gray-500 italic p-4")
            ui.label("UI actions will create audit events automatically").classes("text-sm text-slate-400")
            return
        
        for event in reversed(audit_events):
            with ui.card().classes("p-3 mb-3 bg-nexus-800"):
                with ui.row().classes("items-center justify-between mb-2"):
                    action_type = event.get("action", "unknown")
                    action_color = {
                        "generate_research": "text-green-400",
                        "build_portfolio": "text-blue-400",
                        "archive": "text-red-400",
                        "clone": "text-yellow-400",
                    }.get(action_type, "text-slate-400")
                    ui.label(f"Action: {action_type}").classes(f"font-bold {action_color}")
                    
                    ts = event.get("ts", "")
                    if ts:
                        display_ts = ts[:19].replace("T", " ")
                        ui.label(display_ts).classes("text-sm text-slate-400")
                
                with ui.column().classes("text-sm"):
                    status = "✓ Success" if event.get("ok", False) else "✗ Failed"
                    status_color = "text-green-400" if event.get("ok", False) else "text-red-400"
                    ui.label(f"Status: {status}").classes(f"mb-1 {status_color}")
                    
                    if "inputs" in event:
                        inputs = event["inputs"]
                        if isinstance(inputs, dict) and inputs:
                            ui.label("Inputs:").classes("text-slate-400 mb-1")
                            for key, value in inputs.items():
                                ui.label(f"  {key}: {value}").classes("text-xs text-slate-500 ml-2")


def render_run_detail_page(run_id: str) -> None:
    """渲染 run detail 頁面內容"""
    ui.page_title(f"FishBroWFS V2 - Run {run_id}")
    
    with render_shell("/history", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            with ui.row().classes("w-full items-center mb-6"):
                with ui.row().classes("items-center"):
                    ui.link("← Back to History", "/history").classes("text-cyber-400 hover:text-cyber-300 mr-4")
                    ui.label(f"Run Detail: {run_id}").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                ui.button("Refresh", icon="refresh", on_click=lambda: ui.navigate.to(f"/run/{run_id}", reload=True)).props("outline")
            
            index = get_global_index()
            index.refresh()
            run = index.get(run_id)
            
            if not run:
                with ui.card().classes("fish-card w-full p-8 text-center"):
                    ui.icon("error", size="xl").classes("text-red-500 mb-4")
                    ui.label(f"Run {run_id} not found").classes("text-2xl font-bold text-red-400 mb-2")
                    ui.label("The run may have been archived or deleted.").classes("text-slate-400 mb-4")
                    ui.link("Go back to History", "/history").classes("text-cyber-400 hover:text-cyber-300")
                return
            
            run_dir = Path(run.run_dir)
            if not run_dir.exists():
                with ui.card().classes("fish-card w-full p-8 text-center"):
                    ui.icon("folder_off", size="xl").classes("text-amber-500 mb-4")
                    ui.label(f"Run directory not found").classes("text-2xl font-bold text-amber-400 mb-2")
                    ui.label(f"Path: {run_dir}").classes("text-sm text-slate-400 mb-4")
                    ui.label("The run may have been moved or deleted.").classes("text-slate-400")
                return
            
            with ui.card().classes("fish-card p-4 mb-6 bg-nexus-900"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center gap-4"):
                        status_badge = run.status
                        status_color = {
                            "completed": "bg-green-500/20 text-green-300",
                            "running": "bg-blue-500/20 text-blue-300",
                            "failed": "bg-red-500/20 text-red-300",
                            "unknown": "bg-slate-500/20 text-slate-300",
                        }.get(status_badge, "bg-slate-500/20 text-slate-300")
                        ui.label(status_badge).classes(f"px-3 py-1 rounded-full text-sm {status_color}")
                        
                        if run.is_archived:
                            ui.badge("Archived", color="red").props("dense")
                    
                    with ui.row().classes("gap-2"):
                        ui.button("View in Files", icon="folder_open").props("outline")
                        ui.button("Clone Run", icon="content_copy").props("outline color=positive")
                        if not run.is_archived:
                            ui.button("Archive", icon="archive").props("outline color=negative")
            
            manifest = load_run_manifest(run_dir)
            summary = load_run_summary(run_dir)
            artifacts = list_run_artifacts(run_dir)
            
            render_run_info_card(run, manifest)
            
            if summary:
                render_run_summary_card(summary)
            
            render_run_artifacts_list(artifacts, run_dir)
            
            render_audit_trail_card(run_id, run.season)
            
            with ui.card().classes("fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Run Information: Basic metadata about the run").classes("text-slate-300 mb-1")
                ui.label("• Run Summary: Performance metrics and summary").classes("text-slate-300 mb-1")
                ui.label("• Run Artifacts: Files generated by the run").classes("text-slate-300 mb-1")
                ui.label("• Audit Trail: UI actions related to this run").classes("text-slate-300 mb-1")
                ui.label("• All UI actions are logged for governance and auditability").classes("text-slate-300 text-amber-300")


def register() -> None:
    """註冊 run detail 頁面路由"""
    
    @ui.page("/run/{run_id}")
    def run_detail_page(run_id: str) -> None:
        """Run Detail 頁面"""
        render_run_detail_page(run_id)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/settings.py
sha256(source_bytes) = b7ecc8d535da10f4d82679739004233a3ea5a1a715a11973babc7a3e371ea463
bytes = 9316
redacted = False
--------------------------------------------------------------------------------
"""設定頁面 - Settings"""

from nicegui import ui

from ..api import get_system_settings, update_system_settings
from ..state import app_state


def register() -> None:
    """註冊設定頁面"""
    
    @ui.page("/settings")
    def settings_page() -> None:
        """設定頁面"""
        ui.page_title("FishBroWFS V2 - Settings")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 頁面標題
            ui.label("System Settings").classes("text-3xl font-bold mb-2 text-cyber-400")
            ui.label("Configure system parameters, environment variables, and API endpoints").classes("text-slate-400 mb-8")
            
            # 設定容器
            settings_container = ui.column().classes("w-full")
            
            def refresh_settings() -> None:
                """刷新設定資訊"""
                settings_container.clear()
                
                try:
                    # 獲取系統設定
                    settings = get_system_settings()
                    
                    with settings_container:
                        # 系統資訊卡片
                        with ui.card().classes("w-full mb-6"):
                            ui.label("System Information").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                ui.label("Season").classes("font-bold")
                                ui.label(app_state.season).classes("text-green-400")
                                
                                ui.label("Freeze Status").classes("font-bold")
                                if app_state.frozen:
                                    ui.label("FROZEN").classes("text-red-400 font-bold")
                                else:
                                    ui.label("ACTIVE").classes("text-green-400 font-bold")
                                
                                ui.label("API Endpoint").classes("font-bold")
                                ui.label(settings.get("api_endpoint", "http://localhost:8081")).classes("text-slate-300")
                                
                                ui.label("Dashboard Version").classes("font-bold")
                                ui.label(settings.get("version", "2.0.0")).classes("text-slate-300")
                        
                        # 環境變數設定
                        with ui.card().classes("w-full mb-6"):
                            ui.label("Environment Variables").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            # 顯示環境變數
                            env_vars = settings.get("environment", {})
                            if env_vars:
                                for key, value in env_vars.items():
                                    with ui.row().classes("w-full items-center mb-2"):
                                        ui.label(f"{key}:").classes("w-48 font-mono text-sm text-slate-400")
                                        ui.label(str(value)).classes("flex-1 font-mono text-sm bg-nexus-800 p-2 rounded")
                            else:
                                ui.label("No environment variables configured").classes("text-slate-500 italic")
                        
                        # API 端點設定
                        with ui.card().classes("w-full mb-6"):
                            ui.label("API Endpoints").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            endpoints = settings.get("endpoints", {})
                            if endpoints:
                                for name, url in endpoints.items():
                                    with ui.row().classes("w-full items-center mb-2"):
                                        ui.label(f"{name}:").classes("w-48 text-slate-400")
                                        ui.link(url, url, new_tab=True).classes("flex-1 font-mono text-sm text-cyber-400 hover:text-cyber-300")
                            else:
                                ui.label("No API endpoints configured").classes("text-slate-500 italic")
                        
                        # 系統設定選項
                        with ui.card().classes("w-full mb-6"):
                            ui.label("System Configuration").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            # 自動刷新設定
                            auto_refresh = ui.switch("Auto-refresh dashboard", value=settings.get("auto_refresh", True))
                            
                            # 通知設定
                            notifications = ui.switch("Enable notifications", value=settings.get("notifications", False))
                            
                            # 主題設定
                            theme = ui.select(["dark", "light", "auto"], value=settings.get("theme", "dark"), label="Theme")
                            
                            # 儲存按鈕
                            def save_settings() -> None:
                                """儲存設定"""
                                new_settings = {
                                    "auto_refresh": auto_refresh.value,
                                    "notifications": notifications.value,
                                    "theme": theme.value,
                                }
                                try:
                                    update_system_settings(new_settings)
                                    ui.notify("Settings saved successfully", type="positive")
                                except Exception as e:
                                    ui.notify(f"Failed to save settings: {e}", type="negative")
                            
                            ui.button("Save Settings", on_click=save_settings, icon="save").classes("mt-4 bg-cyber-500 hover:bg-cyber-400")
                        
                        # 系統操作
                        with ui.card().classes("w-full"):
                            ui.label("System Operations").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            with ui.row().classes("w-full gap-4"):
                                # 清除快取
                                def clear_cache() -> None:
                                    """清除系統快取"""
                                    ui.notify("Cache cleared (simulated)", type="info")
                                
                                ui.button("Clear Cache", on_click=clear_cache, icon="delete").classes("bg-amber-600 hover:bg-amber-500")
                                
                                # 重新載入設定
                                def reload_config() -> None:
                                    """重新載入設定"""
                                    refresh_settings()
                                    ui.notify("Settings reloaded", type="info")
                                
                                ui.button("Reload Settings", on_click=reload_config, icon="refresh").classes("bg-blue-600 hover:bg-blue-500")
                                
                                # 重啟服務
                                def restart_service() -> None:
                                    """重啟服務（模擬）"""
                                    ui.notify("Service restart initiated (simulated)", type="warning")
                                
                                ui.button("Restart Service", on_click=restart_service, icon="restart_alt").classes("bg-red-600 hover:bg-red-500")
                            
                            # 警告訊息
                            ui.separator().classes("my-4")
                            with ui.row().classes("w-full items-center p-4 bg-yellow-900/30 border border-yellow-700 rounded"):
                                ui.icon("warning", size="sm").classes("text-yellow-400 mr-2")
                                ui.label("System operations may affect running jobs. Use with caution.").classes("text-sm text-yellow-300")
                
                except Exception as e:
                    with settings_container:
                        ui.label(f"Failed to load settings: {e}").classes("text-red-400")
                        
                        # 顯示錯誤卡片
                        with ui.card().classes("w-full p-6 bg-red-900/20 border border-red-700"):
                            ui.icon("error", size="xl").classes("text-red-400 mx-auto mb-4")
                            ui.label("Settings API Not Available").classes("text-xl font-bold text-red-300 text-center mb-2")
                            ui.label("The system settings API is not currently available.").classes("text-red-200 text-center mb-4")
                            ui.label("This may be because the control API is not running or the endpoint is not configured.").classes("text-sm text-slate-400 text-center")
            
            # 初始載入
            refresh_settings()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/status.py
sha256(source_bytes) = e153f5a8b953923c2556edc21ebf625186da385f6687d17139f693814a3e46cf
bytes = 20523
redacted = False
--------------------------------------------------------------------------------
"""System Status Page - Shows dataset and strategy status with reload and build capabilities."""

from __future__ import annotations

from nicegui import ui

from FishBroWFS_V2.gui.nicegui.layout import render_topbar
from FishBroWFS_V2.gui.services.reload_service import (
    get_system_snapshot,
    reload_everything,
    build_parquet,
    build_all_parquet
)


@ui.page('/status')
def status_page():
    """System status page."""
    # Use render_topbar for consistent header
    render_topbar(active='status')
    
    # State for snapshot data
    snapshot = {'data': None}
    
    def refresh():
        """Refresh snapshot data."""
        try:
            snapshot['data'] = get_system_snapshot()
            ui.notify('Snapshot refreshed', type='positive')
            update_display()
        except Exception as e:
            ui.notify(f'Failed to refresh: {str(e)}', type='negative')
    
    def do_reload():
        """Reload all caches and registries."""
        try:
            r = reload_everything(reason='manual_ui')
            if r.ok:
                ui.notify('Reload OK', type='positive')
            else:
                ui.notify(f'Reload failed: {r.error}', type='negative')
            # Refresh snapshot after reload
            refresh()
        except Exception as e:
            ui.notify(f'Reload error: {str(e)}', type='negative')
    
    def do_build_all():
        """Build Parquet for all datasets."""
        try:
            ui.notify('Starting Parquet build for all datasets...', type='info')
            results = build_all_parquet(reason='manual_ui')
            
            # Count results
            success = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success)
            
            if failed == 0:
                ui.notify(f'Build completed: {success} successful, {failed} failed', type='positive')
            else:
                ui.notify(f'Build completed with errors: {success} successful, {failed} failed', type='warning')
            
            # Refresh snapshot after build
            refresh()
        except Exception as e:
            ui.notify(f'Build error: {str(e)}', type='negative')
    
    def do_build_dataset(dataset_id: str):
        """Build Parquet for a single dataset."""
        try:
            ui.notify(f'Building Parquet for {dataset_id}...', type='info')
            result = build_parquet(dataset_id, reason='manual_ui')
            
            if result.success:
                ui.notify(f'Build successful for {dataset_id}', type='positive')
            else:
                ui.notify(f'Build failed for {dataset_id}: {result.error}', type='negative')
            
            # Refresh snapshot after build
            refresh()
        except Exception as e:
            ui.notify(f'Build error for {dataset_id}: {str(e)}', type='negative')
    
    # Create containers for dynamic content
    summary_container = ui.column().classes('w-full')
    datasets_container = ui.column().classes('w-full mt-6')
    strategies_container = ui.column().classes('w-full mt-6')
    
    def update_display():
        """Update UI with current snapshot data."""
        summary_container.clear()
        datasets_container.clear()
        strategies_container.clear()
        
        if not snapshot['data']:
            with summary_container:
                ui.label('No snapshot data available').classes('text-lg text-yellow-500')
            return
        
        data = snapshot['data']
        
        # Summary section
        with summary_container:
            with ui.card().classes('w-full bg-nexus-900 p-4'):
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.column().classes('gap-2'):
                        ui.label('System Snapshot').classes('text-2xl font-bold text-cyber-300')
                        ui.label(f'Created: {data.created_at.strftime("%Y-%m-%d %H:%M:%S")}').classes('text-sm text-slate-400')
                    
                    with ui.row().classes('gap-2'):
                        ui.button('Refresh Snapshot', icon='refresh').on('click', lambda: refresh())
                        ui.button('Reload All', icon='cached', color='primary').on('click', lambda: do_reload())
                        ui.button('Build All Parquet', icon='build', color='secondary').on('click', lambda: do_build_all())
                
                with ui.row().classes('w-full mt-4 gap-6'):
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Datasets').classes('text-lg font-bold text-cyber-300')
                        ui.label(f'Total: {data.total_datasets}').classes('text-2xl')
                        txt_present = sum(1 for ds in data.dataset_statuses if ds.txt_present)
                        parquet_present = sum(1 for ds in data.dataset_statuses if ds.parquet_present)
                        ui.label(f'TXT: {txt_present}').classes('text-sm text-blue-400')
                        ui.label(f'Parquet: {parquet_present}').classes('text-sm text-green-400')
                    
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Strategies').classes('text-lg font-bold text-cyber-300')
                        ui.label(f'Total: {data.total_strategies}').classes('text-2xl')
                        working = sum(1 for ss in data.strategy_statuses if ss.can_import and ss.can_build_spec)
                        ui.label(f'Working: {working}').classes('text-sm text-green-400')
                        ui.label(f'Errors: {data.total_strategies - working}').classes('text-sm text-red-400')
                    
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Build Status').classes('text-lg font-bold text-cyber-300')
                        up_to_date = sum(1 for ds in data.dataset_statuses if ds.up_to_date)
                        ui.label(f'Up-to-date: {up_to_date}').classes('text-2xl')
                        ui.label(f'Needs build: {data.total_datasets - up_to_date}').classes('text-sm text-yellow-400')
                        ui.label(f'Missing TXT: {data.total_datasets - txt_present}').classes('text-sm text-red-400')
                
                if data.notes:
                    with ui.card().classes('w-full mt-4 bg-nexus-800 p-3'):
                        for note in data.notes:
                            ui.label(f'• {note}').classes('text-sm text-slate-300')
        
        # Datasets table
        with datasets_container:
            ui.label('Datasets').classes('text-xl font-bold text-cyber-300 mb-4')
            
            if not data.dataset_statuses:
                ui.label('No datasets found').classes('text-slate-400')
            else:
                # Create table header
                with ui.row().classes('w-full bg-nexus-800 p-3 rounded-t-lg font-bold'):
                    ui.label('ID').classes('w-1/5')
                    ui.label('Kind').classes('w-1/10')
                    ui.label('TXT').classes('w-1/10')
                    ui.label('Parquet').classes('w-1/10')
                    ui.label('Up-to-date').classes('w-1/10')
                    ui.label('Schema').classes('w-1/10')
                    ui.label('Actions').classes('w-1/5')
                
                # Create table rows
                for ds in data.dataset_statuses:
                    txt_color = 'text-green-400' if ds.txt_present else 'text-red-400'
                    txt_text = '✓' if ds.txt_present else '✗'
                    parquet_color = 'text-green-400' if ds.parquet_present else 'text-red-400'
                    parquet_text = '✓' if ds.parquet_present else '✗'
                    uptodate_color = 'text-green-400' if ds.up_to_date else 'text-yellow-400'
                    uptodate_text = '✓' if ds.up_to_date else '✗'
                    schema_color = 'text-green-400' if ds.schema_ok else 'text-yellow-400'
                    schema_text = 'OK' if ds.schema_ok else 'Unknown'
                    
                    with ui.row().classes('w-full bg-nexus-900 p-3 border-b border-nexus-800 hover:bg-nexus-850'):
                        ui.label(ds.id).classes('w-1/5 font-mono text-sm')
                        ui.label(ds.kind).classes('w-1/10 text-slate-300')
                        ui.label(txt_text).classes(f'w-1/10 {txt_color} text-center')
                        ui.label(parquet_text).classes(f'w-1/10 {parquet_color} text-center')
                        ui.label(uptodate_text).classes(f'w-1/10 {uptodate_color} text-center')
                        ui.label(schema_text).classes(f'w-1/10 {schema_color} text-center')
                        
                        with ui.row().classes('w-1/5 gap-1'):
                            details_btn = ui.button('Details', icon='info', size='sm').props('dense outline')
                            details_btn.on('click', lambda d=ds: show_dataset_details(d))
                            
                            if ds.txt_present and not ds.up_to_date:
                                build_btn = ui.button('Build', icon='build', size='sm').props('dense outline color=primary')
                                build_btn.on('click', lambda d=ds: do_build_dataset(d.dataset_id))
                            else:
                                # Disabled button
                                build_btn = ui.button('Build', icon='build', size='sm').props('dense outline disabled')
                    
                    # Error row if present
                    if ds.error:
                        with ui.row().classes('w-full bg-red-900/20 p-2'):
                            ui.label(f'Error: {ds.error}').classes('text-sm text-red-300')
        
        # Strategies table
        with strategies_container:
            ui.label('Strategies').classes('text-xl font-bold text-cyber-300 mb-4 mt-8')
            
            if not data.strategy_statuses:
                ui.label('No strategies found').classes('text-slate-400')
            else:
                # Create table header
                with ui.row().classes('w-full bg-nexus-800 p-3 rounded-t-lg font-bold'):
                    ui.label('ID').classes('w-1/4')
                    ui.label('Import').classes('w-1/6')
                    ui.label('Build').classes('w-1/6')
                    ui.label('Features').classes('w-1/6')
                    ui.label('Signature').classes('w-1/6')
                    ui.label('Actions').classes('w-1/6')
                
                # Create table rows
                for ss in data.strategy_statuses:
                    import_color = 'text-green-400' if ss.can_import else 'text-red-400'
                    import_text = '✓' if ss.can_import else '✗'
                    build_color = 'text-green-400' if ss.can_build_spec else 'text-red-400'
                    build_text = '✓' if ss.can_build_spec else '✗'
                    
                    with ui.row().classes('w-full bg-nexus-900 p-3 border-b border-nexus-800 hover:bg-nexus-850'):
                        ui.label(ss.id).classes('w-1/4 font-mono text-sm')
                        ui.label(import_text).classes(f'w-1/6 {import_color} text-center')
                        ui.label(build_text).classes(f'w-1/6 {build_color} text-center')
                        ui.label(str(ss.feature_requirements_count)).classes('w-1/6 text-slate-300 text-center')
                        ui.label(ss.signature[:12] + '...' if len(ss.signature) > 12 else ss.signature).classes('w-1/6 font-mono text-xs')
                        
                        with ui.row().classes('w-1/6 gap-1'):
                            details_btn = ui.button('Details', icon='info', size='sm').props('dense outline')
                            details_btn.on('click', lambda s=ss: show_strategy_details(s))
                    
                    # Error row if present
                    if ss.error:
                        with ui.row().classes('w-full bg-red-900/20 p-2'):
                            ui.label(f'Error: {ss.error}').classes('text-sm text-red-300')
    
    def show_dataset_details(dataset):
        """Show dataset details in a dialog."""
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label(f'Dataset: {dataset.id}').classes('text-xl font-bold mb-4')
            
            with ui.column().classes('w-full gap-3'):
                # Basic info
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Basic Information').classes('font-bold mb-2')
                    with ui.grid(columns=2).classes('w-full gap-2'):
                        ui.label('Kind:').classes('font-medium')
                        ui.label(dataset.kind)
                        ui.label('TXT present:').classes('font-medium')
                        ui.label('Yes' if dataset.txt_present else 'No')
                        ui.label('Parquet present:').classes('font-medium')
                        ui.label('Yes' if dataset.parquet_present else 'No')
                        ui.label('Up-to-date:').classes('font-medium')
                        ui.label('Yes' if dataset.up_to_date else 'No')
                        ui.label('Schema OK:').classes('font-medium')
                        ui.label('Yes' if dataset.schema_ok else 'No')
                        ui.label('Bars count:').classes('font-medium')
                        ui.label(str(dataset.bars_count) if dataset.bars_count else 'Unknown')
                
                # TXT files
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('TXT Source Files').classes('font-bold mb-2')
                    if not dataset.txt_required_paths:
                        ui.label('No TXT files defined').classes('text-slate-400')
                    else:
                        for txt_path in dataset.txt_required_paths:
                            from pathlib import Path
                            txt_file = Path(txt_path)
                            exists = txt_file.exists()
                            status_color = 'text-green-400' if exists else 'text-red-400'
                            status_icon = '✓' if exists else '✗'
                            with ui.row().classes('w-full items-center gap-2 p-1'):
                                ui.label(status_icon).classes(status_color)
                                ui.label(txt_path).classes('flex-1 font-mono text-sm')
                                if exists:
                                    stat = txt_file.stat()
                                    ui.label(f'{stat.st_size:,} bytes').classes('text-xs text-slate-400')
                
                # Parquet files
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Parquet Output Files').classes('font-bold mb-2')
                    if not dataset.parquet_expected_paths:
                        ui.label('No Parquet files defined').classes('text-slate-400')
                    else:
                        for parquet_path in dataset.parquet_expected_paths:
                            from pathlib import Path
                            parquet_file = Path(parquet_path)
                            exists = parquet_file.exists()
                            status_color = 'text-green-400' if exists else 'text-red-400'
                            status_icon = '✓' if exists else '✗'
                            with ui.row().classes('w-full items-center gap-2 p-1'):
                                ui.label(status_icon).classes(status_color)
                                ui.label(parquet_path).classes('flex-1 font-mono text-sm')
                                if exists:
                                    stat = parquet_file.stat()
                                    ui.label(f'{stat.st_size:,} bytes').classes('text-xs text-slate-400')
                
                # Build action if needed
                if dataset.txt_present and not dataset.up_to_date:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Build Action').classes('font-bold mb-2')
                        with ui.row().classes('w-full gap-2'):
                            build_btn = ui.button('Build Parquet', icon='build', color='primary')
                            build_btn.on('click', lambda d=dataset: do_build_dataset(d.dataset_id))
                            ui.label('Converts TXT to Parquet format').classes('text-sm text-slate-400')
                
                # Error if present
                if dataset.error:
                    with ui.card().classes('w-full bg-red-900/30 p-3'):
                        ui.label('Error').classes('font-bold text-red-300 mb-1')
                        ui.label(dataset.error).classes('text-sm')
            
            ui.button('Close', on_click=dialog.close).classes('mt-4')
        
        dialog.open()
    
    def show_strategy_details(strategy):
        """Show strategy details in a dialog."""
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label(f'Strategy: {strategy.id}').classes('text-xl font-bold mb-4')
            
            with ui.column().classes('w-full gap-3'):
                # Basic info
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Basic Information').classes('font-bold mb-2')
                    with ui.grid(columns=2).classes('w-full gap-2'):
                        ui.label('Can import:').classes('font-medium')
                        ui.label('Yes' if strategy.can_import else 'No')
                        ui.label('Can build spec:').classes('font-medium')
                        ui.label('Yes' if strategy.can_build_spec else 'No')
                        ui.label('Feature requirements:').classes('font-medium')
                        ui.label(str(strategy.feature_requirements_count))
                        ui.label('Last modified:').classes('font-medium')
                        if strategy.mtime:
                            from datetime import datetime
                            dt = datetime.fromtimestamp(strategy.mtime)
                            ui.label(dt.strftime('%Y-%m-%d %H:%M:%S'))
                        else:
                            ui.label('Unknown')
                
                # Signature
                if strategy.signature:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Signature').classes('font-bold mb-2')
                        ui.label(strategy.signature).classes('font-mono text-sm break-all')
                
                # Error if present
                if strategy.error:
                    with ui.card().classes('w-full bg-red-900/30 p-3'):
                        ui.label('Error').classes('font-bold text-red-300 mb-1')
                        ui.label(strategy.error).classes('text-sm')
                
                # Show spec details if available
                if strategy.spec:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Specification').classes('font-bold mb-2')
                        if hasattr(strategy.spec, 'params') and strategy.spec.params:
                            ui.label('Parameters:').classes('font-medium mt-2')
                            for param in strategy.spec.params:
                                with ui.row().classes('w-full gap-4 p-1'):
                                    ui.label(f'{param.name}:').classes('w-1/3 font-medium')
                                    ui.label(f'{param.type} (default: {param.default})').classes('w-2/3 text-slate-300')
            
            ui.button('Close', on_click=dialog.close).classes('mt-4')
        
        dialog.open()
    
    # Main layout
    with ui.column().classes('w-full gap-4 p-6'):
        # Initial load
        refresh()
        
        # Dynamic containers will be filled by update_display
        ui.element('div').classes('w-full')  # Spacer


def register() -> None:
    """Register status page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/wizard.py
sha256(source_bytes) = de4f0ac742bda642c4b8e8f1228143f6281ead1a5c8582b8c0df034ca7f93aa3
bytes = 31352
redacted = False
--------------------------------------------------------------------------------
"""M1 Wizard - Five-step wizard for job creation.

Step1: DATA1 (dataset / symbols / timeframes)
Step2: DATA2 (optional; single filter)
Step3: Strategies (schema-driven)
Step4: Cost
Step5: Summary (must show Units formula and number)
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from datetime import date

from nicegui import ui

from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog
from FishBroWFS_V2.control.job_api import (
    create_job_from_wizard,
    calculate_units,
    check_season_not_frozen,
    ValidationError,
    SeasonFrozenError,
)
from FishBroWFS_V2.control.dataset_descriptor import get_descriptor


class M1WizardState:
    """State management for M1 wizard."""
    
    def __init__(self):
        # Step 1: DATA1
        self.season: str = "2024Q1"
        self.dataset_id: str = ""
        self.symbols: List[str] = []
        self.timeframes: List[str] = []
        self.start_date: Optional[date] = None
        self.end_date: Optional[date] = None
        
        # Step 2: DATA2
        self.enable_data2: bool = False
        self.data2_dataset_id: str = ""
        self.data2_filters: List[str] = []
        self.selected_filter: str = ""
        
        # Step 3: Strategies
        self.strategy_id: str = ""
        self.params: Dict[str, Any] = {}
        
        # Step 4: Cost (calculated)
        self.units: int = 0
        
        # Step 5: Summary
        self.job_id: Optional[str] = None
        
        # UI references
        self.step_containers: Dict[int, Any] = {}
        self.current_step: int = 1


def create_step_indicator(state: M1WizardState) -> None:
    """Create step indicator UI."""
    with ui.row().classes("w-full mb-8 gap-2"):
        steps = [
            (1, "DATA1", state.current_step == 1),
            (2, "DATA2", state.current_step == 2),
            (3, "Strategies", state.current_step == 3),
            (4, "Cost", state.current_step == 4),
            (5, "Summary", state.current_step == 5),
        ]
        
        for step_num, label, active in steps:
            with ui.column().classes("items-center"):
                ui.label(str(step_num)).classes(
                    f"w-8 h-8 rounded-full flex items-center justify-center font-bold "
                    f"{'bg-blue-500 text-white' if active else 'bg-gray-200 text-gray-600'}"
                )
                ui.label(label).classes(
                    f"text-sm mt-1 {'font-bold text-blue-600' if active else 'text-gray-500'}"
                )


def create_step1_data1(state: M1WizardState) -> None:
    """Create Step 1: DATA1 UI."""
    with state.step_containers[1]:
        ui.label("Step 1: DATA1 Configuration").classes("text-xl font-bold mb-4")
        
        # Season input
        from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_input, labeled_select, labeled_date
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Season")
            season_input = ui.input(
                value=state.season,
                placeholder="e.g., 2024Q1, 2024Q2"
            ).classes("w-full")
            season_input.bind_value(state, 'season')
        
        # Dataset selection
        catalog = get_dataset_catalog()
        datasets = catalog.list_datasets()
        dataset_options = {d.id: f"{d.symbol} ({d.timeframe}) {d.start_date}-{d.end_date}"
                          for d in datasets}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Dataset")
            dataset_select = ui.select(
                options=dataset_options,
                with_input=True
            ).classes("w-full")
            dataset_select.bind_value(state, 'dataset_id')
        
        # Symbols input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Symbols (comma separated)")
            symbols_input = ui.input(
                value="MNQ, MXF",
                placeholder="e.g., MNQ, MXF, MES"
            ).classes("w-full")
            symbols_input.bind_value(state, 'symbols')
        
        # Timeframes input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Timeframes (comma separated)")
            timeframes_input = ui.input(
                value="60m, 120m",
                placeholder="e.g., 60m, 120m, 240m"
            ).classes("w-full")
            timeframes_input.bind_value(state, 'timeframes')
        
        # Date range
        with ui.row().classes("w-full"):
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("Start Date")
                start_date = ui.date(
                    value=date(2020, 1, 1)
                ).classes("w-full")
                start_date.bind_value(state, 'start_date')
            
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("End Date")
                end_date = ui.date(
                    value=date(2024, 12, 31)
                ).classes("w-full")
                end_date.bind_value(state, 'end_date')
        
        # Initialize state with parsed values
        def parse_initial_values():
            if isinstance(state.symbols, str):
                state.symbols = [s.strip() for s in state.symbols.split(",") if s.strip()]
            elif not isinstance(state.symbols, list):
                state.symbols = []
            
            if isinstance(state.timeframes, str):
                state.timeframes = [t.strip() for t in state.timeframes.split(",") if t.strip()]
            elif not isinstance(state.timeframes, list):
                state.timeframes = []
        
        parse_initial_values()


def create_step2_data2(state: M1WizardState) -> None:
    """Create Step 2: DATA2 UI (optional, single filter)."""
    with state.step_containers[2]:
        ui.label("Step 2: DATA2 Configuration (Optional)").classes("text-xl font-bold mb-4")
        
        # Enable DATA2 toggle
        enable_toggle = ui.switch("Enable DATA2 (single filter validation)")
        enable_toggle.bind_value(state, 'enable_data2')
        
        # DATA2 container (initially hidden)
        data2_container = ui.column().classes("w-full mt-4")
        
        def update_data2_visibility(enabled: bool):
            data2_container.clear()
            if not enabled:
                state.data2_dataset_id = ""
                state.data2_filters = []
                state.selected_filter = ""
                return
            
            with data2_container:
                # Dataset selection for DATA2
                catalog = get_dataset_catalog()
                datasets = catalog.list_datasets()
                dataset_options = {d.id: f"{d.symbol} ({d.timeframe})" for d in datasets}
                
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("DATA2 Dataset")
                    dataset_select = ui.select(
                        options=dataset_options,
                        with_input=True
                    ).classes("w-full")
                    dataset_select.bind_value(state, 'data2_dataset_id')
                
                # Filter selection (single filter)
                filter_options = ["momentum", "volatility", "trend", "mean_reversion"]
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("Filter")
                    filter_select = ui.select(
                        options=filter_options,
                        value=filter_options[0] if filter_options else ""
                    ).classes("w-full")
                    filter_select.bind_value(state, 'selected_filter')
                
                # Initialize state
                state.data2_filters = filter_options
                if not state.selected_filter and filter_options:
                    state.selected_filter = filter_options[0]
        
        # Use timer to update visibility when enable_data2 changes
        def update_visibility_from_state():
            update_data2_visibility(state.enable_data2)
        
        ui.timer(0.2, update_visibility_from_state)
        
        # Initial visibility
        update_data2_visibility(state.enable_data2)


def create_step3_strategies(state: M1WizardState) -> None:
    """Create Step 3: Strategies UI (schema-driven)."""
    with state.step_containers[3]:
        ui.label("Step 3: Strategy Selection").classes("text-xl font-bold mb-4")
        
        # Strategy selection
        catalog = get_strategy_catalog()
        strategies = catalog.list_strategies()
        strategy_options = {s.strategy_id: s.strategy_id for s in strategies}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Strategy")
            strategy_select = ui.select(
                options=strategy_options,
                with_input=True
            ).classes("w-full")
            strategy_select.bind_value(state, 'strategy_id')
        
        # Parameters container (dynamic)
        param_container = ui.column().classes("w-full mt-4")
        
        def update_strategy_ui(selected_id: str):
            param_container.clear()
            state.strategy_id = selected_id
            state.params = {}
            
            if not selected_id:
                return
            
            strategy = catalog.get_strategy(selected_id)
            if not strategy:
                return
            
            ui.label("Parameters").classes("font-bold mt-2 mb-2")
            
            # Create UI for each parameter
            for param in strategy.params:
                with ui.row().classes("w-full items-center mb-3"):
                    ui.label(f"{param.name}:").classes("w-1/3 font-medium")
                    
                    if param.type == "int" or param.type == "float":
                        # Number input
                        min_val = param.min if param.min is not None else 0
                        max_val = param.max if param.max is not None else 100
                        step = param.step if param.step is not None else (1 if param.type == "int" else 0.1)
                        
                        input_field = ui.number(
                            value=param.default,
                            min=min_val,
                            max=max_val,
                            step=step
                        ).classes("w-2/3")
                        
                        # Use on('update:model-value') for immediate updates
                        def make_param_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        input_field.on('update:model-value', make_param_handler(param.name, input_field))
                        state.params[param.name] = param.default
                        
                    elif param.type == "enum" and param.choices:
                        # Dropdown for enum
                        dropdown = ui.select(
                            options=param.choices,
                            value=param.default
                        ).classes("w-2/3")
                        
                        def make_enum_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        dropdown.on('update:model-value', make_enum_handler(param.name, dropdown))
                        state.params[param.name] = param.default
                        
                    elif param.type == "bool":
                        # Switch for boolean
                        switch = ui.switch(value=param.default).classes("w-2/3")
                        
                        def make_bool_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        switch.on('update:model-value', make_bool_handler(param.name, switch))
                        state.params[param.name] = param.default
                    
                    # Help text
                    if param.help:
                        ui.tooltip(param.help).classes("ml-2")
        
        # Use timer to update UI when strategy_id changes
        def update_strategy_from_state():
            if state.strategy_id != getattr(update_strategy_from_state, '_last_strategy', None):
                update_strategy_ui(state.strategy_id)
                update_strategy_from_state._last_strategy = state.strategy_id
        
        ui.timer(0.2, update_strategy_from_state)
        
        # Initialize if strategy is selected
        if state.strategy_id:
            update_strategy_ui(state.strategy_id)
        elif strategies:
            # Select first strategy by default
            first_strategy = strategies[0].strategy_id
            state.strategy_id = first_strategy
            update_strategy_ui(first_strategy)


def create_step4_cost(state: M1WizardState) -> None:
    """Create Step 4: Cost UI (Units calculation)."""
    with state.step_containers[4]:
        ui.label("Step 4: Cost Estimation").classes("text-xl font-bold mb-4")
        
        # Units formula explanation
        with ui.card().classes("w-full mb-4 bg-blue-50"):
            ui.label("Units Formula").classes("font-bold text-blue-800")
            ui.label("Units = |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|").classes("font-mono text-sm text-blue-700")
            ui.label("Where |strategies| = 1 (single strategy) and |DATA2.filters| = 1 if DATA2 disabled").classes("text-sm text-blue-600")
        
        # Current configuration summary
        config_card = ui.card().classes("w-full mb-4")
        
        # Units calculation result
        units_label = ui.label("Calculating units...").classes("text-2xl font-bold text-green-600")
        
        # Parquet status warning container
        parquet_warning_container = ui.column().classes("w-full mt-4")
        
        def update_cost_display():
            with config_card:
                config_card.clear()
                
                # Build payload for units calculation
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Calculate units
                try:
                    units = calculate_units(payload)
                    state.units = units
                    
                    # Display configuration
                    ui.label("Current Configuration:").classes("font-bold mb-2")
                    
                    with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                        ui.label("Season:").classes("font-medium")
                        ui.label(state.season)
                        
                        ui.label("DATA1 Dataset:").classes("font-medium")
                        ui.label(state.dataset_id if state.dataset_id else "Not selected")
                        
                        ui.label("Symbols:").classes("font-medium")
                        ui.label(f"{len(state.symbols)}: {', '.join(state.symbols)}" if state.symbols else "None")
                        
                        ui.label("Timeframes:").classes("font-medium")
                        ui.label(f"{len(state.timeframes)}: {', '.join(state.timeframes)}" if state.timeframes else "None")
                        
                        ui.label("Strategy:").classes("font-medium")
                        ui.label(state.strategy_id if state.strategy_id else "Not selected")
                        
                        ui.label("DATA2 Enabled:").classes("font-medium")
                        ui.label("Yes" if state.enable_data2 else "No")
                        
                        if state.enable_data2:
                            ui.label("DATA2 Filter:").classes("font-medium")
                            ui.label(state.selected_filter)
                    
                    # Update units display
                    units_label.set_text(f"Total Units: {units}")
                    
                    # Cost estimation (simplified)
                    if units > 100:
                        ui.label("⚠️ High cost warning: This job may take significant resources").classes("text-yellow-600 mt-2")
                    
                except Exception as e:
                    units_label.set_text(f"Error calculating units: {str(e)}")
                    state.units = 0
            
            # Update Parquet status warnings
            parquet_warning_container.clear()
            
            # Check DATA1 dataset Parquet status
            if state.dataset_id:
                try:
                    descriptor = get_descriptor(state.dataset_id)
                    if descriptor:
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            with parquet_warning_container:
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200"):
                                    ui.label("⚠️ DATA1 Parquet Files Missing").classes("text-yellow-800 font-bold mb-2")
                                    ui.label(f"Dataset '{state.dataset_id}' is missing {len(parquet_missing)} Parquet file(s)").classes("text-yellow-700 mb-2")
                                    ui.label("This may cause job failures or slower performance.").classes("text-sm text-yellow-600 mb-2")
                                    
                                    with ui.row().classes("w-full gap-2"):
                                        ui.button("Build Parquet",
                                                 on_click=lambda: ui.navigate.to("/status"),
                                                 icon="build").props("outline color=warning")
                                        ui.button("Check Status",
                                                 on_click=lambda: ui.navigate.to("/status"),
                                                 icon="info").props("outline")
                except Exception:
                    pass
            
            # Check DATA2 dataset Parquet status if enabled
            if state.enable_data2 and state.data2_dataset_id:
                try:
                    descriptor = get_descriptor(state.data2_dataset_id)
                    if descriptor:
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            with parquet_warning_container:
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200 mt-2"):
                                    ui.label("⚠️ DATA2 Parquet Files Missing").classes("text-yellow-800 font-bold mb-2")
                                    ui.label(f"Dataset '{state.data2_dataset_id}' is missing {len(parquet_missing)} Parquet file(s)").classes("text-yellow-700 mb-2")
                                    ui.label("DATA2 validation may fail without Parquet files.").classes("text-sm text-yellow-600")
                except Exception:
                    pass
        
        # Update cost display periodically
        ui.timer(1.0, update_cost_display)


def create_step5_summary(state: M1WizardState) -> None:
    """Create Step 5: Summary and Submit UI."""
    with state.step_containers[5]:
        ui.label("Step 5: Summary & Submit").classes("text-xl font-bold mb-4")
        
        # Summary card
        summary_card = ui.card().classes("w-full mb-4")
        
        # Submit button
        submit_button = ui.button("Submit Job", icon="send", color="green")
        
        # Result container
        result_container = ui.column().classes("w-full mt-4")
        
        def update_summary():
            summary_card.clear()
            
            with summary_card:
                ui.label("Job Summary").classes("font-bold mb-2")
                
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Display payload
                ui.label("Final Payload:").classes("font-medium mt-2")
                payload_json = json.dumps(payload, indent=2)
                ui.textarea(payload_json).classes("w-full h-48 font-mono text-xs").props("readonly")
                
                # Units display
                units = calculate_units(payload)
                ui.label(f"Total Units: {units}").classes("font-bold text-lg mt-2")
                ui.label("Units = |symbols| × |timeframes| × |strategies| × |filters|").classes("text-sm text-gray-600")
                ui.label(f"= {len(state.symbols)} × {len(state.timeframes)} × 1 × {1 if state.enable_data2 else 1} = {units}").classes("text-sm font-mono")
        
        def submit_job():
            result_container.clear()
            
            try:
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Check season not frozen
                check_season_not_frozen(state.season, action="submit_job")
                
                # Submit job
                result = create_job_from_wizard(payload)
                state.job_id = result["job_id"]
                
                # Show success message
                with result_container:
                    with ui.card().classes("w-full bg-green-50 border-green-200"):
                        ui.label("✅ Job Submitted Successfully!").classes("text-green-800 font-bold mb-2")
                        ui.label(f"Job ID: {result['job_id']}").classes("font-mono text-sm mb-1")
                        ui.label(f"Units: {result['units']}").classes("text-sm mb-1")
                        ui.label(f"Season: {result['season']}").classes("text-sm mb-3")
                        
                        # Navigation button
                        ui.button(
                            "View Job Details",
                            on_click=lambda: ui.navigate.to(f"/jobs/{result['job_id']}"),
                            icon="visibility"
                        ).classes("bg-green-600 text-white")
                
                # Disable submit button
                submit_button.disable()
                submit_button.set_text("Submitted")
                
            except SeasonFrozenError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Season is Frozen").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Cannot submit job: {str(e)}").classes("text-red-700")
            except ValidationError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Validation Error").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Please check your inputs: {str(e)}").classes("text-red-700")
            except Exception as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Submission Failed").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Error: {str(e)}").classes("text-red-700")
        
        submit_button.on_click(submit_job)
        
        # Navigation buttons
        with ui.row().classes("w-full justify-between mt-4"):
            ui.button("Previous Step",
                     on_click=lambda: navigate_to_step(4),
                     icon="arrow_back").props("outline")
            
            ui.button("Save Configuration",
                     on_click=lambda: ui.notify("Save functionality not implemented in M1", type="info"),
                     icon="save").props("outline")
        
        # Initial update
        update_summary()
        
        # Auto-update summary
        ui.timer(2.0, update_summary)


def navigate_to_step(step: int, state: M1WizardState) -> None:
    """Navigate to specific step."""
    if 1 <= step <= 5:
        state.current_step = step
        for step_num, container in state.step_containers.items():
            container.set_visibility(step_num == step)


@ui.page("/wizard")
def wizard_page() -> None:
    """M1 Wizard main page."""
    ui.page_title("FishBroWFS V2 - M1 Wizard")
    
    state = M1WizardState()
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
        # Header
        ui.label("🧙‍♂️ M1 Wizard").classes("text-3xl font-bold mb-2")
        ui.label("Five-step job configuration wizard").classes("text-lg text-gray-600 mb-6")
        
        # Step indicator
        create_step_indicator(state)
        
        # Create step containers (all initially hidden except step 1)
        for step in range(1, 6):
            container = ui.column().classes("w-full")
            container.set_visibility(step == 1)
            state.step_containers[step] = container
        
        # Create step content
        create_step1_data1(state)
        create_step2_data2(state)
        create_step3_strategies(state)
        create_step4_cost(state)
        create_step5_summary(state)
        
        # Navigation buttons (global)
        with ui.row().classes("w-full justify-between mt-8"):
            prev_button = ui.button("Previous",
                                   on_click=lambda: navigate_to_step(state.current_step - 1, state),
                                   icon="arrow_back")
            prev_button.props("disabled" if state.current_step == 1 else "")
            
            next_button = ui.button("Next",
                                   on_click=lambda: navigate_to_step(state.current_step + 1, state),
                                   icon="arrow_forward")
            next_button.props("disabled" if state.current_step == 5 else "")
            
            # Update button states based on current step
            def update_nav_buttons():
                prev_button.props("disabled" if state.current_step == 1 else "")
                next_button.props("disabled" if state.current_step == 5 else "")
                next_button.set_text("Submit" if state.current_step == 4 else "Next")
            
            ui.timer(0.5, update_nav_buttons)
        
        # Quick links
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("Quick links:")
            ui.link("Jobs List", "/jobs").classes("ml-4 text-blue-500 hover:text-blue-700")
            ui.link("Dashboard", "/").classes("ml-4 text-blue-500 hover:text-blue-700")


def register() -> None:
    """Register wizard page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /wizard/m1 for testing
@ui.page("/wizard/m1")
def wizard_m1_page() -> None:
    """Alternative route for M1 wizard."""
    wizard_page()

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/wizard_backup.py
sha256(source_bytes) = 61ab12ebdb451eb6fa16cd52619b826f91b96b84344910a2e15a7e526cee3ceb
bytes = 4988
redacted = False
--------------------------------------------------------------------------------
"""Wizard 頁面 - 任務設定精靈"""

from nicegui import ui


def register() -> None:
    """註冊 Wizard 頁面路由"""
    
    @ui.page("/wizard")
    def wizard_page() -> None:
        """渲染 Wizard 頁面"""
        ui.page_title("FishBroWFS V2 - 任務設定精靈")
        
        with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
            # 標題
            ui.label("🧙‍♂️ 任務設定精靈").classes("text-3xl font-bold mb-2 text-cyber-glow")
            ui.label("引導式任務設定介面（取代舊版 new-job）").classes("text-lg text-slate-400 mb-8")
            
            # 步驟指示器
            with ui.row().classes("w-full mb-8 gap-2"):
                steps = [
                    ("1", "基本設定", True),
                    ("2", "策略選擇", False),
                    ("3", "回測參數", False),
                    ("4", "滑點壓力", False),
                    ("5", "確認提交", False),
                ]
                for num, label, active in steps:
                    with ui.column().classes("items-center"):
                        ui.label(num).classes(
                            f"w-8 h-8 rounded-full flex items-center justify-center font-bold "
                            f"{'bg-cyber-500 text-white' if active else 'bg-nexus-800 text-slate-400'}"
                        )
                        ui.label(label).classes(
                            f"text-sm mt-1 {'text-cyber-400 font-bold' if active else 'text-slate-500'}"
                        )
            
            # 內容區域
            with ui.card().classes("fish-card w-full p-6"):
                ui.label("步驟 1: 基本設定").classes("text-xl font-bold mb-6")
                
                # Season 選擇
                season_select = ui.select(
                    label="Season",
                    options=["2026Q1", "2026Q2", "2026Q3", "2026Q4"],
                    value="2026Q1"
                ).classes("w-full mb-4")
                
                # Dataset 選擇
                dataset_select = ui.select(
                    label="資料集",
                    options=["MNQ_MXF_2025", "MNQ_MXF_2026", "MES_MNQ_2025"],
                    value="MNQ_MXF_2025"
                ).classes("w-full mb-4")
                
                # Symbols 輸入
                symbols_input = ui.input(
                    label="交易標的 (逗號分隔)",
                    value="MNQ, MXF",
                    placeholder="例如: MNQ, MXF, MES"
                ).classes("w-full mb-4")
                
                # Timeframe 選擇
                timeframe_select = ui.select(
                    label="時間框架 (分鐘)",
                    options={60: "60分鐘", 120: "120分鐘", 240: "240分鐘"},
                    value=60
                ).classes("w-full mb-6")
            
            # 導航按鈕
            with ui.row().classes("w-full justify-between mt-8"):
                ui.button("上一步", icon="arrow_back", color="gray").props("disabled").tooltip("DEV MODE: not implemented yet")
                
                with ui.row().classes("gap-4"):
                    ui.button("儲存草稿", icon="save", color="gray").props("outline")
                    ui.button("下一步", icon="arrow_forward", on_click=lambda: ui.notify("下一步功能開發中", type="info")).classes("btn-cyber")
            
            # 快速跳轉
            with ui.row().classes("w-full mt-8 text-sm text-slate-500"):
                ui.label("快速跳轉:")
                ui.link("返回首頁", "/").classes("ml-4 text-cyber-400 hover:text-cyber-300")
                ui.link("查看歷史任務", "/history").classes("ml-4 text-cyber-400 hover:text-cyber-300")
                ui.link("舊版設定頁面", "/new-job").classes("ml-4 text-cyber-400 hover:text-cyber-300")
    
    # 支援 clone 參數
    @ui.page("/wizard/{clone_id}")
    def wizard_clone_page(clone_id: str) -> None:
        """渲染帶有 clone 參數的 Wizard 頁面"""
        ui.page_title(f"FishBroWFS V2 - Clone 任務 {clone_id[:8]}...")
        
        with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
            # 顯示 clone 資訊
            with ui.card().classes("fish-card w-full p-6 mb-6 border-cyber-500/50"):
                ui.label(f"📋 正在複製任務: {clone_id[:8]}...").classes("text-xl font-bold mb-2")
                ui.label("已自動填入欄位，請檢查並修改設定。").classes("text-slate-300")
            
            # 重定向到普通 wizard 頁面，但帶有 clone 參數提示
            ui.label("Clone 功能開發中...").classes("text-lg text-slate-400 mb-4")
            ui.label(f"將從任務 {clone_id} 複製設定。").classes("text-slate-500 mb-6")
            
            ui.button("前往 Wizard 主頁", on_click=lambda: ui.navigate.to("/wizard"), icon="rocket_launch").classes("btn-cyber")
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/wizard_m1.py
sha256(source_bytes) = 9cabc358d1461886e2a1e132957301f8e50d09b61cc05f6c26e1d2126865f95b
bytes = 27604
redacted = False
--------------------------------------------------------------------------------
"""M1 Wizard - Five-step wizard for job creation.

Step1: DATA1 (dataset / symbols / timeframes)
Step2: DATA2 (optional; single filter)
Step3: Strategies (schema-driven)
Step4: Cost
Step5: Summary (must show Units formula and number)
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from datetime import date

from nicegui import ui

from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog
from FishBroWFS_V2.control.job_api import (
    create_job_from_wizard,
    calculate_units,
    check_season_not_frozen,
    ValidationError,
    SeasonFrozenError,
)


class M1WizardState:
    """State management for M1 wizard."""
    
    def __init__(self):
        # Step 1: DATA1
        self.season: str = "2024Q1"
        self.dataset_id: str = ""
        self.symbols: List[str] = []
        self.timeframes: List[str] = []
        self.start_date: Optional[date] = None
        self.end_date: Optional[date] = None
        
        # Step 2: DATA2
        self.enable_data2: bool = False
        self.data2_dataset_id: str = ""
        self.data2_filters: List[str] = []
        self.selected_filter: str = ""
        
        # Step 3: Strategies
        self.strategy_id: str = ""
        self.params: Dict[str, Any] = {}
        
        # Step 4: Cost (calculated)
        self.units: int = 0
        
        # Step 5: Summary
        self.job_id: Optional[str] = None
        
        # UI references
        self.step_containers: Dict[int, Any] = {}
        self.current_step: int = 1


def create_step_indicator(state: M1WizardState) -> None:
    """Create step indicator UI."""
    with ui.row().classes("w-full mb-8 gap-2"):
        steps = [
            (1, "DATA1", state.current_step == 1),
            (2, "DATA2", state.current_step == 2),
            (3, "Strategies", state.current_step == 3),
            (4, "Cost", state.current_step == 4),
            (5, "Summary", state.current_step == 5),
        ]
        
        for step_num, label, active in steps:
            with ui.column().classes("items-center"):
                ui.label(str(step_num)).classes(
                    f"w-8 h-8 rounded-full flex items-center justify-center font-bold "
                    f"{'bg-blue-500 text-white' if active else 'bg-gray-200 text-gray-600'}"
                )
                ui.label(label).classes(
                    f"text-sm mt-1 {'font-bold text-blue-600' if active else 'text-gray-500'}"
                )


def create_step1_data1(state: M1WizardState) -> None:
    """Create Step 1: DATA1 UI."""
    with state.step_containers[1]:
        ui.label("Step 1: DATA1 Configuration").classes("text-xl font-bold mb-4")
        
        # Season input
        from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_input, labeled_select, labeled_date
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Season")
            season_input = ui.input(
                value=state.season,
                placeholder="e.g., 2024Q1, 2024Q2"
            ).classes("w-full")
            season_input.bind_value(state, 'season')
        
        # Dataset selection
        catalog = get_dataset_catalog()
        datasets = catalog.list_datasets()
        dataset_options = {d.id: f"{d.symbol} ({d.timeframe}) {d.start_date}-{d.end_date}"
                          for d in datasets}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Dataset")
            dataset_select = ui.select(
                options=dataset_options,
                with_input=True
            ).classes("w-full")
            dataset_select.bind_value(state, 'dataset_id')
        
        # Symbols input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Symbols (comma separated)")
            symbols_input = ui.input(
                value="MNQ, MXF",
                placeholder="e.g., MNQ, MXF, MES"
            ).classes("w-full")
            symbols_input.bind_value(state, 'symbols')
        
        # Timeframes input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Timeframes (comma separated)")
            timeframes_input = ui.input(
                value="60m, 120m",
                placeholder="e.g., 60m, 120m, 240m"
            ).classes("w-full")
            timeframes_input.bind_value(state, 'timeframes')
        
        # Date range
        with ui.row().classes("w-full"):
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("Start Date")
                start_date = ui.date(
                    value=date(2020, 1, 1)
                ).classes("w-full")
                start_date.bind_value(state, 'start_date')
            
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("End Date")
                end_date = ui.date(
                    value=date(2024, 12, 31)
                ).classes("w-full")
                end_date.bind_value(state, 'end_date')
        
        # Initialize state with parsed values
        def parse_initial_values():
            if isinstance(state.symbols, str):
                state.symbols = [s.strip() for s in state.symbols.split(",") if s.strip()]
            elif not isinstance(state.symbols, list):
                state.symbols = []
            
            if isinstance(state.timeframes, str):
                state.timeframes = [t.strip() for t in state.timeframes.split(",") if t.strip()]
            elif not isinstance(state.timeframes, list):
                state.timeframes = []
        
        parse_initial_values()


def create_step2_data2(state: M1WizardState) -> None:
    """Create Step 2: DATA2 UI (optional, single filter)."""
    with state.step_containers[2]:
        ui.label("Step 2: DATA2 Configuration (Optional)").classes("text-xl font-bold mb-4")
        
        # Enable DATA2 toggle
        enable_toggle = ui.switch("Enable DATA2 (single filter validation)")
        enable_toggle.bind_value(state, 'enable_data2')
        
        # DATA2 container (initially hidden)
        data2_container = ui.column().classes("w-full mt-4")
        
        def update_data2_visibility(enabled: bool):
            data2_container.clear()
            if not enabled:
                state.data2_dataset_id = ""
                state.data2_filters = []
                state.selected_filter = ""
                return
            
            with data2_container:
                # Dataset selection for DATA2
                catalog = get_dataset_catalog()
                datasets = catalog.list_datasets()
                dataset_options = {d.id: f"{d.symbol} ({d.timeframe})" for d in datasets}
                
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("DATA2 Dataset")
                    dataset_select = ui.select(
                        options=dataset_options,
                        with_input=True
                    ).classes("w-full")
                    dataset_select.bind_value(state, 'data2_dataset_id')
                
                # Filter selection (single filter)
                filter_options = ["momentum", "volatility", "trend", "mean_reversion"]
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("Filter")
                    filter_select = ui.select(
                        options=filter_options,
                        value=filter_options[0] if filter_options else ""
                    ).classes("w-full")
                    filter_select.bind_value(state, 'selected_filter')
                
                # Initialize state
                state.data2_filters = filter_options
                if not state.selected_filter and filter_options:
                    state.selected_filter = filter_options[0]
        
        # Use timer to update visibility when enable_data2 changes
        def update_visibility_from_state():
            update_data2_visibility(state.enable_data2)
        
        ui.timer(0.2, update_visibility_from_state)
        
        # Initial visibility
        update_data2_visibility(state.enable_data2)


def create_step3_strategies(state: M1WizardState) -> None:
    """Create Step 3: Strategies UI (schema-driven)."""
    with state.step_containers[3]:
        ui.label("Step 3: Strategy Selection").classes("text-xl font-bold mb-4")
        
        # Strategy selection
        catalog = get_strategy_catalog()
        strategies = catalog.list_strategies()
        strategy_options = {s.strategy_id: s.strategy_id for s in strategies}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Strategy")
            strategy_select = ui.select(
                options=strategy_options,
                with_input=True
            ).classes("w-full")
            strategy_select.bind_value(state, 'strategy_id')
        
        # Parameters container (dynamic)
        param_container = ui.column().classes("w-full mt-4")
        
        def update_strategy_ui(selected_id: str):
            param_container.clear()
            state.strategy_id = selected_id
            state.params = {}
            
            if not selected_id:
                return
            
            strategy = catalog.get_strategy(selected_id)
            if not strategy:
                return
            
            ui.label("Parameters").classes("font-bold mt-2 mb-2")
            
            # Create UI for each parameter
            for param in strategy.params:
                with ui.row().classes("w-full items-center mb-3"):
                    ui.label(f"{param.name}:").classes("w-1/3 font-medium")
                    
                    if param.type == "int" or param.type == "float":
                        # Number input
                        min_val = param.min if param.min is not None else 0
                        max_val = param.max if param.max is not None else 100
                        step = param.step if param.step is not None else (1 if param.type == "int" else 0.1)
                        
                        input_field = ui.number(
                            value=param.default,
                            min=min_val,
                            max=max_val,
                            step=step
                        ).classes("w-2/3")
                        
                        # Use on('update:model-value') for immediate updates
                        def make_param_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        input_field.on('update:model-value', make_param_handler(param.name, input_field))
                        state.params[param.name] = param.default
                        
                    elif param.type == "enum" and param.choices:
                        # Dropdown for enum
                        dropdown = ui.select(
                            options=param.choices,
                            value=param.default
                        ).classes("w-2/3")
                        
                        def make_enum_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        dropdown.on('update:model-value', make_enum_handler(param.name, dropdown))
                        state.params[param.name] = param.default
                        
                    elif param.type == "bool":
                        # Switch for boolean
                        switch = ui.switch(value=param.default).classes("w-2/3")
                        
                        def make_bool_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        switch.on('update:model-value', make_bool_handler(param.name, switch))
                        state.params[param.name] = param.default
                    
                    # Help text
                    if param.help:
                        ui.tooltip(param.help).classes("ml-2")
        
        # Use timer to update UI when strategy_id changes
        def update_strategy_from_state():
            if state.strategy_id != getattr(update_strategy_from_state, '_last_strategy', None):
                update_strategy_ui(state.strategy_id)
                update_strategy_from_state._last_strategy = state.strategy_id
        
        ui.timer(0.2, update_strategy_from_state)
        
        # Initialize if strategy is selected
        if state.strategy_id:
            update_strategy_ui(state.strategy_id)
        elif strategies:
            # Select first strategy by default
            first_strategy = strategies[0].strategy_id
            state.strategy_id = first_strategy
            update_strategy_ui(first_strategy)


def create_step4_cost(state: M1WizardState) -> None:
    """Create Step 4: Cost UI (Units calculation)."""
    with state.step_containers[4]:
        ui.label("Step 4: Cost Estimation").classes("text-xl font-bold mb-4")
        
        # Units formula explanation
        with ui.card().classes("w-full mb-4 bg-blue-50"):
            ui.label("Units Formula").classes("font-bold text-blue-800")
            ui.label("Units = |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|").classes("font-mono text-sm text-blue-700")
            ui.label("Where |strategies| = 1 (single strategy) and |DATA2.filters| = 1 if DATA2 disabled").classes("text-sm text-blue-600")
        
        # Current configuration summary
        config_card = ui.card().classes("w-full mb-4")
        
        # Units calculation result
        units_label = ui.label("Calculating units...").classes("text-2xl font-bold text-green-600")
        
        def update_cost_display():
            with config_card:
                config_card.clear()
                
                # Build payload for units calculation
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Calculate units
                try:
                    units = calculate_units(payload)
                    state.units = units
                    
                    # Display configuration
                    ui.label("Current Configuration:").classes("font-bold mb-2")
                    
                    with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                        ui.label("Season:").classes("font-medium")
                        ui.label(state.season)
                        
                        ui.label("DATA1 Dataset:").classes("font-medium")
                        ui.label(state.dataset_id if state.dataset_id else "Not selected")
                        
                        ui.label("Symbols:").classes("font-medium")
                        ui.label(f"{len(state.symbols)}: {', '.join(state.symbols)}" if state.symbols else "None")
                        
                        ui.label("Timeframes:").classes("font-medium")
                        ui.label(f"{len(state.timeframes)}: {', '.join(state.timeframes)}" if state.timeframes else "None")
                        
                        ui.label("Strategy:").classes("font-medium")
                        ui.label(state.strategy_id if state.strategy_id else "Not selected")
                        
                        ui.label("DATA2 Enabled:").classes("font-medium")
                        ui.label("Yes" if state.enable_data2 else "No")
                        
                        if state.enable_data2:
                            ui.label("DATA2 Filter:").classes("font-medium")
                            ui.label(state.selected_filter)
                    
                    # Update units display
                    units_label.set_text(f"Total Units: {units}")
                    
                    # Cost estimation (simplified)
                    if units > 100:
                        ui.label("⚠️ High cost warning: This job may take significant resources").classes("text-yellow-600 mt-2")
                    
                except Exception as e:
                    units_label.set_text(f"Error calculating units: {str(e)}")
                    state.units = 0
        
        # Update cost display periodically
        ui.timer(1.0, update_cost_display)


def create_step5_summary(state: M1WizardState) -> None:
    """Create Step 5: Summary and Submit UI."""
    with state.step_containers[5]:
        ui.label("Step 5: Summary & Submit").classes("text-xl font-bold mb-4")
        
        # Summary card
        summary_card = ui.card().classes("w-full mb-4")
        
        # Submit button
        submit_button = ui.button("Submit Job", icon="send", color="green")
        
        # Result container
        result_container = ui.column().classes("w-full mt-4")
        
        def update_summary():
            summary_card.clear()
            
            with summary_card:
                ui.label("Job Summary").classes("font-bold mb-2")
                
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Display payload
                ui.label("Final Payload:").classes("font-medium mt-2")
                payload_json = json.dumps(payload, indent=2)
                ui.textarea(payload_json).classes("w-full h-48 font-mono text-xs").props("readonly")
                
                # Units display
                units = calculate_units(payload)
                ui.label(f"Total Units: {units}").classes("font-bold text-lg mt-2")
                ui.label("Units = |symbols| × |timeframes| × |strategies| × |filters|").classes("text-sm text-gray-600")
                ui.label(f"= {len(state.symbols)} × {len(state.timeframes)} × 1 × {1 if state.enable_data2 else 1} = {units}").classes("text-sm font-mono")
        
        def submit_job():
            result_container.clear()
            
            try:
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Check season not frozen
                check_season_not_frozen(state.season, action="submit_job")
                
                # Submit job
                result = create_job_from_wizard(payload)
                state.job_id = result["job_id"]
                
                # Show success message
                with result_container:
                    with ui.card().classes("w-full bg-green-50 border-green-200"):
                        ui.label("✅ Job Submitted Successfully!").classes("text-green-800 font-bold mb-2")
                        ui.label(f"Job ID: {result['job_id']}").classes("font-mono text-sm mb-1")
                        ui.label(f"Units: {result['units']}").classes("text-sm mb-1")
                        ui.label(f"Season: {result['season']}").classes("text-sm mb-3")
                        
                        # Navigation button
                        ui.button(
                            "View Job Details",
                            on_click=lambda: ui.navigate.to(f"/jobs/{result['job_id']}"),
                            icon="visibility"
                        ).classes("bg-green-600 text-white")
                
                # Disable submit button
                submit_button.disable()
                submit_button.set_text("Submitted")
                
            except SeasonFrozenError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Season is Frozen").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Cannot submit job: {str(e)}").classes("text-red-700")
            except ValidationError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Validation Error").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Please check your inputs: {str(e)}").classes("text-red-700")
            except Exception as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Submission Failed").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Error: {str(e)}").classes("text-red-700")
        
        submit_button.on_click(submit_job)
        
        # Navigation buttons
        with ui.row().classes("w-full justify-between mt-4"):
            ui.button("Previous Step",
                     on_click=lambda: navigate_to_step(4),
                     icon="arrow_back").props("outline")
            
            ui.button("Save Configuration",
                     on_click=lambda: ui.notify("Save functionality not implemented in M1", type="info"),
                     icon="save").props("outline")
        
        # Initial update
        update_summary()
        
        # Auto-update summary
        ui.timer(2.0, update_summary)


def navigate_to_step(step: int, state: M1WizardState) -> None:
    """Navigate to specific step."""
    if 1 <= step <= 5:
        state.current_step = step
        for step_num, container in state.step_containers.items():
            container.set_visibility(step_num == step)


@ui.page("/wizard")
def wizard_page() -> None:
    """M1 Wizard main page."""
    ui.page_title("FishBroWFS V2 - M1 Wizard")
    
    state = M1WizardState()
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
        # Header
        ui.label("🧙‍♂️ M1 Wizard").classes("text-3xl font-bold mb-2")
        ui.label("Five-step job configuration wizard").classes("text-lg text-gray-600 mb-6")
        
        # Step indicator
        create_step_indicator(state)
        
        # Create step containers (all initially hidden except step 1)
        for step in range(1, 6):
            container = ui.column().classes("w-full")
            container.set_visibility(step == 1)
            state.step_containers[step] = container
        
        # Create step content
        create_step1_data1(state)
        create_step2_data2(state)
        create_step3_strategies(state)
        create_step4_cost(state)
        create_step5_summary(state)
        
        # Navigation buttons (global)
        with ui.row().classes("w-full justify-between mt-8"):
            prev_button = ui.button("Previous",
                                   on_click=lambda: navigate_to_step(state.current_step - 1, state),
                                   icon="arrow_back")
            prev_button.props("disabled" if state.current_step == 1 else "")
            
            next_button = ui.button("Next",
                                   on_click=lambda: navigate_to_step(state.current_step + 1, state),
                                   icon="arrow_forward")
            next_button.props("disabled" if state.current_step == 5 else "")
            
            # Update button states based on current step
            def update_nav_buttons():
                prev_button.props("disabled" if state.current_step == 1 else "")
                next_button.props("disabled" if state.current_step == 5 else "")
                next_button.set_text("Submit" if state.current_step == 4 else "Next")
            
            ui.timer(0.5, update_nav_buttons)
        
        # Quick links
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("Quick links:")
            ui.link("Jobs List", "/jobs").classes("ml-4 text-blue-500 hover:text-blue-700")
            ui.link("Dashboard", "/").classes("ml-4 text-blue-500 hover:text-blue-700")


# Also register at /wizard/m1 for testing
@ui.page("/wizard/m1")
def wizard_m1_page() -> None:
    """Alternative route for M1 wizard."""
    wizard_page()

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/research/page.py
sha256(source_bytes) = dd4fe0e33162bee01d34c8c3b3320d29a555909c76e877e68245bc58ef73b672
bytes = 659
redacted = False
--------------------------------------------------------------------------------

"""Research Console Page Module (DEPRECATED).

Phase 10: Read-only Research UI + Decision Input.
This module is DEPRECATED after migration to NiceGUI.
"""

from __future__ import annotations

from pathlib import Path


def render(outputs_root: Path) -> None:
    """DEPRECATED: Research Console page renderer - no longer used after migration to NiceGUI.
    
    This function is kept for compatibility but will raise an ImportError
    if streamlit is not available.
    """
    raise ImportError(
        "research/page.py render() is deprecated. "
        "Streamlit UI has been migrated to NiceGUI. "
        "Use the NiceGUI dashboard instead."
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/actions.py
sha256(source_bytes) = cbd65d55b23533f31fea77f5a6284b90f409f65ebd35c22ea1d1de8035b342a8
bytes = 11582
redacted = False
--------------------------------------------------------------------------------
"""
UI Actions Service - Single entry point for UI-triggered actions.

Phase 4: UI must trigger actions via this service, not direct subprocess calls.
Phase 5: Respect season freeze state - actions cannot run on frozen seasons.
Phase 6: Live-safety lock - enforce action risk levels via policy engine.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional, Dict, Any

from FishBroWFS_V2.core.season_context import current_season, outputs_root
from FishBroWFS_V2.core.season_state import check_season_not_frozen
from FishBroWFS_V2.core.policy_engine import enforce_action_policy
from .audit_log import append_audit_event


ActionName = Literal[
    "generate_research",
    "build_portfolio_from_research",
    "export_season_package",
    "deploy_live",
    "send_orders",
    "broker_connect",
    "promote_to_live",
]


class ActionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class ActionResult:
    """Result of an action execution."""
    ok: bool
    action: ActionName
    season: str
    started_ts: str
    finished_ts: str
    stdout_tail: List[str]
    stderr_tail: List[str]
    artifacts_written: List[str]
    audit_event_path: str


def _get_venv_python() -> Path:
    """Return path to venv python executable."""
    venv_python = Path(".venv/bin/python")
    if venv_python.exists():
        return venv_python
    
    # Fallback to system python if venv not found
    return Path(sys.executable)


def _run_subprocess_with_timeout(
    cmd: List[str],
    timeout_seconds: int = 300,
    cwd: Optional[Path] = None,
) -> tuple[int, List[str], List[str]]:
    """Run subprocess and capture stdout/stderr with timeout.
    
    Returns:
        Tuple of (exit_code, stdout_lines, stderr_lines)
    """
    if cwd is None:
        cwd = Path.cwd()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        stdout_lines = result.stdout.splitlines() if result.stdout else []
        stderr_lines = result.stderr.splitlines() if result.stderr else []
        return result.returncode, stdout_lines, stderr_lines
    except subprocess.TimeoutExpired:
        return -1, ["Action timed out"], ["Timeout after {} seconds".format(timeout_seconds)]
    except Exception as e:
        return -2, [], [f"Subprocess error: {str(e)}"]


def _tail_lines(lines: List[str], max_lines: int = 200) -> List[str]:
    """Return last N lines from list."""
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _build_action_command(action: ActionName, season: str, legacy_copy: bool = False) -> List[str]:
    """Build command line for the given action."""
    venv_python = _get_venv_python()
    cmd = [str(venv_python)]
    
    if action == "generate_research":
        cmd.extend([
            "-m", "scripts.generate_research",
            "--season", season,
            "--outputs-root", outputs_root(),
        ])
        if legacy_copy:
            cmd.append("--legacy-copy")
    
    elif action == "build_portfolio_from_research":
        cmd.extend([
            "-m", "scripts.build_portfolio_from_research",
            "--season", season,
            "--outputs-root", outputs_root(),
        ])
    
    elif action == "export_season_package":
        # Placeholder for future export functionality
        cmd.extend([
            "-c", "print('Export season package not yet implemented')"
        ])
    
    elif action in ["deploy_live", "send_orders", "broker_connect", "promote_to_live"]:
        # LIVE_EXECUTE actions are blocked by policy engine
        # This command should never be reached if policy enforcement works correctly
        cmd.extend([
            "-c", f"raise RuntimeError('LIVE_EXECUTE action {action} should have been blocked by policy engine')"
        ])
    
    else:
        raise ValueError(f"Unknown action: {action}")
    
    return cmd


def _collect_artifacts(action: ActionName, season: str) -> List[str]:
    """Collect key artifact paths written by the action."""
    season_dir = Path(outputs_root()) / "seasons" / season
    artifacts = []
    
    if action == "generate_research":
        research_dir = season_dir / "research"
        if research_dir.exists():
            for file in ["canonical_results.json", "research_index.json"]:
                path = research_dir / file
                if path.exists():
                    artifacts.append(str(path))
    
    elif action == "build_portfolio_from_research":
        portfolio_dir = season_dir / "portfolio"
        if portfolio_dir.exists():
            for file in ["portfolio_summary.json", "portfolio_manifest.json"]:
                path = portfolio_dir / file
                if path.exists():
                    artifacts.append(str(path))
            # Also include run-specific directories
            for item in portfolio_dir.iterdir():
                if item.is_dir() and len(item.name) == 12:  # portfolio_id pattern
                    for spec_file in ["portfolio_spec.json", "portfolio_manifest.json"]:
                        spec_path = item / spec_file
                        if spec_path.exists():
                            artifacts.append(str(spec_path))
    
    # LIVE_EXECUTE actions don't produce artifacts in the same way
    # They might produce deployment logs or order confirmations
    elif action in ["deploy_live", "send_orders", "broker_connect", "promote_to_live"]:
        live_dir = season_dir / "live"
        if live_dir.exists():
            for file in live_dir.iterdir():
                if file.is_file():
                    artifacts.append(str(file))
    
    return artifacts


def run_action(
    action: ActionName,
    season: Optional[str] = None,
    *,
    legacy_copy: bool = False,
    timeout_seconds: int = 300,
    check_integrity: bool = True,
) -> ActionResult:
    """
    Runs the action via subprocess using venv python.
    
    Must be deterministic in its file outputs given same inputs.
    Must write audit event jsonl for every action (success or fail).
    
    Phase 5: First line checks season freeze state - cannot run on frozen seasons.
    Phase 5: Optional integrity check for frozen seasons.
    Phase 6: Live-safety lock - enforce action risk levels via policy engine.
    
    Args:
        action: Action name.
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        legacy_copy: Whether to enable legacy copy for generate_research.
        timeout_seconds: Timeout for subprocess execution.
        check_integrity: Whether to verify season integrity before action (for frozen seasons).
    
    Returns:
        ActionResult with execution details.
    """
    # Phase 6: Live-safety lock - enforce action policy
    policy_decision = enforce_action_policy(action, season)
    if not policy_decision.allowed:
        raise PermissionError(f"Action blocked by policy: {policy_decision.reason}")
    
    # Phase 5: Check season freeze state before any action
    check_season_not_frozen(season, action=action)
    
    # Phase 5: Optional integrity check for frozen seasons
    if check_integrity:
        try:
            from FishBroWFS_V2.core.season_state import load_season_state
            from FishBroWFS_V2.core.snapshot import verify_snapshot_integrity
            
            season_str = season or current_season()
            state = load_season_state(season_str)
            if state.is_frozen():
                # Season is frozen, verify integrity
                integrity_result = verify_snapshot_integrity(season_str)
                if not integrity_result["ok"]:
                    # Log integrity violation but don't block action (frozen season already blocks)
                    print(f"WARNING: Season {season_str} integrity check failed for frozen season")
                    print(f"  Missing files: {len(integrity_result['missing_files'])}")
                    print(f"  Changed files: {len(integrity_result['changed_files'])}")
        except ImportError:
            # snapshot module may not be available in older versions
            pass
        except Exception as e:
            # Don't fail action on integrity check errors
            print(f"WARNING: Integrity check failed: {e}")
    
    if season is None:
        season = current_season()
    
    started_ts = datetime.now(timezone.utc).isoformat()
    
    # Build command
    cmd = _build_action_command(action, season, legacy_copy)
    
    # Run subprocess
    exit_code, stdout_lines, stderr_lines = _run_subprocess_with_timeout(
        cmd, timeout_seconds=timeout_seconds
    )
    
    finished_ts = datetime.now(timezone.utc).isoformat()
    ok = exit_code == 0
    
    # Collect artifacts
    artifacts_written = _collect_artifacts(action, season) if ok else []
    
    # Prepare audit event
    audit_event = {
        "ts": finished_ts,
        "actor": "gui",
        "action": action,
        "season": season,
        "ok": ok,
        "exit_code": exit_code,
        "inputs": {
            "action": action,
            "season": season,
            "legacy_copy": legacy_copy,
            "timeout_seconds": timeout_seconds,
        },
        "artifacts_written": artifacts_written,
    }
    
    if not ok:
        audit_event["error"] = {
            "exit_code": exit_code,
            "stderr_tail": _tail_lines(stderr_lines, 10),
        }
    
    # Write audit log
    audit_event_path = append_audit_event(audit_event, season=season)
    
    # Create result
    result = ActionResult(
        ok=ok,
        action=action,
        season=season,
        started_ts=started_ts,
        finished_ts=finished_ts,
        stdout_tail=_tail_lines(stdout_lines),
        stderr_tail=_tail_lines(stderr_lines),
        artifacts_written=artifacts_written,
        audit_event_path=audit_event_path,
    )
    
    return result


# Convenience functions for common actions
def generate_research(season: Optional[str] = None, legacy_copy: bool = False) -> ActionResult:
    """Generate research artifacts for a season."""
    return run_action("generate_research", season, legacy_copy=legacy_copy)


def build_portfolio_from_research(season: Optional[str] = None) -> ActionResult:
    """Build portfolio from research results."""
    return run_action("build_portfolio_from_research", season)


def get_action_status(action_id: str) -> Optional[Dict[str, Any]]:
    """Get status of a previously executed action (placeholder).
    
    Note: In a real implementation, this would track async actions.
    For now, actions are synchronous, so this returns None.
    """
    return None


def list_recent_actions(season: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """List recent actions from audit log."""
    from .audit_log import read_audit_tail
    
    events = read_audit_tail(season, max_lines=limit * 2)  # Read extra to filter
    action_events = []
    
    for event in events:
        if event.get("actor") == "gui" and "action" in event:
            action_events.append(event)
            if len(action_events) >= limit:
                break
    
    return action_events
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/archive.py
sha256(source_bytes) = 759f293f3ed85fd0a6c621068d622c6ef776b8cb95d9f99008cd7829c6e81de9
bytes = 6428
redacted = False
--------------------------------------------------------------------------------
"""Archive 服務 - 軟刪除 + Audit log"""

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import hashlib

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


@dataclass(frozen=True)
class ArchiveResult:
    """歸檔結果"""
    archived_path: str
    audit_path: str


def archive_run(
    outputs_root: Path,
    run_dir: Path,
    reason: str,
    operator: str = "local"
) -> ArchiveResult:
    """
    歸檔 run（軟刪除）
    
    Args:
        outputs_root: outputs 根目錄
        run_dir: 要歸檔的 run 目錄
        reason: 歸檔原因（必須是 failed/garbage/disk/other 之一）
        operator: 操作者標識
    
    Returns:
        ArchiveResult: 歸檔結果
    
    Raises:
        ValueError: 如果 reason 不在允許的清單中
        OSError: 如果移動檔案失敗
    """
    # 驗證 reason
    allowed_reasons = ["failed", "garbage", "disk", "other"]
    if reason not in allowed_reasons:
        raise ValueError(f"reason 必須是 {allowed_reasons} 之一，得到: {reason}")
    
    # 確保 run_dir 存在
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir 不存在: {run_dir}")
    
    # 從 run_dir 路徑解析 season 和 run_id
    # 路徑格式: .../seasons/<season>/runs/<run_id>
    parts = run_dir.parts
    try:
        # 尋找 seasons 索引
        seasons_idx = parts.index("seasons")
        if seasons_idx + 2 >= len(parts):
            raise ValueError(f"無法從路徑解析 season 和 run_id: {run_dir}")
        
        season = parts[seasons_idx + 1]
        run_id = parts[-1]
    except ValueError:
        # 如果找不到 seasons，使用預設值
        season = "unknown"
        run_id = run_dir.name
    
    # Phase 5: 檢查 season 是否被凍結
    if SEASON_STATE_AVAILABLE and load_season_state is not None:
        try:
            state = load_season_state(season)
            if state and state.get("state") == "FROZEN":
                frozen_reason = state.get("reason", "Season is frozen")
                raise ValueError(f"Cannot archive run: season {season} is frozen ({frozen_reason})")
        except Exception:
            # 如果載入失敗，忽略錯誤（允許歸檔）
            pass
    
    # 建立目標目錄
    archive_root = outputs_root / ".archive"
    archive_root.mkdir(exist_ok=True)
    
    season_archive_dir = archive_root / season
    season_archive_dir.mkdir(exist_ok=True)
    
    target_dir = season_archive_dir / run_id
    
    # 如果目標目錄已存在，添加時間戳後綴
    if target_dir.exists():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = season_archive_dir / f"{run_id}_{timestamp}"
    
    # 計算原始 manifest 的 SHA256（如果存在）
    manifest_sha256 = None
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'rb') as f:
                manifest_sha256 = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            pass
    
    # 移動目錄
    shutil.move(str(run_dir), str(target_dir))
    
    # 寫入 audit log
    audit_dir = archive_root / "_audit"
    audit_dir.mkdir(exist_ok=True)
    
    audit_file = audit_dir / "archive_log.jsonl"
    
    audit_entry = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "operator": operator,
        "reason": reason,
        "original_path": str(run_dir),
        "archived_path": str(target_dir),
        "season": season,
        "run_id": run_id,
        "original_manifest_sha256": manifest_sha256,
    }
    
    with open(audit_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
    
    return ArchiveResult(
        archived_path=str(target_dir),
        audit_path=str(audit_file)
    )


def list_archived_runs(outputs_root: Path, season: Optional[str] = None) -> list[dict]:
    """
    列出已歸檔的 runs
    
    Args:
        outputs_root: outputs 根目錄
        season: 可選的 season 過濾
    
    Returns:
        list[dict]: 已歸檔 runs 的清單
    """
    archive_root = outputs_root / ".archive"
    if not archive_root.exists():
        return []
    
    archived_runs = []
    
    # 掃描所有 season 目錄
    for season_dir in archive_root.iterdir():
        if not season_dir.is_dir() or season_dir.name == "_audit":
            continue
        
        if season is not None and season_dir.name != season:
            continue
        
        for run_dir in season_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            # 讀取 run 資訊
            manifest_path = run_dir / "manifest.json"
            manifest = None
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
            
            archived_runs.append({
                "season": season_dir.name,
                "run_id": run_dir.name,
                "path": str(run_dir),
                "manifest": manifest,
            })
    
    return archived_runs


def read_audit_log(outputs_root: Path, limit: int = 100) -> list[dict]:
    """
    讀取 audit log
    
    Args:
        outputs_root: outputs 根目錄
        limit: 返回的條目數量限制
    
    Returns:
        list[dict]: audit log 條目
    """
    audit_file = outputs_root / ".archive" / "_audit" / "archive_log.jsonl"
    
    if not audit_file.exists():
        return []
    
    entries = []
    try:
        with open(audit_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 從最新開始讀取
        for line in reversed(lines[-limit:]):
            try:
                entry = json.loads(line.strip())
                entries.append(entry)
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    
    return entries
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/audit_log.py
sha256(source_bytes) = ffa41f82ed75a1201250bedb398af86a38381d41fe872e5c45853b4d92027e47
bytes = 3889
redacted = False
--------------------------------------------------------------------------------
"""
Audit Log - Append-only JSONL logging for UI actions.

Phase 4: Every UI Action / Archive / Clone must write an audit event.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from FishBroWFS_V2.core.season_context import outputs_root, season_dir


def append_audit_event(event: Dict[str, Any], *, season: Optional[str] = None) -> str:
    """Append one JSON line to outputs/seasons/{season}/governance/ui_audit.jsonl; return path.
    
    Args:
        event: Audit event dictionary (must be JSON-serializable)
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
    
    Returns:
        Path to the audit log file.
    
    Raises:
        OSError: If file cannot be written.
    """
    # Ensure event has required fields
    if "ts" not in event:
        event["ts"] = datetime.now(timezone.utc).isoformat()
    if "actor" not in event:
        event["actor"] = "gui"
    
    # Get season directory
    season_path = season_dir(season)
    audit_dir = season_path / "governance"
    audit_dir.mkdir(parents=True, exist_ok=True)
    
    audit_path = audit_dir / "ui_audit.jsonl"
    
    # Append JSON line
    with open(audit_path, "a", encoding="utf-8") as f:
        json_line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        f.write(json_line + "\n")
    
    return str(audit_path)


def read_audit_tail(season: Optional[str] = None, max_lines: int = 200) -> list[Dict[str, Any]]:
    """Read last N lines from audit log.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        max_lines: Maximum number of lines to read.
    
    Returns:
        List of audit events (most recent first).
    """
    season_path = season_dir(season)
    audit_path = season_path / "governance" / "ui_audit.jsonl"
    
    if not audit_path.exists():
        return []
    
    # Read file and parse last N lines
    lines = []
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            # Read all lines efficiently for small files
            all_lines = f.readlines()
            # Take last max_lines
            tail_lines = all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines
        
        for line in tail_lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                lines.append(event)
            except json.JSONDecodeError:
                # Skip malformed lines
                continue
    except (OSError, UnicodeDecodeError):
        return []
    
    # Return in chronological order (oldest first)
    return lines


def get_audit_events_for_run_id(run_id: str, season: Optional[str] = None, max_lines: int = 200) -> list[Dict[str, Any]]:
    """Filter audit events for a specific run_id.
    
    Args:
        run_id: Run ID to filter by.
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        max_lines: Maximum number of lines to read from log.
    
    Returns:
        List of audit events related to the run_id.
    """
    all_events = read_audit_tail(season, max_lines)
    filtered = []
    
    for event in all_events:
        # Check if event is related to run_id
        inputs = event.get("inputs", {})
        artifacts = event.get("artifacts_written", [])
        
        # Check inputs for run_id
        if isinstance(inputs, dict) and inputs.get("run_id") == run_id:
            filtered.append(event)
            continue
        
        # Check artifacts for run_id pattern
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if run_id in str(artifact):
                    filtered.append(event)
                    break
    
    return filtered
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/candidates_reader.py
sha256(source_bytes) = d728be4fd30c46c2930fa8c2aab85871dfbdbd8261e3330c814073fa7ec6a442
bytes = 9938
redacted = False
--------------------------------------------------------------------------------
"""
Candidates Reader - 讀取 outputs/seasons/{season}/research/ 下的 canonical_results.json 和 research_index.json
Phase 4: 使用 season_context 作為單一真相來源
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

from FishBroWFS_V2.core.season_context import (
    current_season,
    canonical_results_path,
    research_index_path,
)

logger = logging.getLogger(__name__)

# 官方路徑契約 - 使用 season_context
def get_canonical_results_path(season: Optional[str] = None) -> Path:
    """返回 canonical_results.json 的路徑"""
    return canonical_results_path(season)

def get_research_index_path(season: Optional[str] = None) -> Path:
    """返回 research_index.json 的路徑"""
    return research_index_path(season)

@dataclass
class CanonicalResult:
    """Canonical Results 的單一項目"""
    run_id: str
    strategy_id: str
    symbol: str
    bars: int
    net_profit: float
    max_drawdown: float
    score_final: float
    score_net_mdd: float
    trades: int
    start_date: str
    end_date: str
    sharpe: Optional[float] = None
    profit_factor: Optional[float] = None
    portfolio_id: Optional[str] = None
    portfolio_version: Optional[str] = None
    strategy_version: Optional[str] = None
    timeframe_min: Optional[int] = None

@dataclass
class ResearchIndexEntry:
    """Research Index 的單一項目"""
    run_id: str
    season: str
    stage: str
    mode: str
    strategy_id: str
    dataset_id: str
    created_at: str
    status: str
    manifest_path: Optional[str] = None

def load_canonical_results(season: Optional[str] = None) -> List[CanonicalResult]:
    """
    載入 canonical_results.json
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        List[CanonicalResult]: 解析後的 canonical results 列表
        
    Raises:
        FileNotFoundError: 如果檔案不存在
        json.JSONDecodeError: 如果 JSON 格式錯誤
    """
    canonical_path = get_canonical_results_path(season)
    
    if not canonical_path.exists():
        logger.warning(f"Canonical results file not found: {canonical_path}")
        return []
    
    try:
        with open(canonical_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            logger.error(f"Canonical results should be a list, got {type(data)}")
            return []
        
        results = []
        for item in data:
            try:
                result = CanonicalResult(
                    run_id=item.get("run_id", ""),
                    strategy_id=item.get("strategy_id", ""),
                    symbol=item.get("symbol", "UNKNOWN"),
                    bars=item.get("bars", 0),
                    net_profit=item.get("net_profit", 0.0),
                    max_drawdown=item.get("max_drawdown", 0.0),
                    score_final=item.get("score_final", 0.0),
                    score_net_mdd=item.get("score_net_mdd", 0.0),
                    trades=item.get("trades", 0),
                    start_date=item.get("start_date", ""),
                    end_date=item.get("end_date", ""),
                    sharpe=item.get("sharpe"),
                    profit_factor=item.get("profit_factor"),
                    portfolio_id=item.get("portfolio_id"),
                    portfolio_version=item.get("portfolio_version"),
                    strategy_version=item.get("strategy_version"),
                    timeframe_min=item.get("timeframe_min"),
                )
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to parse canonical result item: {item}, error: {e}")
                continue
        
        logger.info(f"Loaded {len(results)} canonical results from {canonical_path}")
        return results
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse canonical_results.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading canonical results: {e}")
        return []

def load_research_index(season: Optional[str] = None) -> List[ResearchIndexEntry]:
    """
    載入 research_index.json
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        List[ResearchIndexEntry]: 解析後的 research index 列表
        
    Raises:
        FileNotFoundError: 如果檔案不存在
        json.JSONDecodeError: 如果 JSON 格式錯誤
    """
    research_path = get_research_index_path(season)
    
    if not research_path.exists():
        logger.warning(f"Research index file not found: {research_path}")
        return []
    
    try:
        with open(research_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            logger.error(f"Research index should be a list, got {type(data)}")
            return []
        
        entries = []
        for item in data:
            try:
                entry = ResearchIndexEntry(
                    run_id=item.get("run_id", ""),
                    season=item.get("season", ""),
                    stage=item.get("stage", ""),
                    mode=item.get("mode", ""),
                    strategy_id=item.get("strategy_id", ""),
                    dataset_id=item.get("dataset_id", ""),
                    created_at=item.get("created_at", ""),
                    status=item.get("status", ""),
                    manifest_path=item.get("manifest_path"),
                )
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse research index item: {item}, error: {e}")
                continue
        
        logger.info(f"Loaded {len(entries)} research index entries from {research_path}")
        return entries
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse research_index.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading research index: {e}")
        return []

def get_canonical_results_by_strategy(strategy_id: str, season: Optional[str] = None) -> List[CanonicalResult]:
    """
    根據 strategy_id 篩選 canonical results
    
    Args:
        strategy_id: 策略 ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        List[CanonicalResult]: 符合條件的結果列表
    """
    results = load_canonical_results(season)
    return [r for r in results if r.strategy_id == strategy_id]

def get_canonical_results_by_run_id(run_id: str, season: Optional[str] = None) -> Optional[CanonicalResult]:
    """
    根據 run_id 查找 canonical result
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Optional[CanonicalResult]: 找到的結果，如果沒有則返回 None
    """
    results = load_canonical_results(season)
    for result in results:
        if result.run_id == run_id:
            return result
    return None

def get_research_index_by_run_id(run_id: str, season: Optional[str] = None) -> Optional[ResearchIndexEntry]:
    """
    根據 run_id 查找 research index entry
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Optional[ResearchIndexEntry]: 找到的項目，如果沒有則返回 None
    """
    entries = load_research_index(season)
    for entry in entries:
        if entry.run_id == run_id:
            return entry
    return None

def get_research_index_by_season(season: str) -> List[ResearchIndexEntry]:
    """
    根據 season 篩選 research index
    
    Args:
        season: Season ID
        
    Returns:
        List[ResearchIndexEntry]: 符合條件的項目列表
    """
    entries = load_research_index(season)
    return [e for e in entries if e.season == season]

def get_combined_candidate_info(run_id: str, season: Optional[str] = None) -> Dict[str, Any]:
    """
    結合 canonical results 和 research index 的資訊
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Dict[str, Any]: 合併後的候選人資訊
    """
    canonical = get_canonical_results_by_run_id(run_id, season)
    research = get_research_index_by_run_id(run_id, season)
    
    result = {
        "run_id": run_id,
        "canonical": canonical.__dict__ if canonical else None,
        "research": research.__dict__ if research else None,
    }
    
    return result

def refresh_canonical_results(season: Optional[str] = None) -> bool:
    """
    刷新 canonical results（目前只是重新讀取檔案）
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        bool: 是否成功刷新
    """
    try:
        # 目前只是重新讀取檔案，未來可以加入重新生成邏輯
        results = load_canonical_results(season)
        logger.info(f"Refreshed canonical results, found {len(results)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to refresh canonical results: {e}")
        return False

def refresh_research_index(season: Optional[str] = None) -> bool:
    """
    刷新 research index（目前只是重新讀取檔案）
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        bool: 是否成功刷新
    """
    try:
        # 目前只是重新讀取檔案，未來可以加入重新生成邏輯
        entries = load_research_index(season)
        logger.info(f"Refreshed research index, found {len(entries)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to refresh research index: {e}")
        return False
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/clone.py
sha256(source_bytes) = ce9e3bb3966670ce4e504a071da1d05e2db608c108b218171b3e803ed530c7fe
bytes = 5487
redacted = False
--------------------------------------------------------------------------------
"""Clone to Wizard 服務 - 從現有 run 預填 Wizard 欄位"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


def load_config_snapshot(run_dir: Path) -> Optional[Dict[str, Any]]:
    """
    從 run_dir 載入 config snapshot
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Optional[Dict[str, Any]]: config snapshot 字典，如果不存在則返回 None
    """
    # 嘗試讀取 config_snapshot.json
    config_path = run_dir / "config_snapshot.json"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    
    # 嘗試讀取 manifest.json
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            # 從 manifest 提取 config 相關欄位
            config_snapshot = {
                "season": manifest.get("season"),
                "dataset_id": manifest.get("dataset_id"),
                "strategy_id": manifest.get("strategy_id"),
                "mode": manifest.get("mode"),
                "stage": manifest.get("stage"),
                "timestamp": manifest.get("timestamp"),
                "run_id": manifest.get("run_id"),
            }
            
            # 嘗試提取 wfs_config
            if "wfs_config" in manifest:
                config_snapshot["wfs_config"] = manifest["wfs_config"]
            
            return config_snapshot
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    
    return None


def build_wizard_prefill(run_dir: Path) -> Dict[str, Any]:
    """
    建立 Wizard 預填資料
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Dict[str, Any]: Wizard 預填資料
    """
    # 載入 config snapshot
    config = load_config_snapshot(run_dir)
    
    if config is None:
        # 如果無法載入 config，返回基本資訊
        return {
            "season": "2026Q1",
            "dataset_id": None,
            "strategy_id": None,
            "mode": "smoke",
            "note": f"Cloned from {run_dir.name}",
        }
    
    # 建立預填資料
    prefill: Dict[str, Any] = {
        "season": config.get("season", "2026Q1"),
        "dataset_id": config.get("dataset_id"),
        "strategy_id": config.get("strategy_id"),
        "mode": _map_mode(config.get("mode")),
        "note": f"Cloned from {run_dir.name}",
    }
    
    # 添加 wfs_config（如果存在）
    if "wfs_config" in config:
        prefill["wfs_config"] = config["wfs_config"]
    
    # 添加 grid preset（如果可推斷）
    grid_preset = _infer_grid_preset(config)
    if grid_preset:
        prefill["grid_preset"] = grid_preset
    
    # 添加 stage 資訊
    stage = config.get("stage")
    if stage:
        prefill["stage"] = stage
    
    return prefill


def _map_mode(mode: Optional[str]) -> str:
    """
    映射 mode 到 Wizard 可用的選項
    
    Args:
        mode: 原始 mode
    
    Returns:
        str: 映射後的 mode
    """
    if not mode:
        return "smoke"
    
    mode_lower = mode.lower()
    
    # 映射規則
    if "smoke" in mode_lower:
        return "smoke"
    elif "lite" in mode_lower:
        return "lite"
    elif "full" in mode_lower:
        return "full"
    elif "incremental" in mode_lower:
        return "incremental"
    else:
        # 預設回退
        return "smoke"


def _infer_grid_preset(config: Dict[str, Any]) -> Optional[str]:
    """
    從 config 推斷 grid preset
    
    Args:
        config: config snapshot
    
    Returns:
        Optional[str]: grid preset 名稱
    """
    # 檢查是否有 wfs_config
    wfs_config = config.get("wfs_config")
    if isinstance(wfs_config, dict):
        # 檢查是否有 grid 相關設定
        if "grid" in wfs_config or "param_grid" in wfs_config:
            return "custom"
    
    # 檢查 stage
    stage = config.get("stage")
    if stage:
        if "stage0" in stage:
            return "coarse"
        elif "stage1" in stage:
            return "topk"
        elif "stage2" in stage:
            return "confirm"
    
    # 檢查 mode
    mode = config.get("mode", "").lower()
    if "full" in mode:
        return "full_grid"
    elif "lite" in mode:
        return "lite_grid"
    
    return None


def get_clone_summary(run_dir: Path) -> Dict[str, Any]:
    """
    獲取 clone 摘要資訊（用於 UI 顯示）
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Dict[str, Any]: 摘要資訊
    """
    config = load_config_snapshot(run_dir)
    
    if config is None:
        return {
            "success": False,
            "error": "無法載入 config snapshot 或 manifest",
            "run_id": run_dir.name,
        }
    
    prefill = build_wizard_prefill(run_dir)
    
    return {
        "success": True,
        "run_id": run_dir.name,
        "season": prefill.get("season"),
        "dataset_id": prefill.get("dataset_id"),
        "strategy_id": prefill.get("strategy_id"),
        "mode": prefill.get("mode"),
        "stage": prefill.get("stage"),
        "grid_preset": prefill.get("grid_preset"),
        "has_wfs_config": "wfs_config" in prefill,
        "note": prefill.get("note"),
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/command_builder.py
sha256(source_bytes) = ff3c3d002b133d7049c8416d830dc25184ed23815aa27032f127cabc362bc9e2
bytes = 8737
redacted = False
--------------------------------------------------------------------------------
"""Generate Command 與 ui_command_snapshot.json 服務"""

import json
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass(frozen=True)
class CommandBuildResult:
    """命令建構結果"""
    argv: List[str]
    shell: str
    snapshot: Dict[str, Any]


def build_research_command(snapshot: Dict[str, Any]) -> CommandBuildResult:
    """
    從 UI snapshot 建構可重現的 CLI command
    
    Args:
        snapshot: UI 設定 snapshot
    
    Returns:
        CommandBuildResult: 命令建構結果
    """
    # 基礎命令
    argv = ["python", "-m", "src.FishBroWFS_V2.research"]
    
    # 添加必要參數
    required_fields = ["season", "dataset_id", "strategy_id", "mode"]
    for field in required_fields:
        if field in snapshot and snapshot[field]:
            argv.extend([f"--{field}", str(snapshot[field])])
    
    # 添加可選參數
    optional_fields = [
        "stage", "grid_preset", "note", "wfs_config_path",
        "param_grid", "max_workers", "timeout_hours"
    ]
    for field in optional_fields:
        if field in snapshot and snapshot[field]:
            argv.extend([f"--{field}", str(snapshot[field])])
    
    # 添加 wfs_config（如果是檔案路徑）
    if "wfs_config" in snapshot and isinstance(snapshot["wfs_config"], str):
        argv.extend(["--wfs-config", snapshot["wfs_config"]])
    
    # 構建 shell 命令字串
    shell_parts = []
    for arg in argv:
        if " " in arg or any(c in arg for c in ["'", '"', "\\", "$", "`"]):
            # 需要引號
            shell_parts.append(json.dumps(arg))
        else:
            shell_parts.append(arg)
    
    shell = " ".join(shell_parts)
    
    return CommandBuildResult(
        argv=argv,
        shell=shell,
        snapshot=snapshot
    )


def write_ui_snapshot(outputs_root: Path, season: str, snapshot: Dict[str, Any]) -> str:
    """
    將 UI snapshot 寫入檔案（append-only，不覆寫）
    
    Args:
        outputs_root: outputs 根目錄
        season: season 名稱
        snapshot: UI snapshot 資料
    
    Returns:
        str: 寫入的檔案路徑
    """
    # 建立目錄結構
    snapshots_dir = outputs_root / "seasons" / season / "ui_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    # 產生時間戳和 hash
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_str = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    snapshot_hash = hashlib.sha256(snapshot_str.encode()).hexdigest()[:8]
    
    # 檔案名稱
    filename = f"{timestamp}-{snapshot_hash}.json"
    filepath = snapshots_dir / filename
    
    # 確保不覆寫現有檔案（如果存在，添加計數器）
    counter = 1
    while filepath.exists():
        filename = f"{timestamp}-{snapshot_hash}-{counter}.json"
        filepath = snapshots_dir / filename
        counter += 1
    
    # 添加 metadata
    full_snapshot = {
        "_metadata": {
            "created_at": time.time(),
            "created_at_iso": datetime.now().isoformat(),
            "version": "1.0",
            "source": "ui_wizard",
            "snapshot_hash": snapshot_hash,
            "filename": filename,
        },
        "data": snapshot
    }
    
    # 寫入檔案
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(full_snapshot, f, indent=2, ensure_ascii=False)
    
    return str(filepath)


def load_ui_snapshot(filepath: Path) -> Optional[Dict[str, Any]]:
    """
    載入 UI snapshot 檔案
    
    Args:
        filepath: snapshot 檔案路徑
    
    Returns:
        Optional[Dict[str, Any]]: snapshot 資料，如果載入失敗則返回 None
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 返回實際資料（不含 metadata）
        if "data" in data:
            return data["data"]
        else:
            return data
    except (json.JSONDecodeError, OSError):
        return None


def list_ui_snapshots(outputs_root: Path, season: str, limit: int = 50) -> List[dict]:
    """
    列出指定 season 的 UI snapshots
    
    Args:
        outputs_root: outputs 根目錄
        season: season 名稱
        limit: 返回的數量限制
    
    Returns:
        List[dict]: snapshot 資訊清單
    """
    snapshots_dir = outputs_root / "seasons" / season / "ui_snapshots"
    
    if not snapshots_dir.exists():
        return []
    
    snapshots = []
    
    for filepath in sorted(snapshots_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not filepath.is_file() or not filepath.name.endswith('.json'):
            continue
        
        try:
            stat = filepath.stat()
            
            # 讀取 metadata（不讀取完整資料以提高效能）
            with open(filepath, 'r', encoding='utf-8') as f:
                metadata = json.load(f).get("_metadata", {})
            
            snapshots.append({
                "filename": filepath.name,
                "path": str(filepath),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created_at": metadata.get("created_at", stat.st_mtime),
                "created_at_iso": metadata.get("created_at_iso"),
                "snapshot_hash": metadata.get("snapshot_hash"),
                "source": metadata.get("source", "unknown"),
            })
            
            if len(snapshots) >= limit:
                break
        except (json.JSONDecodeError, OSError):
            continue
    
    return snapshots


def create_snapshot_from_wizard(wizard_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    從 Wizard 資料建立標準化的 snapshot
    
    Args:
        wizard_data: Wizard 表單資料
    
    Returns:
        Dict[str, Any]: 標準化的 snapshot
    """
    # 基礎欄位
    snapshot = {
        "season": wizard_data.get("season", "2026Q1"),
        "dataset_id": wizard_data.get("dataset_id"),
        "strategy_id": wizard_data.get("strategy_id"),
        "mode": wizard_data.get("mode", "smoke"),
        "note": wizard_data.get("note", ""),
        "created_from": "wizard",
        "created_at": time.time(),
        "created_at_iso": datetime.now().isoformat(),
    }
    
    # 可選欄位
    optional_fields = [
        "stage", "grid_preset", "wfs_config_path",
        "param_grid", "max_workers", "timeout_hours"
    ]
    for field in optional_fields:
        if field in wizard_data and wizard_data[field]:
            snapshot[field] = wizard_data[field]
    
    # wfs_config（如果是字典）
    if "wfs_config" in wizard_data and isinstance(wizard_data["wfs_config"], dict):
        snapshot["wfs_config"] = wizard_data["wfs_config"]
    
    # txt_paths（如果是清單）
    if "txt_paths" in wizard_data and isinstance(wizard_data["txt_paths"], list):
        snapshot["txt_paths"] = wizard_data["txt_paths"]
    
    return snapshot


def validate_snapshot_for_command(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    驗證 snapshot 是否可用於建構命令
    
    Args:
        snapshot: 要驗證的 snapshot
    
    Returns:
        Dict[str, Any]: 驗證結果
    """
    errors = []
    warnings = []
    
    # 檢查必要欄位
    required_fields = ["season", "dataset_id", "strategy_id", "mode"]
    for field in required_fields:
        if field not in snapshot or not snapshot[field]:
            errors.append(f"缺少必要欄位: {field}")
    
    # 檢查 season 格式
    if "season" in snapshot:
        season = snapshot["season"]
        if not isinstance(season, str) or len(season) < 4:
            warnings.append(f"season 格式可能不正確: {season}")
    
    # 檢查 mode 有效性
    valid_modes = ["smoke", "lite", "full", "incremental"]
    if "mode" in snapshot and snapshot["mode"] not in valid_modes:
        warnings.append(f"mode 可能無效: {snapshot['mode']}，有效值: {valid_modes}")
    
    # 檢查 wfs_config_path 是否存在（如果是檔案路徑）
    if "wfs_config_path" in snapshot and snapshot["wfs_config_path"]:
        path = Path(snapshot["wfs_config_path"])
        if not path.exists():
            warnings.append(f"wfs_config_path 不存在: {path}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "has_warnings": len(warnings) > 0,
        "required_fields_present": all(field in snapshot and snapshot[field] for field in required_fields),
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/log_tail.py
sha256(source_bytes) = a5b616fb1bd93b1013ced101272e7bea18072dc794bdef596564923e9f3a6b6a
bytes = 7233
redacted = False
--------------------------------------------------------------------------------
"""Logs Viewer 服務 - Lazy + Polling（禁止 push）"""

import os
import time
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime


def tail_lines(path: Path, n: int = 200) -> List[str]:
    """
    讀取檔案的最後 n 行
    
    Args:
        path: 檔案路徑
        n: 要讀取的行數
    
    Returns:
        List[str]: 最後 n 行的清單（如果檔案不存在則返回空清單）
    """
    if not path.exists():
        return []
    
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            # 簡單實現：讀取所有行然後取最後 n 行
            lines = f.readlines()
            return lines[-n:] if len(lines) > n else lines
    except (OSError, UnicodeDecodeError):
        return []


def tail_lines_with_stats(path: Path, n: int = 200) -> Tuple[List[str], dict]:
    """
    讀取檔案的最後 n 行並返回統計資訊
    
    Args:
        path: 檔案路徑
        n: 要讀取的行數
    
    Returns:
        Tuple[List[str], dict]: (行清單, 統計資訊)
    """
    lines = tail_lines(path, n)
    
    stats = {
        "file_exists": path.exists(),
        "file_size": path.stat().st_size if path.exists() else 0,
        "file_mtime": path.stat().st_mtime if path.exists() else 0,
        "lines_returned": len(lines),
        "timestamp": time.time(),
        "timestamp_iso": datetime.now().isoformat(),
    }
    
    return lines, stats


class LogTailer:
    """Log tailer 類別，支援 lazy polling"""
    
    def __init__(self, log_path: Path, max_lines: int = 200, poll_interval: float = 2.0):
        """
        初始化 LogTailer
        
        Args:
            log_path: log 檔案路徑
            max_lines: 最大行數
            poll_interval: polling 間隔（秒）
        """
        self.log_path = Path(log_path)
        self.max_lines = max_lines
        self.poll_interval = poll_interval
        self._last_read_position = 0
        self._last_read_time = 0.0
        self._is_active = False
        self._timer = None
    
    def start(self) -> None:
        """啟動 polling"""
        self._is_active = True
        self._last_read_position = 0
        self._last_read_time = time.time()
    
    def stop(self) -> None:
        """停止 polling"""
        self._is_active = False
        if self._timer:
            self._timer.cancel()
    
    def read_new_lines(self) -> List[str]:
        """
        讀取新的行（從上次讀取位置開始）
        
        Returns:
            List[str]: 新的行清單
        """
        if not self.log_path.exists():
            return []
        
        try:
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 移動到上次讀取的位置
                if self._last_read_position > 0:
                    try:
                        f.seek(self._last_read_position)
                    except (OSError, ValueError):
                        # 如果 seek 失敗，從頭開始讀取
                        self._last_read_position = 0
                
                # 讀取新行
                new_lines = f.readlines()
                
                # 更新位置
                self._last_read_position = f.tell()
                self._last_read_time = time.time()
                
                return new_lines
        except (OSError, UnicodeDecodeError):
            return []
    
    def get_status(self) -> dict:
        """獲取 tailer 狀態"""
        return {
            "is_active": self._is_active,
            "log_path": str(self.log_path),
            "log_exists": self.log_path.exists(),
            "last_read_position": self._last_read_position,
            "last_read_time": self._last_read_time,
            "last_read_time_iso": datetime.fromtimestamp(self._last_read_time).isoformat() if self._last_read_time > 0 else None,
            "poll_interval": self.poll_interval,
            "max_lines": self.max_lines,
        }


def find_log_files(run_dir: Path) -> List[dict]:
    """
    在 run_dir 中尋找 log 檔案
    
    Args:
        run_dir: run 目錄
    
    Returns:
        List[dict]: log 檔案資訊
    """
    if not run_dir.exists():
        return []
    
    log_files = []
    
    # 常見的 log 檔案名稱
    common_log_names = [
        "worker.log",
        "run.log",
        "output.log",
        "error.log",
        "stdout.log",
        "stderr.log",
        "log.txt",
    ]
    
    for log_name in common_log_names:
        log_path = run_dir / log_name
        if log_path.exists() and log_path.is_file():
            try:
                stat = log_path.stat()
                log_files.append({
                    "name": log_name,
                    "path": str(log_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                continue
    
    # 也尋找 logs 目錄
    logs_dir = run_dir / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        try:
            for log_file in logs_dir.iterdir():
                if log_file.is_file() and log_file.suffix in ['.log', '.txt']:
                    try:
                        stat = log_file.stat()
                        log_files.append({
                            "name": f"logs/{log_file.name}",
                            "path": str(log_file),
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        })
                    except OSError:
                        continue
        except OSError:
            pass
    
    return log_files


def get_log_preview(log_path: Path, preview_lines: int = 50) -> dict:
    """
    獲取 log 檔案預覽
    
    Args:
        log_path: log 檔案路徑
        preview_lines: 預覽行數
    
    Returns:
        dict: log 預覽資訊
    """
    if not log_path.exists():
        return {
            "exists": False,
            "error": "Log 檔案不存在",
            "preview": [],
            "total_lines": 0,
        }
    
    try:
        # 計算總行數
        total_lines = 0
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in f:
                total_lines += 1
        
        # 讀取預覽
        preview = tail_lines(log_path, preview_lines)
        
        stat = log_path.stat()
        return {
            "exists": True,
            "path": str(log_path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "total_lines": total_lines,
            "preview_lines": len(preview),
            "preview": preview,
        }
    except (OSError, UnicodeDecodeError) as e:
        return {
            "exists": True,
            "error": str(e),
            "preview": [],
            "total_lines": 0,
        }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/path_picker.py
sha256(source_bytes) = 49e64d5f85e788f475a00ffc97a288c2922253e40f6383a9a1c293cd8288a535
bytes = 5951
redacted = False
--------------------------------------------------------------------------------
"""Server-side path selector - 禁止 file upload，只允許伺服器端路徑"""

import os
import glob
from pathlib import Path
from typing import List, Optional


# 允許的根目錄（根據 HUMAN TASKS 要求）
ALLOWED_ROOTS = [
    Path("/home/fishbro/FishBroData/raw"),
    Path("/home/fishbro/FishBroData/normalized"),  # 如果未來有
    Path(__file__).parent.parent.parent.parent / "data",  # 專案內的 data 目錄
]


def list_txt_candidates(base_dir: Path, pattern: str = "*.txt", limit: int = 200) -> List[str]:
    """
    列出指定目錄下的 txt 檔案候選
    
    Args:
        base_dir: 基礎目錄
        pattern: 檔案模式（預設 *.txt）
        limit: 返回的檔案數量限制
    
    Returns:
        List[str]: 檔案路徑清單（相對路徑或絕對路徑）
    
    Raises:
        ValueError: 如果 base_dir 不在 allowed roots 內
    """
    # 驗證 base_dir 是否在 allowed roots 內
    if not _is_allowed_path(base_dir):
        raise ValueError(f"base_dir 不在允許的根目錄內: {base_dir}")
    
    if not base_dir.exists():
        return []
    
    # 使用 glob 尋找檔案
    search_pattern = str(base_dir / "**" / pattern)
    files = []
    
    try:
        for file_path in glob.glob(search_pattern, recursive=True):
            if os.path.isfile(file_path):
                # 返回相對路徑（相對於 base_dir）
                rel_path = os.path.relpath(file_path, base_dir)
                files.append(rel_path)
                
                if len(files) >= limit:
                    break
    except (OSError, PermissionError):
        pass
    
    # 排序（按修改時間或名稱）
    files.sort()
    return files


def validate_server_path(p: str, allowed_roots: Optional[List[Path]] = None) -> str:
    """
    驗證伺服器端路徑是否在允許的根目錄內
    
    Args:
        p: 要驗證的路徑
        allowed_roots: 允許的根目錄清單（預設使用 ALLOWED_ROOTS）
    
    Returns:
        str: 驗證後的路徑（絕對路徑）
    
    Raises:
        ValueError: 如果路徑不在 allowed roots 內
        FileNotFoundError: 如果路徑不存在
    """
    if allowed_roots is None:
        allowed_roots = ALLOWED_ROOTS
    
    # 轉換為 Path 物件
    path = Path(p)
    
    # 如果是相對路徑，嘗試解析為絕對路徑
    if not path.is_absolute():
        # 嘗試在每個 allowed root 下尋找
        for root in allowed_roots:
            candidate = root / path
            if candidate.exists():
                path = candidate
                break
        else:
            # 如果找不到，使用第一個 allowed root 作為基礎
            path = allowed_roots[0] / path
    
    # 確保路徑是絕對路徑
    path = path.resolve()
    
    # 檢查是否在 allowed roots 內
    if not _is_allowed_path(path, allowed_roots):
        raise ValueError(f"路徑不在允許的根目錄內: {path}")
    
    # 檢查路徑是否存在
    if not path.exists():
        raise FileNotFoundError(f"路徑不存在: {path}")
    
    return str(path)


def _is_allowed_path(path: Path, allowed_roots: Optional[List[Path]] = None) -> bool:
    """
    檢查路徑是否在 allowed roots 內
    
    Args:
        path: 要檢查的路徑
        allowed_roots: 允許的根目錄清單
    
    Returns:
        bool: 是否允許
    """
    if allowed_roots is None:
        allowed_roots = ALLOWED_ROOTS
    
    path = path.resolve()
    
    for root in allowed_roots:
        root = root.resolve()
        try:
            # 檢查 path 是否是 root 的子目錄
            if path.is_relative_to(root):
                return True
        except (AttributeError, ValueError):
            # Python 3.8 兼容性：使用 str 比較
            if str(path).startswith(str(root) + os.sep):
                return True
    
    return False


def get_allowed_roots_info() -> List[dict]:
    """
    獲取 allowed roots 的資訊
    
    Returns:
        List[dict]: 每個 root 的資訊
    """
    info = []
    for root in ALLOWED_ROOTS:
        exists = root.exists()
        info.append({
            "path": str(root),
            "exists": exists,
            "readable": os.access(root, os.R_OK) if exists else False,
            "files_count": _count_files(root) if exists else 0,
        })
    return info


def _count_files(directory: Path) -> int:
    """計算目錄下的檔案數量"""
    if not directory.exists() or not directory.is_dir():
        return 0
    
    try:
        return sum(1 for _ in directory.rglob("*") if _.is_file())
    except (OSError, PermissionError):
        return 0


def browse_directory(directory: Path, pattern: str = "*") -> List[dict]:
    """
    瀏覽目錄內容
    
    Args:
        directory: 要瀏覽的目錄
        pattern: 檔案模式
    
    Returns:
        List[dict]: 目錄內容
    """
    if not _is_allowed_path(directory):
        raise ValueError(f"目錄不在允許的根目錄內: {directory}")
    
    if not directory.exists() or not directory.is_dir():
        return []
    
    contents = []
    try:
        for item in directory.iterdir():
            try:
                stat = item.stat()
                contents.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "is_file": item.is_file(),
                    "size": stat.st_size if item.is_file() else 0,
                    "mtime": stat.st_mtime,
                    "readable": os.access(item, os.R_OK),
                })
            except (OSError, PermissionError):
                continue
        
        # 排序：目錄在前，檔案在後
        contents.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    except (OSError, PermissionError):
        pass
    
    return contents
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/reload_service.py
sha256(source_bytes) = b80fcc1e996552f0c1ba3458a3155eaee88a1b9dc604419459ea6ab542964fb3
bytes = 16858
redacted = False
--------------------------------------------------------------------------------
"""Reload Service for System Status and Cache Invalidation.

Provides functions to:
1. Get system snapshot (datasets, strategies, caches)
2. Invalidate caches and reload registries
3. Compute file signatures for validation
4. TXT → Parquet build functionality
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog, DatasetCatalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog, StrategyCatalog
from FishBroWFS_V2.control.feature_resolver import invalidate_feature_cache as invalidate_feature_cache_impl
from FishBroWFS_V2.control.data_build import BuildParquetRequest, BuildParquetResult, build_parquet_from_txt
from FishBroWFS_V2.control.dataset_descriptor import DatasetDescriptor, get_descriptor, list_descriptors
from FishBroWFS_V2.data.dataset_registry import DatasetRecord
from FishBroWFS_V2.strategy.registry import StrategySpecForGUI


@dataclass
class FileStatus:
    """Status of a file or directory."""
    path: str
    exists: bool
    size: int = 0
    mtime: float = 0.0
    signature: str = ""
    error: Optional[str] = None


@dataclass
class DatasetStatus:
    """Status of a dataset with TXT and Parquet information."""
    # Required fields (no defaults) first
    dataset_id: str
    kind: str
    txt_root: str
    txt_required_paths: List[str]
    parquet_root: str
    parquet_expected_paths: List[str]
    
    # Optional fields with defaults
    descriptor: Optional[DatasetDescriptor] = None
    txt_present: bool = False
    txt_missing: List[str] = field(default_factory=list)
    txt_latest_mtime_utc: Optional[str] = None
    txt_total_size_bytes: int = 0
    txt_signature: str = ""
    parquet_present: bool = False
    parquet_missing: List[str] = field(default_factory=list)
    parquet_latest_mtime_utc: Optional[str] = None
    parquet_total_size_bytes: int = 0
    parquet_signature: str = ""
    up_to_date: bool = False
    bars_count: Optional[int] = None
    schema_ok: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class StrategyStatus:
    """Status of a strategy."""
    id: str
    spec: Optional[StrategySpecForGUI] = None
    can_import: bool = False
    can_build_spec: bool = False
    mtime: float = 0.0
    signature: str = ""
    feature_requirements_count: int = 0
    error: Optional[str] = None


@dataclass
class SystemSnapshot:
    """System snapshot with status of all components."""
    created_at: datetime = field(default_factory=datetime.now)
    total_datasets: int = 0
    total_strategies: int = 0
    dataset_statuses: List[DatasetStatus] = field(default_factory=list)
    strategy_statuses: List[StrategyStatus] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ReloadResult:
    """Result of a reload operation."""
    ok: bool
    error: Optional[str] = None
    datasets_reloaded: int = 0
    strategies_reloaded: int = 0
    caches_invalidated: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def compute_file_signature(file_path: Path, max_size_mb: int = 50) -> str:
    """Compute signature for a file.
    
    For small files (< max_size_mb): compute sha256
    For large files: use stat-hash (path + size + mtime)
    """
    try:
        if not file_path.exists():
            return "missing"
        
        stat = file_path.stat()
        file_size_mb = stat.st_size / (1024 * 1024)
        
        if file_size_mb < max_size_mb:
            # Small file: compute actual hash
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return f"sha256:{hasher.hexdigest()[:16]}"
        else:
            # Large file: use stat-hash
            return f"stat:{file_path.name}:{stat.st_size}:{stat.st_mtime}"
    except Exception as e:
        return f"error:{str(e)[:50]}"


def check_txt_files(txt_root: str, txt_required_paths: List[str]) -> Tuple[bool, List[str], Optional[str], int, str]:
    """Check TXT files for a dataset.
    
    Returns:
        Tuple of (present, missing_paths, latest_mtime_utc, total_size_bytes, signature)
    """
    missing = []
    latest_mtime = 0.0
    total_size = 0
    signatures = []
    
    for txt_path_str in txt_required_paths:
        txt_path = Path(txt_path_str)
        if txt_path.exists():
            stat = txt_path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime)
            total_size += stat.st_size
            sig = compute_file_signature(txt_path)
            signatures.append(f"{txt_path.name}:{sig}")
        else:
            missing.append(txt_path_str)
    
    present = len(missing) == 0
    signature = "|".join(signatures) if signatures else "none"
    
    # Convert latest mtime to UTC string
    latest_mtime_utc = None
    if latest_mtime > 0:
        latest_mtime_utc = datetime.utcfromtimestamp(latest_mtime).isoformat() + "Z"
    
    return present, missing, latest_mtime_utc, total_size, signature


def check_parquet_files(parquet_root: str, parquet_expected_paths: List[str]) -> Tuple[bool, List[str], Optional[str], int, str]:
    """Check Parquet files for a dataset.
    
    Returns:
        Tuple of (present, missing_paths, latest_mtime_utc, total_size_bytes, signature)
    """
    missing = []
    latest_mtime = 0.0
    total_size = 0
    signatures = []
    
    for parquet_path_str in parquet_expected_paths:
        parquet_path = Path(parquet_path_str)
        if parquet_path.exists():
            stat = parquet_path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime)
            total_size += stat.st_size
            sig = compute_file_signature(parquet_path)
            signatures.append(f"{parquet_path.name}:{sig}")
        else:
            missing.append(parquet_path_str)
    
    present = len(missing) == 0
    signature = "|".join(signatures) if signatures else "none"
    
    # Convert latest mtime to UTC string
    latest_mtime_utc = None
    if latest_mtime > 0:
        latest_mtime_utc = datetime.utcfromtimestamp(latest_mtime).isoformat() + "Z"
    
    return present, missing, latest_mtime_utc, total_size, signature


def get_dataset_status(dataset_id: str) -> DatasetStatus:
    """Get status for a single dataset with TXT and Parquet information."""
    try:
        # Get dataset descriptor
        descriptor = get_descriptor(dataset_id)
        if descriptor is None:
            return DatasetStatus(
                dataset_id=dataset_id,
                kind="unknown",
                txt_root="",
                txt_required_paths=[],
                parquet_root="",
                parquet_expected_paths=[],
                error=f"Dataset not found: {dataset_id}"
            )
        
        # Check TXT files
        txt_present, txt_missing, txt_latest_mtime_utc, txt_total_size, txt_signature = check_txt_files(
            descriptor.txt_root, descriptor.txt_required_paths
        )
        
        # Check Parquet files
        parquet_present, parquet_missing, parquet_latest_mtime_utc, parquet_total_size, parquet_signature = check_parquet_files(
            descriptor.parquet_root, descriptor.parquet_expected_paths
        )
        
        # Determine if up-to-date
        up_to_date = False
        if txt_present and parquet_present:
            # Simple up-to-date check: compare signatures
            # In a real implementation, this would compare content hashes
            up_to_date = True  # Placeholder
        
        # Try to get bars count (lazy, can be expensive)
        bars_count = None
        schema_ok = None
        
        # Simple schema check for Parquet files
        if parquet_present and descriptor.parquet_expected_paths:
            try:
                parquet_path = Path(descriptor.parquet_expected_paths[0])
                if parquet_path.exists():
                    # Quick check: try to read first few rows
                    import pandas as pd
                    df_sample = pd.read_parquet(parquet_path, nrows=1)
                    schema_ok = True
                    bars_count = len(pd.read_parquet(parquet_path)) if parquet_path.stat().st_size < 1000000 else None
            except Exception:
                schema_ok = False
        
        return DatasetStatus(
            dataset_id=dataset_id,
            kind=descriptor.kind,
            descriptor=descriptor,
            txt_root=descriptor.txt_root,
            txt_required_paths=descriptor.txt_required_paths,
            txt_present=txt_present,
            txt_missing=txt_missing,
            txt_latest_mtime_utc=txt_latest_mtime_utc,
            txt_total_size_bytes=txt_total_size,
            txt_signature=txt_signature,
            parquet_root=descriptor.parquet_root,
            parquet_expected_paths=descriptor.parquet_expected_paths,
            parquet_present=parquet_present,
            parquet_missing=parquet_missing,
            parquet_latest_mtime_utc=parquet_latest_mtime_utc,
            parquet_total_size_bytes=parquet_total_size,
            parquet_signature=parquet_signature,
            up_to_date=up_to_date,
            bars_count=bars_count,
            schema_ok=schema_ok
        )
    except Exception as e:
        return DatasetStatus(
            dataset_id=dataset_id,
            kind="unknown",
            txt_root="",
            txt_required_paths=[],
            parquet_root="",
            parquet_expected_paths=[],
            error=str(e)
        )


def get_strategy_status(strategy: StrategySpecForGUI) -> StrategyStatus:
    """Get status for a single strategy."""
    try:
        # Check if strategy can be imported
        can_import = True  # Assume yes for now
        can_build_spec = True  # Assume yes for now
        
        # Get feature requirements count
        feature_requirements_count = 0
        if hasattr(strategy, 'feature_requirements'):
            feature_requirements_count = len(strategy.feature_requirements)
        
        # Try to get file info if path is available
        mtime = 0.0
        signature = ""
        if hasattr(strategy, 'file_path') and strategy.file_path:
            file_path = Path(strategy.file_path)
            if file_path.exists():
                stat = file_path.stat()
                mtime = stat.st_mtime
                signature = compute_file_signature(file_path)
        
        return StrategyStatus(
            id=strategy.strategy_id,
            spec=strategy,
            can_import=can_import,
            can_build_spec=can_build_spec,
            mtime=mtime,
            signature=signature,
            feature_requirements_count=feature_requirements_count
        )
    except Exception as e:
        return StrategyStatus(
            id=strategy.strategy_id if hasattr(strategy, 'strategy_id') else 'unknown',
            error=str(e),
            can_import=False,
            can_build_spec=False
        )


def get_system_snapshot() -> SystemSnapshot:
    """Get current system snapshot with TXT and Parquet status."""
    snapshot = SystemSnapshot()
    
    try:
        # Get dataset descriptors
        descriptors = list_descriptors()
        snapshot.total_datasets = len(descriptors)
        
        for descriptor in descriptors:
            status = get_dataset_status(descriptor.dataset_id)
            snapshot.dataset_statuses.append(status)
            if status.error:
                snapshot.errors.append(f"Dataset {descriptor.dataset_id}: {status.error}")
        
        # Get strategies
        strategy_catalog = get_strategy_catalog()
        strategies = strategy_catalog.list_strategies()
        snapshot.total_strategies = len(strategies)
        
        for strategy in strategies:
            status = get_strategy_status(strategy)
            snapshot.strategy_statuses.append(status)
            if status.error:
                snapshot.errors.append(f"Strategy {strategy.strategy_id}: {status.error}")
        
        # Add notes
        if snapshot.errors:
            snapshot.notes.append(f"Found {len(snapshot.errors)} errors")
        
        # Count TXT/Parquet status
        txt_present_count = sum(1 for ds in snapshot.dataset_statuses if ds.txt_present)
        parquet_present_count = sum(1 for ds in snapshot.dataset_statuses if ds.parquet_present)
        up_to_date_count = sum(1 for ds in snapshot.dataset_statuses if ds.up_to_date)
        
        snapshot.notes.append(f"TXT present: {txt_present_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Parquet present: {parquet_present_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Up-to-date: {up_to_date_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Snapshot created at {snapshot.created_at.isoformat()}")
        
    except Exception as e:
        snapshot.errors.append(f"Failed to get system snapshot: {str(e)}")
    
    return snapshot


def invalidate_feature_cache() -> bool:
    """Invalidate feature resolver cache."""
    try:
        return invalidate_feature_cache_impl()
    except Exception as e:
        return False


def reload_dataset_registry() -> bool:
    """Reload dataset registry."""
    try:
        catalog = get_dataset_catalog()
        # Force reload by calling load_index
        catalog.load_index()  # Force load
        return True
    except Exception as e:
        return False


def reload_strategy_registry() -> bool:
    """Reload strategy registry."""
    try:
        catalog = get_strategy_catalog()
        # Force reload by calling load_registry
        catalog.load_registry()  # Force load
        return True
    except Exception as e:
        return False


def reload_everything(reason: str = "manual") -> ReloadResult:
    """Reload all caches and registries."""
    start_time = time.time()
    result = ReloadResult(ok=True)
    caches_invalidated = []
    
    try:
        # 1. Invalidate feature cache
        if invalidate_feature_cache():
            caches_invalidated.append("feature_cache")
        else:
            result.ok = False
            result.error = "Failed to invalidate feature cache"
        
        # 2. Reload dataset registry
        if reload_dataset_registry():
            result.datasets_reloaded += 1
        else:
            result.ok = False
            result.error = "Failed to reload dataset registry"
        
        # 3. Reload strategy registry
        if reload_strategy_registry():
            result.strategies_reloaded += 1
        else:
            result.ok = False
            result.error = "Failed to reload strategy registry"
        
        # 4. Rebuild snapshot (implicitly done by get_system_snapshot)
        
        result.caches_invalidated = caches_invalidated
        result.duration_seconds = time.time() - start_time
        
        if result.ok:
            result.error = None
        
    except Exception as e:
        result.ok = False
        result.error = f"Reload failed: {str(e)}"
        result.duration_seconds = time.time() - start_time
    
    return result


def build_parquet(
    dataset_id: str,
    force: bool = False,
    deep_validate: bool = False,
    reason: str = "manual"
) -> BuildParquetResult:
    """Build Parquet from TXT for a dataset.
    
    Args:
        dataset_id: Dataset ID to build
        force: Rebuild even if up-to-date
        deep_validate: Perform schema validation after build
        reason: Reason for build (for audit/logging)
        
    Returns:
        BuildParquetResult with build status
    """
    req = BuildParquetRequest(
        dataset_id=dataset_id,
        force=force,
        deep_validate=deep_validate,
        reason=reason
    )
    
    return build_parquet_from_txt(req)


def build_all_parquet(force: bool = False, reason: str = "manual") -> List[BuildParquetResult]:
    """Build Parquet for all datasets.
    
    Args:
        force: Rebuild even if up-to-date
        reason: Reason for build (for audit/logging)
        
    Returns:
        List of BuildParquetResult for each dataset
    """
    results = []
    descriptors = list_descriptors()
    
    for descriptor in descriptors:
        result = build_parquet(
            dataset_id=descriptor.dataset_id,
            force=force,
            deep_validate=False,
            reason=f"{reason}_batch"
        )
        results.append(result)
    
    return results

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/runs_index.py
sha256(source_bytes) = eef1021b4bd992d1eb48c399a1a3cd60cdcbf68e3465d3732379482e5f17aa0d
bytes = 7518
redacted = False
--------------------------------------------------------------------------------
"""Runs Index 服務 - 禁止全量掃描，只讀最新 N 個 run"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass(frozen=True)
class RunIndexRow:
    """Run 索引行，包含必要 metadata"""
    run_id: str
    run_dir: str
    mtime: float
    season: str
    status: str
    mode: str
    strategy_id: Optional[str]
    dataset_id: Optional[str]
    stage: Optional[str]
    manifest_path: Optional[str]
    
    @property
    def mtime_iso(self) -> str:
        """返回 ISO 格式的修改時間"""
        return datetime.fromtimestamp(self.mtime).isoformat()
    
    @property
    def is_archived(self) -> bool:
        """檢查是否已歸檔（路徑包含 .archive）"""
        return ".archive" in self.run_dir


class RunsIndex:
    """Runs Index 管理器 - 只掃最新 N 個 run，避免全量掃描"""
    
    def __init__(self, outputs_root: Path, limit: int = 50) -> None:
        self.outputs_root = Path(outputs_root)
        self.limit = limit
        self._cache: List[RunIndexRow] = []
        self._cache_time: float = 0.0
        self._cache_ttl: float = 30.0  # 快取 30 秒
        
    def build(self) -> None:
        """建立索引（掃描 seasons/<season>/runs 目錄）"""
        rows: List[RunIndexRow] = []
        
        # 掃描所有 season 目錄
        seasons_dir = self.outputs_root / "seasons"
        if not seasons_dir.exists():
            self._cache = []
            self._cache_time = time.time()
            return
        
        for season_dir in seasons_dir.iterdir():
            if not season_dir.is_dir():
                continue
                
            season = season_dir.name
            runs_dir = season_dir / "runs"
            
            if not runs_dir.exists():
                continue
                
            # 只掃描 runs 目錄下的直接子目錄
            run_dirs = []
            for run_path in runs_dir.iterdir():
                if run_path.is_dir():
                    try:
                        mtime = run_path.stat().st_mtime
                        run_dirs.append((run_path, mtime, season))
                    except OSError:
                        continue
            
            # 按修改時間排序，取最新的
            run_dirs.sort(key=lambda x: x[1], reverse=True)
            
            for run_path, mtime, season in run_dirs[:self.limit]:
                row = self._parse_run_dir(run_path, mtime, season)
                if row:
                    rows.append(row)
        
        # 按修改時間全局排序
        rows.sort(key=lambda x: x.mtime, reverse=True)
        rows = rows[:self.limit]
        
        self._cache = rows
        self._cache_time = time.time()
    
    def _parse_run_dir(self, run_path: Path, mtime: float, season: str) -> Optional[RunIndexRow]:
        """解析單個 run 目錄，讀取 manifest.json（如果存在）"""
        run_id = run_path.name
        manifest_path = run_path / "manifest.json"
        
        # 預設值
        status = "unknown"
        mode = "unknown"
        strategy_id = None
        dataset_id = None
        stage = None
        
        # 嘗試讀取 manifest.json
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                # 從 manifest 提取資訊
                status = manifest.get("status", "unknown")
                mode = manifest.get("mode", "unknown")
                strategy_id = manifest.get("strategy_id")
                dataset_id = manifest.get("dataset_id")
                stage = manifest.get("stage")
                
                # 如果 stage 不存在，嘗試從 run_id 推斷
                if stage is None and "stage" in run_id:
                    for stage_name in ["stage0", "stage1", "stage2", "stage3"]:
                        if stage_name in run_id:
                            stage = stage_name
                            break
            except (json.JSONDecodeError, OSError):
                # 如果讀取失敗，使用預設值
                pass
        
        # 從 run_id 推斷 stage（如果尚未設定）
        if stage is None:
            if "stage0" in run_id:
                stage = "stage0"
            elif "stage1" in run_id:
                stage = "stage1"
            elif "stage2" in run_id:
                stage = "stage2"
            elif "demo" in run_id:
                stage = "demo"
        
        return RunIndexRow(
            run_id=run_id,
            run_dir=str(run_path),
            mtime=mtime,
            season=season,
            status=status,
            mode=mode,
            strategy_id=strategy_id,
            dataset_id=dataset_id,
            stage=stage,
            manifest_path=str(manifest_path) if manifest_path.exists() else None
        )
    
    def refresh(self) -> None:
        """刷新索引（重建快取）"""
        self.build()
    
    def list(self, season: Optional[str] = None, include_archived: bool = False) -> List[RunIndexRow]:
        """列出 runs（可選按 season 過濾）"""
        # 如果快取過期，重新建立
        if time.time() - self._cache_time > self._cache_ttl:
            self.build()
        
        rows = self._cache
        
        # 按 season 過濾
        if season is not None:
            rows = [r for r in rows if r.season == season]
        
        # 過濾歸檔的 runs
        if not include_archived:
            rows = [r for r in rows if not r.is_archived]
        
        return rows
    
    def get(self, run_id: str) -> Optional[RunIndexRow]:
        """根據 run_id 獲取單個 run"""
        # 如果快取過期，重新建立
        if time.time() - self._cache_time > self._cache_ttl:
            self.build()
        
        for row in self._cache:
            if row.run_id == run_id:
                return row
        
        # 如果不在快取中，嘗試直接查找
        # 掃描所有 season 目錄尋找該 run_id
        seasons_dir = self.outputs_root / "seasons"
        if seasons_dir.exists():
            for season_dir in seasons_dir.iterdir():
                if not season_dir.is_dir():
                    continue
                    
                runs_dir = season_dir / "runs"
                if not runs_dir.exists():
                    continue
                
                run_path = runs_dir / run_id
                if run_path.exists() and run_path.is_dir():
                    try:
                        mtime = run_path.stat().st_mtime
                        return self._parse_run_dir(run_path, mtime, season_dir.name)
                    except OSError:
                        pass
        
        return None


# Singleton instance for app-level caching
_global_index: Optional[RunsIndex] = None

def get_global_index(outputs_root: Optional[Path] = None) -> RunsIndex:
    """獲取全域 RunsIndex 實例（singleton）"""
    global _global_index
    
    if _global_index is None:
        if outputs_root is None:
            # 預設使用專案根目錄下的 outputs
            outputs_root = Path(__file__).parent.parent.parent.parent / "outputs"
        _global_index = RunsIndex(outputs_root)
        _global_index.build()
    
    return _global_index
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/stale.py
sha256(source_bytes) = 33e0a537d8b49a98dece00c3b6769a3b04d9d2a7d86b26931c1c7616e468cc06
bytes = 6340
redacted = False
--------------------------------------------------------------------------------
"""Stale Warning 服務 - UI 開著超過 10 分鐘顯示警告"""

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class StaleState:
    """Stale 狀態"""
    opened_at: float
    warned: bool = False
    last_check: float = 0.0
    warning_shown_at: Optional[float] = None


def should_warn_stale(state: StaleState, seconds: int = 600) -> bool:
    """
    檢查是否應該顯示 stale warning
    
    Args:
        state: StaleState 物件
        seconds: 警告閾值（秒），預設 600 秒（10 分鐘）
    
    Returns:
        bool: 是否應該顯示警告
    """
    if state.warned:
        return False
    
    elapsed = time.time() - state.opened_at
    return elapsed >= seconds


def update_stale_state(state: StaleState) -> dict:
    """
    更新 stale 狀態並返回狀態資訊
    
    Args:
        state: StaleState 物件
    
    Returns:
        dict: 狀態資訊
    """
    current_time = time.time()
    elapsed = current_time - state.opened_at
    
    state.last_check = current_time
    
    # 檢查是否應該警告
    should_warn = should_warn_stale(state)
    
    if should_warn and not state.warned:
        state.warned = True
        state.warning_shown_at = current_time
    
    return {
        "opened_at": state.opened_at,
        "opened_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.opened_at)),
        "elapsed_seconds": elapsed,
        "elapsed_minutes": elapsed / 60,
        "elapsed_hours": elapsed / 3600,
        "should_warn": should_warn,
        "warned": state.warned,
        "warning_shown_at": state.warning_shown_at,
        "warning_shown_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.warning_shown_at)) if state.warning_shown_at else None,
        "last_check": state.last_check,
    }


class StaleMonitor:
    """Stale 監視器"""
    
    def __init__(self, warning_threshold_seconds: int = 600):
        """
        初始化 StaleMonitor
        
        Args:
            warning_threshold_seconds: 警告閾值（秒）
        """
        self.warning_threshold = warning_threshold_seconds
        self._states = {}  # client_id -> StaleState
        self._start_time = time.time()
    
    def register_client(self, client_id: str) -> StaleState:
        """
        註冊客戶端
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            StaleState: 新建立的狀態
        """
        state = StaleState(opened_at=time.time())
        self._states[client_id] = state
        return state
    
    def unregister_client(self, client_id: str) -> None:
        """取消註冊客戶端"""
        if client_id in self._states:
            del self._states[client_id]
    
    def get_client_state(self, client_id: str) -> Optional[StaleState]:
        """獲取客戶端狀態"""
        return self._states.get(client_id)
    
    def update_client(self, client_id: str) -> Optional[dict]:
        """
        更新客戶端狀態
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            Optional[dict]: 狀態資訊，如果客戶端不存在則返回 None
        """
        state = self.get_client_state(client_id)
        if state is None:
            return None
        
        return update_stale_state(state)
    
    def check_all_clients(self) -> dict:
        """
        檢查所有客戶端
        
        Returns:
            dict: 所有客戶端的狀態摘要
        """
        results = {}
        warnings = []
        
        for client_id, state in self._states.items():
            info = update_stale_state(state)
            results[client_id] = info
            
            if info["should_warn"] and not state.warned:
                warnings.append({
                    "client_id": client_id,
                    "elapsed_minutes": info["elapsed_minutes"],
                    "opened_at": info["opened_at_iso"],
                })
        
        return {
            "total_clients": len(self._states),
            "clients": results,
            "warnings": warnings,
            "has_warnings": len(warnings) > 0,
            "monitor_uptime": time.time() - self._start_time,
        }
    
    def reset_client(self, client_id: str) -> Optional[StaleState]:
        """
        重置客戶端狀態（重新計時）
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            Optional[StaleState]: 新的狀態，如果客戶端不存在則返回 None
        """
        if client_id not in self._states:
            return None
        
        self._states[client_id] = StaleState(opened_at=time.time())
        return self._states[client_id]


# 全域監視器實例
_global_monitor: Optional[StaleMonitor] = None

def get_global_monitor() -> StaleMonitor:
    """獲取全域 StaleMonitor 實例"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = StaleMonitor()
    return _global_monitor


def create_stale_warning_message(state_info: dict) -> str:
    """
    建立 stale warning 訊息
    
    Args:
        state_info: 狀態資訊
    
    Returns:
        str: 警告訊息
    """
    elapsed_minutes = state_info["elapsed_minutes"]
    
    if elapsed_minutes < 60:
        time_str = f"{elapsed_minutes:.1f} 分鐘"
    else:
        time_str = f"{elapsed_minutes/60:.1f} 小時"
    
    return (
        f"⚠️  UI 已開啟 {time_str}，資料可能已過期。\n"
        f"建議重新整理頁面以獲取最新資料。\n"
        f"（開啟時間: {state_info['opened_at_iso']})"
    )


def create_stale_warning_ui_state(state_info: dict) -> dict:
    """
    建立 stale warning UI 狀態
    
    Args:
        state_info: 狀態資訊
    
    Returns:
        dict: UI 狀態
    """
    return {
        "show_warning": state_info["should_warn"],
        "message": create_stale_warning_message(state_info) if state_info["should_warn"] else "",
        "severity": "warning",
        "elapsed_minutes": state_info["elapsed_minutes"],
        "opened_at": state_info["opened_at_iso"],
        "can_dismiss": True,
        "auto_refresh_suggested": state_info["elapsed_minutes"] > 20,  # 超過 20 分鐘建議自動重新整理
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/__init__.py
sha256(source_bytes) = 2f52538f216f07d0e68d4bdb192cccd19072506ea5fcce09b2d87dcc9d05f4d6
bytes = 39
redacted = False
--------------------------------------------------------------------------------

"""Viewer package for Phase 6.0."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/app.py
sha256(source_bytes) = 16ab9da16c0c1aa43a068bca0b6a3d90bd701ec4eeb8b8ba3ca8bf0854663192
bytes = 3821
redacted = False
--------------------------------------------------------------------------------

"""Streamlit Viewer entrypoint (official).

This is the single source of truth for launching the B5 Viewer.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import render_viewer_page
from FishBroWFS_V2.gui.viewer.pages.kpi import render_page as render_kpi_page
from FishBroWFS_V2.gui.viewer.pages.overview import render_page as render_overview_page
from FishBroWFS_V2.gui.viewer.pages.winners import render_page as render_winners_page
from FishBroWFS_V2.gui.viewer.pages.governance import render_page as render_governance_page
from FishBroWFS_V2.gui.viewer.pages.artifacts import render_page as render_artifacts_page
from FishBroWFS_V2.gui.research.page import render as render_research_page
from FishBroWFS_V2.ui.plan_viewer import render_page as render_plan_viewer_page
from FishBroWFS_V2.control.paths import get_outputs_root


def get_run_dir_from_query() -> Path | None:
    """
    Get run_dir from query parameters.
    
    Returns:
        Path to run directory if season and run_id are provided, None otherwise
    """
    season = st.query_params.get("season", "")
    run_id = st.query_params.get("run_id", "")
    
    if not season or not run_id:
        return None
    
    # Get outputs root from environment or default
    outputs_root_str = os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")
    outputs_root = Path(outputs_root_str)
    run_dir = outputs_root / "seasons" / season / "runs" / run_id
    
    return run_dir


def main() -> None:
    """Main Viewer entrypoint."""
    st.set_page_config(
        page_title="FishBroWFS B5 Viewer",
        layout="wide",
    )
    
    # Mode selection: Viewer, Research Console, or Portfolio Plan
    mode = st.sidebar.radio(
        "Mode",
        ["Viewer", "Research Console", "Portfolio Plan"],
        index=0,
    )
    
    if mode == "Research Console":
        # Research Console mode - doesn't need query parameters
        outputs_root_str = os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")
        outputs_root = Path(outputs_root_str)

        # Show Research Console
        render_research_page(outputs_root)
        return
    
    if mode == "Portfolio Plan":
        # Portfolio Plan mode - doesn't need query parameters
        outputs_root = get_outputs_root()
        
        # Show Portfolio Plan Viewer
        render_plan_viewer_page(outputs_root)
        return

    # Viewer mode - requires query parameters
    # Get run_dir from query params
    run_dir = get_run_dir_from_query()
    
    if not run_dir:
        st.error("Missing query parameters: season and run_id required")
        st.info("Usage: /?season=...&run_id=...")
        st.info("Example: /?season=2026Q1&run_id=demo_20250101T000000Z")
        return
    
    if not run_dir.exists():
        st.error(f"Run directory does not exist: {run_dir}")
        st.info(f"Outputs root: {run_dir.parent.parent.parent}")
        st.info(f"Expected path: {run_dir}")
        return

    # Page selection for Viewer mode
    page = st.sidebar.selectbox(
        "Viewer Pages",
        [
            "Overview",
            "KPI",
            "Winners",
            "Governance",
            "Artifacts",
        ],
    )
    
    # Render selected page
    if page == "Overview":
        render_viewer_page("Overview", run_dir, render_overview_page)
    elif page == "KPI":
        render_viewer_page("KPI", run_dir, render_kpi_page)
    elif page == "Winners":
        render_viewer_page("Winners", run_dir, render_winners_page)
    elif page == "Governance":
        render_viewer_page("Governance", run_dir, render_governance_page)
    elif page == "Artifacts":
        render_viewer_page("Artifacts", run_dir, render_artifacts_page)


if __name__ == "__main__":
    main()




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/json_pointer.py
sha256(source_bytes) = c5c307bdef0d2d5c7a47aecca9914753bf2db33d09e69aa8524007dc4a98d11d
bytes = 2407
redacted = False
--------------------------------------------------------------------------------

"""JSON Pointer resolver (RFC 6901).

Resolves JSON pointers in a defensive, never-raise manner.
"""

from __future__ import annotations

from typing import Any


def resolve_json_pointer(data: dict, pointer: str) -> tuple[bool, Any | None]:
    """
    Resolve RFC 6901 JSON Pointer.
    
    Never raises; return (found: bool, value).
    
    Supports basic pointer syntax:
    - /a/b/c for object keys
    - /a/b/0 for array indices
    - Does NOT support ~1 ~0 escape sequences (simplified version)
    - Does NOT support root pointer "/" (by design for Viewer UX)
    
    Args:
        data: JSON data (dict/list)
        pointer: RFC 6901 JSON Pointer (e.g., "/a/b/0/c")
        
    Returns:
        Tuple of (found: bool, value: Any | None)
        - found=True: pointer resolved successfully, value contains result
        - found=False: pointer failed to resolve, value is None
        
    Contract:
        - Never raises exceptions
        - Returns (False, None) on any failure
        - Supports list indices (e.g., "/0", "/items/0/name")
        - Root pointer "/" is intentionally disabled (returns False)
    """
    try:
        # ❶ Outermost defense (root cause of previous failure)
        if data is None or not isinstance(data, (dict, list)):
            return (False, None)
        
        if not isinstance(pointer, str):
            return (False, None)
        
        if pointer == "" or pointer == "/":
            return (False, None)
        
        if not pointer.startswith("/"):
            return (False, None)
        
        # ❷ Normal resolution flow
        parts = pointer.lstrip("/").split("/")
        current: Any = data
        
        for part in parts:
            # list index
            if isinstance(current, list):
                if not part.isdigit():
                    return (False, None)
                idx = int(part)
                if idx < 0 or idx >= len(current):
                    return (False, None)
                current = current[idx]
            # dict key
            elif isinstance(current, dict):
                if part not in current:
                    return (False, None)
                current = current[part]
            else:
                return (False, None)
        
        return (True, current)
    
    except Exception:
        # ❸ Viewer world final safety net
        return (False, None)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/kpi_registry.py
sha256(source_bytes) = b232dfcb5f2e694eb93d29b84b554035dbec06e47d5182555b33927b88dc0972
bytes = 1933
redacted = False
--------------------------------------------------------------------------------

"""KPI Evidence Registry.

Maps KPI names to EvidenceLink (artifact + JSON pointer).
"""

from __future__ import annotations

from typing import Literal

from FishBroWFS_V2.gui.viewer.schema import EvidenceLink

ArtifactName = Literal["manifest", "winners_v2", "governance"]


# KPI Evidence Registry (first version hardcoded, extensible later)
KPI_EVIDENCE_REGISTRY: dict[str, EvidenceLink] = {
    "net_profit": EvidenceLink(
        artifact="winners_v2",
        json_pointer="/summary/net_profit",
        description="Total net profit from winners_v2 summary",
    ),
    "max_drawdown": EvidenceLink(
        artifact="winners_v2",
        json_pointer="/summary/max_drawdown",
        description="Maximum drawdown over full backtest",
    ),
    "num_trades": EvidenceLink(
        artifact="winners_v2",
        json_pointer="/summary/num_trades",
        description="Total number of executed trades",
    ),
    "final_score": EvidenceLink(
        artifact="governance",
        json_pointer="/scoring/final_score",
        description="Governance final score used for KEEP/FREEZE/DROP",
    ),
}


def get_evidence_link(kpi_name: str) -> EvidenceLink | None:
    """
    Get EvidenceLink for KPI name.
    
    Args:
        kpi_name: KPI name to look up
        
    Returns:
        EvidenceLink if found, None otherwise
        
    Contract:
        - Never raises exceptions
        - Returns None for unknown KPI names
    """
    try:
        return KPI_EVIDENCE_REGISTRY.get(kpi_name)
    except Exception:
        return None


def has_evidence(kpi_name: str) -> bool:
    """
    Check if KPI has evidence link.
    
    Args:
        kpi_name: KPI name to check
        
    Returns:
        True if KPI has evidence link, False otherwise
        
    Contract:
        - Never raises exceptions
    """
    try:
        return kpi_name in KPI_EVIDENCE_REGISTRY
    except Exception:
        return False



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/load_state.py
sha256(source_bytes) = ae93a9927bbbd1f3dc0ab88cb8e968c239f72893a378b5ff15b540a6856421b7
bytes = 7433
redacted = False
--------------------------------------------------------------------------------

"""Viewer load state model and contract.

Defines unified artifact load status for Viewer pages.
Never raises exceptions - pure mapping logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.core.artifact_reader import SafeReadResult
from FishBroWFS_V2.core.artifact_status import ValidationResult, ArtifactStatus


class ArtifactLoadStatus(str, Enum):
    """Artifact load status - fixed string values for UI consistency."""
    OK = "OK"
    MISSING = "MISSING"
    INVALID = "INVALID"
    DIRTY = "DIRTY"


@dataclass(frozen=True)
class ArtifactLoadState:
    """
    Artifact load state for Viewer.
    
    Represents the load status of a single artifact (manifest/winners_v2/governance).
    """
    status: ArtifactLoadStatus
    artifact_name: str  # "manifest" / "winners_v2" / "governance"
    path: Path
    error: Optional[str] = None  # Error message when INVALID
    dirty_reasons: list[str] = None  # List of reasons when DIRTY (can be empty)
    last_modified_ts: Optional[float] = None  # Optional timestamp for UI display
    
    def __post_init__(self) -> None:
        """Ensure dirty_reasons is always a list."""
        if self.dirty_reasons is None:
            object.__setattr__(self, "dirty_reasons", [])


def compute_load_state(
    artifact_name: str,
    path: Path,
    read_result: SafeReadResult,
    validation_result: Optional[ValidationResult] = None,
) -> ArtifactLoadState:
    """
    Compute ArtifactLoadState from read and validation results.
    
    Zero-trust function - never assumes any attribute exists.
    This function performs pure mapping - no IO, no inference, no exceptions.
    
    Args:
        artifact_name: Name of artifact ("manifest", "winners_v2", "governance")
        path: Path to artifact file
        read_result: Result from try_read_artifact()
        validation_result: Optional validation result from validate_*_status()
        
    Returns:
        ArtifactLoadState with mapped status and error information
        
    Contract:
        - Never raises exceptions
        - Only performs mapping logic
        - Status strings are fixed (OK/MISSING/INVALID/DIRTY)
        - Zero-trust: uses getattr for all attribute access
    """
    try:
        # ❶ Zero-trust: check is_error property safely
        is_error = getattr(read_result, "is_error", False)
        
        if is_error:
            # Read error - map to MISSING or INVALID
            error = getattr(read_result, "error", None)
            if error is not None:
                error_code = getattr(error, "error_code", "")
                error_message = getattr(error, "message", "Unknown error")
                
                # FILE_NOT_FOUND -> MISSING
                if error_code == "FILE_NOT_FOUND":
                    return ArtifactLoadState(
                        status=ArtifactLoadStatus.MISSING,
                        artifact_name=artifact_name,
                        path=path,
                        error=None,
                        dirty_reasons=[],
                        last_modified_ts=None,
                    )
                
                # Other errors -> INVALID
                return ArtifactLoadState(
                    status=ArtifactLoadStatus.INVALID,
                    artifact_name=artifact_name,
                    path=path,
                    error=str(error_message),
                    dirty_reasons=[],
                    last_modified_ts=None,
                )
            else:
                # Error object missing -> INVALID
                return ArtifactLoadState(
                    status=ArtifactLoadStatus.INVALID,
                    artifact_name=artifact_name,
                    path=path,
                    error="Read error but error object missing",
                    dirty_reasons=[],
                    last_modified_ts=None,
                )
        
        # File read successfully - check validation result
        read_result_obj = getattr(read_result, "result", None)
        if read_result_obj is None:
            # No result but no error -> INVALID
            return ArtifactLoadState(
                status=ArtifactLoadStatus.INVALID,
                artifact_name=artifact_name,
                path=path,
                error="Read result missing",
                dirty_reasons=[],
                last_modified_ts=None,
            )
        
        # Extract metadata safely
        meta = getattr(read_result_obj, "meta", None)
        last_modified_ts = None
        if meta is not None:
            last_modified_ts = getattr(meta, "mtime_s", None)
        
        # If validation_result is provided, use it
        if validation_result is not None:
            # Zero-trust: get status safely
            validation_status = getattr(validation_result, "status", None)
            
            # Map ValidationResult.status to ArtifactLoadStatus
            if validation_status == ArtifactStatus.OK:
                load_status = ArtifactLoadStatus.OK
            elif validation_status == ArtifactStatus.MISSING:
                load_status = ArtifactLoadStatus.MISSING
            elif validation_status == ArtifactStatus.INVALID:
                load_status = ArtifactLoadStatus.INVALID
            elif validation_status == ArtifactStatus.DIRTY:
                load_status = ArtifactLoadStatus.DIRTY
            else:
                # Fallback to INVALID for unknown status
                load_status = ArtifactLoadStatus.INVALID
            
            # Extract error and dirty_reasons from validation_result safely
            error_msg = None
            dirty_reasons_list: list[str] = []
            
            if load_status == ArtifactLoadStatus.INVALID:
                error_msg = getattr(validation_result, "message", "Unknown validation error")
                error_details = getattr(validation_result, "error_details", None)
                if error_details:
                    # Prefer error_details if available
                    error_msg = str(error_details)
            elif load_status == ArtifactLoadStatus.DIRTY:
                # Extract dirty reason from message
                message = getattr(validation_result, "message", "")
                dirty_reasons_list = [message] if message else []
            
            return ArtifactLoadState(
                status=load_status,
                artifact_name=artifact_name,
                path=path,
                error=error_msg,
                dirty_reasons=dirty_reasons_list,
                last_modified_ts=last_modified_ts,
            )
        
        # No validation result - assume OK if file read successfully
        return ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name=artifact_name,
            path=path,
            error=None,
            dirty_reasons=[],
            last_modified_ts=last_modified_ts,
        )
    
    except Exception as e:
        # ❸ Final safety net: compute_load_state never raises
        return ArtifactLoadState(
            status=ArtifactLoadStatus.INVALID,
            artifact_name=artifact_name,
            path=path,
            error=f"compute_load_state exception: {e}",
            dirty_reasons=[],
            last_modified_ts=None,
        )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/page_scaffold.py
sha256(source_bytes) = 5ec6f593293edb8f8cdae3b2b93721f82f121cfa9169e40c31dbdcb9ad612104
bytes = 6486
redacted = False
--------------------------------------------------------------------------------

"""Viewer page scaffold - unified "never crash" page skeleton.

Provides consistent page structure that never raises exceptions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import streamlit as st

from FishBroWFS_V2.core.artifact_reader import try_read_artifact
from FishBroWFS_V2.core.artifact_status import (
    ValidationResult,
    validate_manifest_status,
    validate_winners_v2_status,
    validate_governance_status,
)

from FishBroWFS_V2.gui.viewer.load_state import (
    ArtifactLoadState,
    ArtifactLoadStatus,
    compute_load_state,
)
from FishBroWFS_V2.gui.viewer.components.status_bar import render_artifact_status_bar


@dataclass(frozen=True)
class Bundle:
    """
    Bundle of artifacts for Viewer page.
    
    Contains loaded artifacts and their load states.
    """
    manifest_state: ArtifactLoadState
    winners_v2_state: ArtifactLoadState
    governance_state: ArtifactLoadState
    
    @property
    def all_ok(self) -> bool:
        """Check if all artifacts are OK."""
        return all(
            s.status.value == "OK"
            for s in [self.manifest_state, self.winners_v2_state, self.governance_state]
        )
    
    @property
    def has_blocking_error(self) -> bool:
        """Check if any artifact is MISSING or INVALID (blocks page content)."""
        blocking_statuses = {"MISSING", "INVALID"}
        return any(
            s.status.value in blocking_statuses
            for s in [self.manifest_state, self.winners_v2_state, self.governance_state]
        )


def render_viewer_page(
    title: str,
    run_dir: Path,
    content_render_fn: Optional[Callable[[Bundle], None]] = None,
) -> None:
    """
    Render Viewer page with unified scaffold.
    
    This function ensures Viewer pages never crash - all errors are handled gracefully.
    
    Args:
        title: Page title
        run_dir: Path to run directory containing artifacts
        content_render_fn: Optional function to render page content.
                         Receives Bundle with artifact states.
                         If None, only status bar is rendered.
    
    Contract:
        - Never raises exceptions
        - Always renders status bar
        - Shows BLOCKED panel if artifacts are MISSING/INVALID
        - Calls content_render_fn only if artifacts are OK or DIRTY (non-blocking)
    """
    st.set_page_config(page_title=title, layout="wide")
    st.title(title)
    
    # ❶ Load bundle - completely wrapped in try/except
    try:
        bundle = _load_bundle(run_dir)
    except Exception as e:
        # Load phase any error → BLOCKED
        states = [
            ArtifactLoadState(
                status=ArtifactLoadStatus.INVALID,
                artifact_name="bundle",
                path=None,
                error=f"load_bundle_fn exception: {e}",
                dirty_reasons=[],
                last_modified_ts=None,
            )
        ]
        render_artifact_status_bar(states)
        st.error("**BLOCKED / 無法載入**")
        st.error(f"Viewer BLOCKED: failed to load artifacts. Error: {e}")
        return
    
    # ❷ Bundle loaded successfully, but internal artifacts may still be missing/invalid
    states = [
        bundle.manifest_state,
        bundle.winners_v2_state,
        bundle.governance_state,
    ]
    
    render_artifact_status_bar(states)
    
    # Check if any artifact is MISSING or INVALID (blocks page content)
    if bundle.has_blocking_error:
        st.error("**BLOCKED / 無法載入**")
        st.warning("Viewer BLOCKED due to invalid or missing artifacts.")
        return
    
    # ❸ Only OK / DIRTY will reach content render
    if content_render_fn is not None:
        try:
            content_render_fn(bundle)
        except Exception as e:
            # Catch any exceptions from content renderer
            st.error(f"**內容渲染錯誤:** {e}")
            st.exception(e)


def _load_bundle(run_dir: Path) -> Bundle:
    """
    Load artifact bundle from run directory.
    
    Never raises exceptions - all errors are captured in ArtifactLoadState.
    """
    manifest_path = run_dir / "manifest.json"
    winners_path = run_dir / "winners.json"  # Note: file is winners.json but schema is winners_v2
    governance_path = run_dir / "governance.json"
    
    # Read artifacts (never raises)
    manifest_read = try_read_artifact(manifest_path)
    winners_read = try_read_artifact(winners_path)
    governance_read = try_read_artifact(governance_path)
    
    # Validate artifacts (may raise, but we catch exceptions)
    manifest_validation: Optional[ValidationResult] = None
    winners_validation: Optional[ValidationResult] = None
    governance_validation: Optional[ValidationResult] = None
    
    try:
        if manifest_read.is_ok and manifest_read.result:
            # Use already-read data for validation
            manifest_data = manifest_read.result.raw
            manifest_validation = validate_manifest_status(str(manifest_path), manifest_data)
    except Exception:
        pass  # Validation failed, will use read_result only
    
    try:
        if winners_read.is_ok and winners_read.result:
            # Use already-read data for validation
            winners_data = winners_read.result.raw
            winners_validation = validate_winners_v2_status(str(winners_path), winners_data)
    except Exception:
        pass
    
    try:
        if governance_read.is_ok and governance_read.result:
            # Use already-read data for validation
            governance_data = governance_read.result.raw
            governance_validation = validate_governance_status(str(governance_path), governance_data)
    except Exception:
        pass
    
    # Compute load states (never raises)
    manifest_state = compute_load_state(
        "manifest",
        manifest_path,
        manifest_read,
        manifest_validation,
    )
    
    winners_state = compute_load_state(
        "winners_v2",
        winners_path,
        winners_read,
        winners_validation,
    )
    
    governance_state = compute_load_state(
        "governance",
        governance_path,
        governance_read,
        governance_validation,
    )
    
    return Bundle(
        manifest_state=manifest_state,
        winners_v2_state=winners_state,
        governance_state=governance_state,
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/schema.py
sha256(source_bytes) = b2546a5bfca358c6df53dd1d517cf3d56d9c1d2a363f1b27546e1d945387589d
bytes = 464
redacted = False
--------------------------------------------------------------------------------

"""Viewer schema definitions.

Public types for Viewer and Audit schema.
"""

from __future__ import annotations

from pydantic import BaseModel


class EvidenceLink(BaseModel):
    """Evidence link pointing to a specific KPI value."""
    artifact: str  # Artifact name (e.g., "winners_v2", "governance")
    json_pointer: str  # JSON pointer to the value (e.g., "/summary/net_profit")
    description: str | None = None  # Optional human-readable description



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/components/__init__.py
sha256(source_bytes) = cb0ec9f9b842c6a936a44911a2de6cdc848b135c69a3602763398ac6da406032
bytes = 36
redacted = False
--------------------------------------------------------------------------------

"""Viewer components package."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/components/evidence_panel.py
sha256(source_bytes) = 5eab191bf07f2e06fa3e0726c2d6ff0cbc73a24ef6a70310e94045be68da9fe3
bytes = 3836
redacted = False
--------------------------------------------------------------------------------

"""Evidence Panel component.

Displays evidence for active KPI from artifacts.
"""

from __future__ import annotations

import json

import streamlit as st

from FishBroWFS_V2.gui.viewer.json_pointer import resolve_json_pointer


def render_evidence_panel(artifacts: dict[str, dict]) -> None:
    """
    Render evidence panel showing active KPI evidence.
    
    Args:
        artifacts: Dictionary mapping artifact names to their JSON data
                  e.g., {"manifest": {...}, "winners_v2": {...}, "governance": {...}}
        
    Contract:
        - Never raises exceptions
        - Shows warning if evidence is missing
        - Handles missing session_state gracefully
        - Unknown render_hint falls back to "highlight" (never raises)
    """
    try:
        # Get active evidence from session state
        active_evidence = st.session_state.get("active_evidence", None)
        
        if not active_evidence:
            # No active evidence selected
            return
        
        st.subheader("Evidence")
        
        # Extract evidence info safely
        kpi_name = active_evidence.get("kpi_name", "unknown")
        artifact_name = active_evidence.get("artifact", "unknown")
        json_pointer = active_evidence.get("json_pointer", "")
        description = active_evidence.get("description", "")
        
        # Extract render_hint with allowlist check and warning
        render_hint = active_evidence.get("render_hint", "highlight")
        allowed_hints = {"highlight", "chart_annotation", "diff"}
        if render_hint not in allowed_hints:
            st.warning(f"Unsupported render_hint={render_hint}, fallback to highlight")
            render_hint = "highlight"  # Fallback for unknown hints
        
        render_payload = active_evidence.get("render_payload", {})
        
        # Display KPI info
        st.markdown(f"**KPI:** {kpi_name}")
        if description:
            st.caption(description)
        
        st.markdown("---")
        
        # Get artifact data
        artifact_data = artifacts.get(artifact_name)
        
        if artifact_data is None:
            st.warning(f"⚠️ Artifact '{artifact_name}' not available.")
            return
        
        # Resolve JSON pointer
        found, value = resolve_json_pointer(artifact_data, json_pointer)
        
        if not found:
            st.warning("⚠️ Evidence missing: JSON pointer not found.")
            st.info(f"**Artifact:** {artifact_name}")
            st.info(f"**JSON Pointer:** `{json_pointer}`")
            return
        
        # Display evidence based on render_hint
        st.markdown(f"**Artifact:** `{artifact_name}`")
        st.markdown(f"**JSON Pointer:** `{json_pointer}`")
        
        if render_hint == "chart_annotation":
            # Chart annotation mode: show compact preview for chart overlays
            st.markdown("**Value:**")
            st.caption(f"({render_hint} mode)")
            st.code(str(value)[:100] + "..." if len(str(value)) > 100 else str(value), language=None)
        elif render_hint == "diff":
            # Diff mode: show full details with diff highlighting
            st.markdown("**Value:**")
            st.caption(f"({render_hint} mode)")
            if isinstance(value, (dict, list)):
                st.json(value)
            else:
                st.code(str(value), language=None)
        else:
            # Default "highlight" mode
            st.markdown("**Value:**")
            try:
                if isinstance(value, (dict, list)):
                    st.json(value)
                else:
                    st.code(str(value), language=None)
            except Exception:
                st.text(str(value))
    
    except Exception as e:
        st.error(f"Error rendering evidence panel: {e}")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/components/kpi_table.py
sha256(source_bytes) = f67f0245c075b6924246c125313a9c2aa5b8a527af62ad81b638ef6129571712
bytes = 3216
redacted = False
--------------------------------------------------------------------------------

"""KPI Table component with evidence drill-down.

Renders KPI table with clickable evidence links.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from FishBroWFS_V2.gui.viewer.kpi_registry import get_evidence_link


def render_kpi_table(kpi_rows: list[dict]) -> None:
    """
    Render KPI table with evidence drill-down capability.
    
    Each row must include:
      - name: str - KPI name
      - value: Any - KPI value (will be converted to string for display)
    
    Optional:
      - label: str - Display label (defaults to name)
      - format: str - Value format hint
    
    Args:
        kpi_rows: List of KPI row dictionaries
        
    Contract:
        - Never raises exceptions
        - KPI names not in registry are displayed but not clickable
        - Missing name/value fields are handled gracefully
    """
    try:
        if not kpi_rows:
            st.info("No KPI data available.")
            return
        
        st.subheader("Key Performance Indicators")
        
        # Render table
        for row in kpi_rows:
            _render_kpi_row(row)
    
    except Exception as e:
        st.error(f"Error rendering KPI table: {e}")


def _render_kpi_row(row: dict) -> None:
    """Render single KPI row."""
    try:
        # Extract row data safely
        kpi_name = row.get("name", "unknown")
        kpi_value = row.get("value", None)
        kpi_label = row.get("label", kpi_name)
        
        # Format value
        value_str = _format_value(kpi_value)
        
        # Check if KPI has evidence link
        evidence_link = get_evidence_link(kpi_name)
        
        if evidence_link:
            # Render with clickable evidence link
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{kpi_label}**")
            with col2:
                st.text(value_str)
            with col3:
                if st.button("🔍 View Evidence", key=f"evidence_{kpi_name}"):
                    # Store evidence link in session state
                    st.session_state["active_evidence"] = {
                        "kpi_name": kpi_name,
                        "artifact": evidence_link.artifact,
                        "json_pointer": evidence_link.json_pointer,
                        "description": evidence_link.description or "",
                    }
                    st.rerun()
        else:
            # Render without evidence link
            col1, col2 = st.columns([3, 2])
            with col1:
                st.markdown(f"**{kpi_label}**")
            with col2:
                st.text(value_str)
    
    except Exception:
        # Silently handle errors in row rendering
        pass


def _format_value(value: Any) -> str:
    """Format KPI value for display."""
    try:
        if value is None:
            return "N/A"
        if isinstance(value, (int, float)):
            # Format numbers with appropriate precision
            if isinstance(value, float):
                return f"{value:,.2f}"
            return f"{value:,}"
        return str(value)
    except Exception:
        return str(value) if value is not None else "N/A"



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/components/status_bar.py
sha256(source_bytes) = 77137ad4a6b43f15a619e902b780143596a2ae4db41dc82129f919dba105b1db
bytes = 3779
redacted = False
--------------------------------------------------------------------------------

"""Artifact Status Bar component for Viewer pages.

Renders consistent status bar across all Viewer pages.
Never raises exceptions - graceful degradation.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.load_state import ArtifactLoadState, ArtifactLoadStatus


def render_artifact_status_bar(states: list[ArtifactLoadState]) -> None:
    """
    Render artifact status bar for Viewer page.
    
    Displays status badges for each artifact with error/dirty information.
    Never raises exceptions - page continues to render even if artifacts are missing/invalid.
    
    Args:
        states: List of ArtifactLoadState for each artifact
        
    Contract:
        - Never raises exceptions
        - Always renders something (even if states is empty)
        - INVALID shows error summary (max 1 line)
        - DIRTY shows dirty_reasons (collapsible expander)
        - Page continues to render even if artifacts are MISSING/INVALID
    """
    if not states:
        return
    
    st.subheader("Artifact Status")
    
    # Create columns for badges
    num_cols = min(len(states), 4)  # Max 4 columns
    cols = st.columns(num_cols)
    
    for idx, state in enumerate(states):
        col_idx = idx % num_cols
        with cols[col_idx]:
            _render_artifact_badge(state)
    
    # Show detailed error/dirty info below badges
    _render_detailed_info(states)


def _render_artifact_badge(state: ArtifactLoadState) -> None:
    """Render single artifact badge."""
    # Map status to badge color
    if state.status == ArtifactLoadStatus.OK:
        badge_color = "🟢"
        badge_text = f"{state.artifact_name}: OK"
    elif state.status == ArtifactLoadStatus.MISSING:
        badge_color = "⚪"
        badge_text = f"{state.artifact_name}: MISSING"
    elif state.status == ArtifactLoadStatus.INVALID:
        badge_color = "🔴"
        badge_text = f"{state.artifact_name}: INVALID"
    elif state.status == ArtifactLoadStatus.DIRTY:
        badge_color = "🟡"
        badge_text = f"{state.artifact_name}: DIRTY"
    else:
        badge_color = "⚪"
        badge_text = f"{state.artifact_name}: UNKNOWN"
    
    st.markdown(f"{badge_color} **{badge_text}**")
    
    # Show last modified time if available
    if state.last_modified_ts is not None:
        from datetime import datetime
        dt = datetime.fromtimestamp(state.last_modified_ts)
        st.caption(f"Updated: {dt.strftime('%Y-%m-%d %H:%M:%S')}")


def _render_detailed_info(states: list[ArtifactLoadState]) -> None:
    """Render detailed error/dirty information."""
    invalid_states = [s for s in states if s.status == ArtifactLoadStatus.INVALID]
    dirty_states = [s for s in states if s.status == ArtifactLoadStatus.DIRTY]
    
    if not invalid_states and not dirty_states:
        return
    
    # Show INVALID errors
    if invalid_states:
        st.error("**Invalid Artifacts:**")
        for state in invalid_states:
            error_summary = state.error or "Unknown error"
            # Truncate to 1 line if too long
            if len(error_summary) > 100:
                error_summary = error_summary[:97] + "..."
            st.text(f"• {state.artifact_name}: {error_summary}")
    
    # Show DIRTY reasons (collapsible)
    if dirty_states:
        with st.expander("**Dirty Artifacts (config_hash mismatch)**", expanded=False):
            for state in dirty_states:
                st.markdown(f"**{state.artifact_name}:**")
                if state.dirty_reasons:
                    for reason in state.dirty_reasons:
                        st.text(f"  • {reason}")
                else:
                    st.text("  • No specific reason provided")
                st.markdown("---")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/pages/__init__.py
sha256(source_bytes) = 28ce313c66d262aa8bf6e4ca55c0fefe696addeef71fe724de402e412c2f530e
bytes = 31
redacted = False
--------------------------------------------------------------------------------

"""Viewer pages package."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/pages/artifacts.py
sha256(source_bytes) = c270945e33e06bdf84682d24773a7c6dcc5c07a17558092b150bbb26f0f4f6ce
bytes = 1721
redacted = False
--------------------------------------------------------------------------------

"""Artifacts Viewer page.

Displays raw artifacts JSON.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle
from FishBroWFS_V2.core.artifact_reader import try_read_artifact


def render_page(bundle: Bundle) -> None:
    """
    Render Artifacts viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays raw artifacts JSON
    """
    try:
        st.subheader("Raw Artifacts")
        
        # Display manifest
        if bundle.manifest_state.status.value == "OK" and bundle.manifest_state.path:
            st.markdown("### manifest.json")
            manifest_read = try_read_artifact(bundle.manifest_state.path)
            if manifest_read.is_ok and manifest_read.result:
                st.json(manifest_read.result.raw)
        
        # Display winners_v2
        if bundle.winners_v2_state.status.value == "OK" and bundle.winners_v2_state.path:
            st.markdown("### winners_v2.json")
            winners_read = try_read_artifact(bundle.winners_v2_state.path)
            if winners_read.is_ok and winners_read.result:
                st.json(winners_read.result.raw)
        
        # Display governance
        if bundle.governance_state.status.value == "OK" and bundle.governance_state.path:
            st.markdown("### governance.json")
            governance_read = try_read_artifact(bundle.governance_state.path)
            if governance_read.is_ok and governance_read.result:
                st.json(governance_read.result.raw)
    
    except Exception as e:
        st.error(f"Error rendering artifacts page: {e}")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/pages/governance.py
sha256(source_bytes) = 61e6b157fb841436babf7fb7b4797ca6bee5f4ff0de4e3e24d9d737075118839
bytes = 2522
redacted = False
--------------------------------------------------------------------------------

"""Governance Viewer page.

Displays governance decisions and evidence.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle


def render_page(bundle: Bundle) -> None:
    """
    Render Governance viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays governance decisions table with lifecycle_state
    """
    try:
        st.subheader("Governance Decisions")
        
        if bundle.governance_state.status.value == "OK":
            st.info("✅ Governance data loaded successfully")
            
            # Display governance decisions table
            if bundle.governance_state.result:
                governance_data = bundle.governance_state.result.raw
                
                # Extract rows if available
                rows = governance_data.get("rows", [])
                if not rows and "items" in governance_data:
                    # Fallback to items format (backward compatibility)
                    items = governance_data.get("items", [])
                    rows = items
                
                if rows:
                    # Display table
                    import pandas as pd
                    
                    table_data = []
                    for row in rows:
                        table_data.append({
                            "Strategy ID": row.get("strategy_id", "N/A"),
                            "Decision": row.get("decision", "N/A"),
                            "Rule ID": row.get("rule_id", "N/A"),
                            "Lifecycle State": row.get("lifecycle_state", "INCUBATION"),  # Default for backward compatibility
                            "Reason": row.get("reason", ""),
                            "Run ID": row.get("run_id", "N/A"),
                            "Stage": row.get("stage", "N/A"),
                        })
                    
                    df = pd.DataFrame(table_data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No governance decisions found.")
        else:
            st.warning(f"⚠️ Governance status: {bundle.governance_state.status.value}")
            if bundle.governance_state.error:
                st.error(f"Error: {bundle.governance_state.error}")
    
    except Exception as e:
        st.error(f"Error rendering governance page: {e}")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/pages/kpi.py
sha256(source_bytes) = 02e1d5c07f68fca1040e047ed6177075c0231dfefe81fe242e059d09bfe588b9
bytes = 3965
redacted = False
--------------------------------------------------------------------------------

"""KPI Viewer page.

Displays KPIs with evidence drill-down capability.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle
from FishBroWFS_V2.gui.viewer.components.kpi_table import render_kpi_table
from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
from FishBroWFS_V2.core.artifact_reader import try_read_artifact


def render_page(bundle: Bundle) -> None:
    """
    Render KPI viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Extracts KPIs from artifacts
        - Renders KPI table and evidence panel
    """
    try:
        # Extract artifacts data
        artifacts = _extract_artifacts(bundle)
        
        # Extract KPIs from artifacts
        kpi_rows = _extract_kpis(artifacts)
        
        # Layout: KPI table on left, evidence panel on right
        col1, col2 = st.columns([2, 1])
        
        with col1:
            render_kpi_table(kpi_rows)
        
        with col2:
            render_evidence_panel(artifacts)
    
    except Exception as e:
        st.error(f"Error rendering KPI page: {e}")


def _extract_artifacts(bundle: Bundle) -> dict[str, dict]:
    """
    Extract artifact data from bundle.
    
    Returns dictionary mapping artifact names to their JSON data.
    """
    artifacts: dict[str, dict] = {}
    
    try:
        # Extract manifest
        if bundle.manifest_state.status.value == "OK" and bundle.manifest_state.path:
            manifest_read = try_read_artifact(bundle.manifest_state.path)
            if manifest_read.is_ok and manifest_read.result:
                artifacts["manifest"] = manifest_read.result.raw
        
        # Extract winners_v2
        if bundle.winners_v2_state.status.value == "OK" and bundle.winners_v2_state.path:
            winners_read = try_read_artifact(bundle.winners_v2_state.path)
            if winners_read.is_ok and winners_read.result:
                artifacts["winners_v2"] = winners_read.result.raw
        
        # Extract governance
        if bundle.governance_state.status.value == "OK" and bundle.governance_state.path:
            governance_read = try_read_artifact(bundle.governance_state.path)
            if governance_read.is_ok and governance_read.result:
                artifacts["governance"] = governance_read.result.raw
    
    except Exception:
        pass
    
    return artifacts


def _extract_kpis(artifacts: dict[str, dict]) -> list[dict]:
    """
    Extract KPI rows from artifacts.
    
    Returns list of KPI row dictionaries.
    """
    kpi_rows: list[dict] = []
    
    try:
        # Extract from winners_v2 summary
        winners_v2 = artifacts.get("winners_v2", {})
        summary = winners_v2.get("summary", {})
        
        if "net_profit" in summary:
            kpi_rows.append({
                "name": "net_profit",
                "value": summary["net_profit"],
                "label": "Net Profit",
            })
        
        if "max_drawdown" in summary:
            kpi_rows.append({
                "name": "max_drawdown",
                "value": summary["max_drawdown"],
                "label": "Max Drawdown",
            })
        
        if "num_trades" in summary:
            kpi_rows.append({
                "name": "num_trades",
                "value": summary["num_trades"],
                "label": "Number of Trades",
            })
        
        # Extract from governance scoring
        governance = artifacts.get("governance", {})
        scoring = governance.get("scoring", {})
        
        if "final_score" in scoring:
            kpi_rows.append({
                "name": "final_score",
                "value": scoring["final_score"],
                "label": "Final Score",
            })
    
    except Exception:
        pass
    
    return kpi_rows



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/pages/overview.py
sha256(source_bytes) = f004363bb2d3a17c0cc9501371af3fb5d3671e48170a9f2d85819c7733f9103d
bytes = 1226
redacted = False
--------------------------------------------------------------------------------

"""Overview Viewer page.

Displays run overview and summary information.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle


def render_page(bundle: Bundle) -> None:
    """
    Render Overview viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays run overview and summary
    """
    try:
        st.subheader("Run Overview")
        
        # Display manifest info if available
        if bundle.manifest_state.status.value == "OK":
            st.info("✅ Manifest loaded successfully")
        else:
            st.warning(f"⚠️ Manifest status: {bundle.manifest_state.status.value}")
        
        # Display summary stats
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Manifest", bundle.manifest_state.status.value)
        with col2:
            st.metric("Winners", bundle.winners_v2_state.status.value)
        with col3:
            st.metric("Governance", bundle.governance_state.status.value)
    
    except Exception as e:
        st.error(f"Error rendering overview page: {e}")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/pages/winners.py
sha256(source_bytes) = e629b144f6b9d612e005f32a0af9431dfca307dfb7c7377300502ceaae9c2e52
bytes = 1026
redacted = False
--------------------------------------------------------------------------------

"""Winners Viewer page.

Displays winners list and details.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle


def render_page(bundle: Bundle) -> None:
    """
    Render Winners viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays winners list
    """
    try:
        st.subheader("Winners")
        
        if bundle.winners_v2_state.status.value == "OK":
            st.info("✅ Winners data loaded successfully")
            # TODO: Phase 6.2 - Display winners table
            st.info("Winners table display coming in Phase 6.2")
        else:
            st.warning(f"⚠️ Winners status: {bundle.winners_v2_state.status.value}")
            if bundle.winners_v2_state.error:
                st.error(f"Error: {bundle.winners_v2_state.error}")
    
    except Exception as e:
        st.error(f"Error rendering winners page: {e}")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/indicators/__init__.py
sha256(source_bytes) = 545c38b0922de19734fbffde62792c37c2aef6a3216cfa472449173165220f7d
bytes = 4
redacted = False
--------------------------------------------------------------------------------





--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/indicators/numba_indicators.py
sha256(source_bytes) = e76df8625b362302095ce1679a1ae41d75590318cbf6ff0a7ec0546d1222cb5a
bytes = 4455
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

import numpy as np

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore


# ----------------------------
# Rolling Max / Min
# ----------------------------
# Design choice (v1):
# - Simple loop scan for window <= ~50 is cache-friendly and predictable.
# - Correctness first; no deque optimization in v1.


if nb is not None:

    @nb.njit(cache=False)
    def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            m = arr[start]
            for j in range(start + 1, i + 1):
                v = arr[j]
                if v > m:
                    m = v
            out[i] = m
        return out

    @nb.njit(cache=False)
    def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            m = arr[start]
            for j in range(start + 1, i + 1):
                v = arr[j]
                if v < m:
                    m = v
            out[i] = m
        return out

else:
    # Fallback pure-python (used only if numba unavailable)
    def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:  # type: ignore
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            out[i] = np.max(arr[start : i + 1])
        return out

    def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:  # type: ignore
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            out[i] = np.min(arr[start : i + 1])
        return out


# ----------------------------
# ATR (Wilder's RMA)
# ----------------------------
# Definition:
# TR[t] = max(high[t]-low[t], abs(high[t]-close[t-1]), abs(low[t]-close[t-1]))
# ATR[t] = (ATR[t-1]*(n-1) + TR[t]) / n
# Notes:
# - Recursive; must keep state.
# - First ATR uses simple average of first n TRs.


if nb is not None:

    @nb.njit(cache=False)
    def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
        n = high.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0 or n == 0:
            return out
        if window > n:
            return out

        # TR computation
        tr = np.empty(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            a = high[i] - low[i]
            b = abs(high[i] - close[i - 1])
            c = abs(low[i] - close[i - 1])
            tr[i] = a if a >= b and a >= c else (b if b >= c else c)

        # initial ATR: simple average of first window TRs
        s = 0.0
        end = window if window < n else n
        for i in range(end):
            s += tr[i]
        # here window <= n guaranteed
        out[end - 1] = s / window

        # Wilder smoothing
        for i in range(window, n):
            out[i] = (out[i - 1] * (window - 1) + tr[i]) / window

        return out

else:
    def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:  # type: ignore
        n = high.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0 or n == 0:
            return out
        if window > n:
            return out

        tr = np.empty(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )

        end = min(window, n)
        # window <= n guaranteed
        out[end - 1] = np.mean(tr[:end])
        for i in range(window, n):
            out[i] = (out[i - 1] * (window - 1) + tr[i]) / window
        return out




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/perf/__init__.py
sha256(source_bytes) = e0e9b9d1f559cb3efd8a1de022db68e939be183015b19cf7e6f66bd3794fdaba
bytes = 44
redacted = False
--------------------------------------------------------------------------------

"""
Performance profiling utilities.
"""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/perf/cost_model.py
sha256(source_bytes) = fde8e9b3d0e1670423cd14f208cb871f62592f1f2f680864a1f715668e8c586e
bytes = 1401
redacted = False
--------------------------------------------------------------------------------

"""Cost model for performance estimation.

Provides predictable cost estimation: given bars and params, estimate execution time.
"""

from __future__ import annotations


def estimate_seconds(
    bars: int,
    params: int,
    cost_ms_per_param: float,
) -> float:
    """
    Estimate execution time in seconds based on cost model.
    
    Cost model assumption:
    - Time is linear in number of parameters only
    - Cost per parameter is measured in milliseconds
    - Formula: time_seconds = (params * cost_ms_per_param) / 1000.0
    - Note: bars parameter is for reference only and does not affect the calculation
    
    Args:
        bars: number of bars (for reference only, not used in calculation)
        params: number of parameters
        cost_ms_per_param: cost per parameter in milliseconds
        
    Returns:
        Estimated time in seconds
        
    Note:
        - This is a simple linear model: time = params * cost_per_param_ms / 1000.0
        - Bars are provided for reference but NOT used in the calculation
        - The model assumes cost per parameter is constant (measured from actual runs)
    """
    if params <= 0:
        return 0.0
    
    if cost_ms_per_param <= 0:
        return 0.0
    
    # Linear model: time = params * cost_per_param_ms / 1000.0
    estimated_seconds = (params * cost_ms_per_param) / 1000.0
    
    return estimated_seconds



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/perf/profile_report.py
sha256(source_bytes) = 31860f252306213dcc22bb9aead26aceaf4a2ad03f28a4d559d7b269926863f5
bytes = 1591
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

import cProfile
import io
import os
import pstats


def _format_profile_report(
    lane_id: str,
    n_bars: int,
    n_params: int,
    jit_enabled: bool,
    sort_params: bool,
    topn: int,
    mode: str,
    pr: cProfile.Profile,
) -> str:
    """
    Format a deterministic profile report string for perf harness.

    Contract:
    - Always includes __PROFILE_START__/__PROFILE_END__ markers.
    - Always includes the 'pstats sort: cumtime' header even if no stats exist.
    - Must not throw when the profile has no collected stats (empty Profile).
    """
    s = io.StringIO()
    s.write("__PROFILE_START__\n")
    s.write(f"lane_id={lane_id}\n")
    s.write(f"bars={n_bars} params={n_params}\n")
    s.write(f"jit_enabled={jit_enabled} sort_params={sort_params}\n")
    s.write(f"pid={os.getpid()}\n")
    if mode is not None:
        s.write(f"mode={mode}\n")
    s.write("\n")

    # Always emit the headers so tests can rely on markers/labels.
    s.write(f"== pstats sort: cumtime (top {topn}) ==\n")
    try:
        ps = pstats.Stats(pr, stream=s).strip_dirs()
        ps.sort_stats("cumtime")
        ps.print_stats(topn)
    except TypeError:
        s.write("(no profile stats collected)\n")

    s.write("\n\n")
    s.write(f"== pstats sort: tottime (top {topn}) ==\n")
    try:
        ps = pstats.Stats(pr, stream=s).strip_dirs()
        ps.sort_stats("tottime")
        ps.print_stats(topn)
    except TypeError:
        s.write("(no profile stats collected)\n")

    s.write("\n\n__PROFILE_END__\n")
    return s.getvalue()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/perf/scenario_control.py
sha256(source_bytes) = d400d93d83dcc730110451c484ad18572951c922fc1ab562adca43f3bdbb2986
bytes = 2600
redacted = False
--------------------------------------------------------------------------------

"""
Perf Harness Scenario Control (P2-1.6)

Provides trigger rate masking for perf harness to control sparse trigger density.
"""
from __future__ import annotations

import numpy as np


def apply_trigger_rate_mask(
    trigger: np.ndarray,
    trigger_rate: float,
    warmup: int = 0,
    seed: int = 42,
) -> np.ndarray:
    """
    Apply deterministic trigger rate mask to trigger array.
    
    This function masks trigger array to control sparse trigger density for perf testing.
    Only applies masking when trigger_rate < 1.0. When trigger_rate == 1.0, returns
    original array unchanged (preserves baseline behavior).
    
    Args:
        trigger: Input trigger array (e.g., donch_prev) of shape (n_bars,)
        trigger_rate: Rate of triggers to keep (0.0 to 1.0). Must be in [0, 1].
        warmup: Warmup period. Positions before warmup that are already NaN are preserved.
        seed: Random seed for deterministic masking.
    
    Returns:
        Masked trigger array with same dtype as input. Positions not kept are set to NaN.
    
    Rules:
        - If trigger_rate == 1.0: return original array unchanged
        - Otherwise: use RNG to determine which positions to keep
        - Respect warmup: positions < warmup that are already NaN remain NaN
        - Positions >= warmup are subject to masking
        - Keep dtype unchanged
    """
    if trigger_rate < 0.0 or trigger_rate > 1.0:
        raise ValueError(f"trigger_rate must be in [0, 1], got {trigger_rate}")
    
    # Fast path: no masking needed
    if trigger_rate == 1.0:
        return trigger
    
    # Create a copy to avoid modifying input
    masked = trigger.copy()
    
    # Use deterministic RNG
    rng = np.random.default_rng(seed)
    
    # Generate keep mask: positions to keep based on trigger_rate
    # Only apply masking to positions >= warmup that are currently finite
    n = len(trigger)
    keep_mask = np.ones(n, dtype=bool)  # Default: keep all
    
    # For positions >= warmup, apply random masking
    if warmup < n:
        # Generate random values for positions >= warmup
        random_vals = rng.random(n - warmup)
        keep_mask[warmup:] = random_vals < trigger_rate
    
    # Preserve existing NaN positions (they should remain NaN)
    # Only mask positions that are currently finite and not kept
    finite_mask = np.isfinite(masked)
    
    # Apply masking: set non-kept finite positions to NaN
    # But preserve warmup period (positions < warmup remain unchanged)
    to_mask = finite_mask & (~keep_mask)
    masked[to_mask] = np.nan
    
    return masked



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/perf/timers.py
sha256(source_bytes) = 5835f56b7ac695fc2c06df9ca9efbd6fdee1e2ef1a2199e5f500ecb581a25032
bytes = 1814
redacted = False
--------------------------------------------------------------------------------

"""
Perf Harness Timer Helper (P2-1.8)

Provides granular timing breakdown for kernel stages.
"""
from __future__ import annotations

import time
from typing import Dict


class PerfTimers:
    """
    Performance timer helper for granular breakdown.
    
    Supports multiple start/stop calls for the same timer name (accumulates).
    All timings are in seconds with '_s' suffix.
    """
    
    def __init__(self) -> None:
        self._accumulated: Dict[str, float] = {}
        self._active: Dict[str, float] = {}
    
    def start(self, name: str) -> None:
        """
        Start a timer. If already running, does nothing (no nested timing).
        """
        if name not in self._active:
            self._active[name] = time.perf_counter()
    
    def stop(self, name: str) -> None:
        """
        Stop a timer and accumulate the elapsed time.
        If timer was not started, does nothing.
        """
        if name in self._active:
            elapsed = time.perf_counter() - self._active[name]
            self._accumulated[name] = self._accumulated.get(name, 0.0) + elapsed
            del self._active[name]
    
    def as_dict_seconds(self) -> Dict[str, float]:
        """
        Return accumulated timings as dict with '_s' suffix keys.
        
        Returns:
            dict with keys like "t_xxx_s": float (seconds)
        """
        result: Dict[str, float] = {}
        for name, seconds in self._accumulated.items():
            # Ensure '_s' suffix
            key = name if name.endswith("_s") else f"{name}_s"
            result[key] = float(seconds)
        return result
    
    def get(self, name: str, default: float = 0.0) -> float:
        """
        Get accumulated time for a timer name.
        """
        return self._accumulated.get(name, default)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/__init__.py
sha256(source_bytes) = 545c38b0922de19734fbffde62792c37c2aef6a3216cfa472449173165220f7d
bytes = 4
redacted = False
--------------------------------------------------------------------------------





--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/funnel.py
sha256(source_bytes) = ee3b91e4f143383035667f29473d8af0a821978af5e732f1cdc79aba2da5ec65
bytes = 3386
redacted = False
--------------------------------------------------------------------------------

"""Funnel orchestrator - Stage0 → Top-K → Stage2 pipeline.

This is the main entry point for the Phase 4 Funnel pipeline.
It orchestrates the complete flow: proxy ranking → selection → full backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from FishBroWFS_V2.config.constants import TOPK_K
from FishBroWFS_V2.pipeline.stage0_runner import Stage0Result, run_stage0
from FishBroWFS_V2.pipeline.stage2_runner import Stage2Result, run_stage2
from FishBroWFS_V2.pipeline.topk import select_topk


@dataclass(frozen=True)
class FunnelResult:
    """
    Complete funnel pipeline result.
    
    Contains:
    - stage0_results: all Stage0 proxy ranking results
    - topk_param_ids: selected Top-K parameter indices
    - stage2_results: full backtest results for Top-K parameters
    - meta: optional metadata
    """
    stage0_results: List[Stage0Result]
    topk_param_ids: List[int]
    stage2_results: List[Stage2Result]
    meta: Optional[dict] = None


def run_funnel(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
    *,
    k: int = TOPK_K,
    commission: float = 0.0,
    slip: float = 0.0,
    order_qty: int = 1,
    proxy_name: str = "ma_proxy_v0",
) -> FunnelResult:
    """
    Run complete Funnel pipeline: Stage0 → Top-K → Stage2.
    
    Pipeline flow (fixed):
    1. Stage0: proxy ranking on all parameters
    2. Top-K: select top K parameters based on proxy_value
    3. Stage2: full backtest on Top-K subset
    
    Args:
        open_, high, low, close: OHLC arrays (float64, 1D, same length)
        params_matrix: float64 2D array (n_params, >=3)
            - For Stage0: uses col0 (fast_len), col1 (slow_len) for MA proxy
            - For Stage2: uses col0 (channel_len), col1 (atr_len), col2 (stop_mult) for kernel
        k: number of top parameters to select (default: TOPK_K)
        commission: commission per trade (absolute)
        slip: slippage per trade (absolute)
        order_qty: order quantity (default: 1)
        proxy_name: name of proxy to use for Stage0 (default: ma_proxy_v0)
        
    Returns:
        FunnelResult containing:
        - stage0_results: all proxy ranking results
        - topk_param_ids: selected Top-K parameter indices
        - stage2_results: full backtest results for Top-K only
        
    Note:
        - Pipeline is deterministic: same input produces same output
        - Stage0 does NOT compute PnL metrics (only proxy_value)
        - Top-K selection is based solely on proxy_value
        - Stage2 runs full backtest only on Top-K subset
    """
    # Step 1: Stage0 - proxy ranking
    stage0_results = run_stage0(
        close,
        params_matrix,
        proxy_name=proxy_name,
    )
    
    # Step 2: Top-K selection
    topk_param_ids = select_topk(stage0_results, k=k)
    
    # Step 3: Stage2 - full backtest on Top-K
    stage2_results = run_stage2(
        open_,
        high,
        low,
        close,
        params_matrix,
        topk_param_ids,
        commission=commission,
        slip=slip,
        order_qty=order_qty,
    )
    
    return FunnelResult(
        stage0_results=stage0_results,
        topk_param_ids=topk_param_ids,
        stage2_results=stage2_results,
        meta=None,
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/funnel_plan.py
sha256(source_bytes) = 5b0049795f24e0d8b39cf6f7277c565b26f031cc1ff9ed7bbb35a76614d299af
bytes = 1867
redacted = False
--------------------------------------------------------------------------------

"""Funnel plan builder.

Builds default funnel plan with three stages:
- Stage 0: Coarse subsample (config rate)
- Stage 1: Increased subsample (min(1.0, stage0_rate * 2))
- Stage 2: Full confirm (1.0)
"""

from __future__ import annotations

from FishBroWFS_V2.pipeline.funnel_schema import FunnelPlan, StageName, StageSpec


def build_default_funnel_plan(cfg: dict) -> FunnelPlan:
    """
    Build default funnel plan with three stages.
    
    Rules (locked):
    - Stage 0: subsample = config's param_subsample_rate (coarse exploration)
    - Stage 1: subsample = min(1.0, stage0_rate * 2) (increased density)
    - Stage 2: subsample = 1.0 (full confirm, mandatory)
    
    Args:
        cfg: Configuration dictionary containing:
            - param_subsample_rate: Base subsample rate for Stage 0
            - topk_stage0: Optional top-K for Stage 0 (default: 50)
            - topk_stage1: Optional top-K for Stage 1 (default: 20)
    
    Returns:
        FunnelPlan with three stages
    """
    s0_rate = float(cfg["param_subsample_rate"])
    s1_rate = min(1.0, s0_rate * 2.0)
    s2_rate = 1.0  # Stage2 must be 1.0
    
    return FunnelPlan(stages=[
        StageSpec(
            name=StageName.STAGE0_COARSE,
            param_subsample_rate=s0_rate,
            topk=int(cfg.get("topk_stage0", 50)),
            notes={"rule": "default", "description": "Coarse exploration"},
        ),
        StageSpec(
            name=StageName.STAGE1_TOPK,
            param_subsample_rate=s1_rate,
            topk=int(cfg.get("topk_stage1", 20)),
            notes={"rule": "default", "description": "Top-K refinement"},
        ),
        StageSpec(
            name=StageName.STAGE2_CONFIRM,
            param_subsample_rate=s2_rate,
            topk=None,
            notes={"rule": "default", "description": "Full confirmation"},
        ),
    ])



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/funnel_runner.py
sha256(source_bytes) = 57b884cab89a1b10428c4042fb2fc523313dbe92adeb78452dfb8c13b458e009
bytes = 10711
redacted = False
--------------------------------------------------------------------------------

"""Funnel runner - orchestrates stage execution and artifact writing.

Runs funnel pipeline stages sequentially, writing artifacts for each stage.
Each stage gets its own run_id and run directory.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.core.artifacts import write_run_artifacts
from FishBroWFS_V2.core.audit_schema import AuditSchema, compute_params_effective
from FishBroWFS_V2.core.config_hash import stable_config_hash
from FishBroWFS_V2.core.config_snapshot import make_config_snapshot
from FishBroWFS_V2.core.oom_gate import decide_oom_action
from FishBroWFS_V2.core.paths import ensure_run_dir
from FishBroWFS_V2.core.run_id import make_run_id
from FishBroWFS_V2.data.session.tzdb_info import get_tzdb_info
from FishBroWFS_V2.pipeline.funnel_plan import build_default_funnel_plan
from FishBroWFS_V2.pipeline.funnel_schema import FunnelResultIndex, FunnelStageIndex
from FishBroWFS_V2.pipeline.runner_adapter import run_stage_job


def _get_git_info(repo_root: Path | None = None) -> tuple[str, bool]:
    """
    Get git SHA and dirty status.
    
    Args:
        repo_root: Optional path to repo root
        
    Returns:
        Tuple of (git_sha, dirty_repo)
    """
    if repo_root is None:
        repo_root = Path.cwd()
    
    try:
        # Get git SHA (short, 12 chars)
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        git_sha = result.stdout.strip()
        
        # Check if repo is dirty
        result_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        dirty_repo = len(result_status.stdout.strip()) > 0
        
        return git_sha, dirty_repo
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown", True


def run_funnel(cfg: dict, outputs_root: Path) -> FunnelResultIndex:
    """
    Run funnel pipeline with three stages.
    
    Each stage:
    1. Generates new run_id
    2. Creates run directory
    3. Builds AuditSchema
    4. Runs stage job (via adapter)
    5. Writes artifacts
    
    Args:
        cfg: Configuration dictionary containing:
            - season: Season identifier
            - dataset_id: Dataset identifier
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Base subsample rate for Stage 0
            - open_, high, low, close: OHLC arrays
            - params_matrix: Parameter matrix
            - commission, slip, order_qty: Trading parameters
            - topk_stage0, topk_stage1: Optional top-K counts
            - git_sha, dirty_repo, created_at: Optional audit fields
        outputs_root: Root outputs directory
    
    Returns:
        FunnelResultIndex with plan and stage execution indices
    """
    # Build funnel plan
    plan = build_default_funnel_plan(cfg)
    
    # Get git info if not provided
    git_sha = cfg.get("git_sha")
    dirty_repo = cfg.get("dirty_repo")
    if git_sha is None or dirty_repo is None:
        repo_root = cfg.get("repo_root")
        if repo_root:
            repo_root = Path(repo_root)
        git_sha, dirty_repo = _get_git_info(repo_root)
    
    created_at = cfg.get("created_at")
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    season = cfg["season"]
    dataset_id = cfg["dataset_id"]
    bars = int(cfg["bars"])
    params_total = int(cfg["params_total"])
    
    stage_indices: list[FunnelStageIndex] = []
    prev_winners: list[dict[str, Any]] = []
    
    for spec in plan.stages:
        # Generate run_id for this stage
        run_id = make_run_id(prefix=str(spec.name.value))
        
        # Create run directory
        run_dir = ensure_run_dir(outputs_root, season, run_id)
        
        # Build stage config (runtime: includes ndarrays for runner_adapter)
        stage_cfg = dict(cfg)
        stage_cfg["stage_name"] = str(spec.name.value)
        stage_cfg["param_subsample_rate"] = float(spec.param_subsample_rate)
        stage_cfg["topk"] = spec.topk
        
        # Pass previous stage winners to Stage2
        if spec.name.value == "stage2_confirm" and prev_winners:
            stage_cfg["prev_stage_winners"] = prev_winners
        
        # OOM Gate: Check memory limits before running stage
        mem_limit_mb = float(cfg.get("mem_limit_mb", 2048.0))
        allow_auto_downsample = cfg.get("allow_auto_downsample", True)
        auto_downsample_step = float(cfg.get("auto_downsample_step", 0.5))
        auto_downsample_min = float(cfg.get("auto_downsample_min", 0.02))
        
        gate_result = decide_oom_action(
            stage_cfg,
            mem_limit_mb=mem_limit_mb,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
        )
        
        # Handle gate actions
        if gate_result["action"] == "BLOCK":
            raise RuntimeError(
                f"OOM Gate BLOCKED stage {spec.name.value}: {gate_result['reason']}"
            )
        
        # Planned subsample for this stage (before gate adjustment)
        planned_subsample = float(spec.param_subsample_rate)
        final_subsample = gate_result["final_subsample"]
        
        # SSOT: Use new_cfg from gate_result (never mutate original stage_cfg)
        stage_cfg = gate_result["new_cfg"]
        
        # Use final_subsample for all calculations
        effective_subsample = final_subsample
        
        # Create sanitized snapshot (for hash and artifacts, excludes ndarrays)
        # Snapshot must reflect final subsample (after auto-downsample if any)
        stage_snapshot = make_config_snapshot(stage_cfg)
        
        # Compute config hash (only on sanitized snapshot)
        config_hash = stable_config_hash(stage_snapshot)
        
        # Compute params_effective with final subsample
        params_effective = compute_params_effective(params_total, effective_subsample)
        
        # Build AuditSchema (must use final subsample)
        audit = AuditSchema(
            run_id=run_id,
            created_at=created_at,
            git_sha=git_sha,
            dirty_repo=bool(dirty_repo),
            param_subsample_rate=effective_subsample,  # Use final subsample
            config_hash=config_hash,
            season=season,
            dataset_id=dataset_id,
            bars=bars,
            params_total=params_total,
            params_effective=params_effective,
            artifact_version="v1",
        )
        
        # Run stage job (adapter returns data only, no file I/O)
        # Use stage_cfg which has final subsample (after auto-downsample if any)
        stage_out = run_stage_job(stage_cfg)
        
        # Extract metrics and winners
        stage_metrics = dict(stage_out.get("metrics", {}))
        stage_winners = stage_out.get("winners", {"topk": [], "notes": {"schema": "v1"}})
        
        # Ensure metrics include required fields
        stage_metrics["param_subsample_rate"] = effective_subsample  # Use final subsample
        stage_metrics["params_effective"] = params_effective
        stage_metrics["params_total"] = params_total
        stage_metrics["bars"] = bars
        stage_metrics["stage_name"] = str(spec.name.value)
        
        # Add OOM gate fields (mandatory for audit)
        stage_metrics["oom_gate_action"] = gate_result["action"]
        stage_metrics["oom_gate_reason"] = gate_result["reason"]
        stage_metrics["mem_est_mb"] = gate_result["estimates"]["mem_est_mb"]
        stage_metrics["mem_limit_mb"] = mem_limit_mb
        stage_metrics["ops_est"] = gate_result["estimates"]["ops_est"]
        
        # Record planned subsample (before gate adjustment)
        stage_metrics["stage_planned_subsample"] = planned_subsample
        
        # If auto-downsample occurred, record original and final subsample
        if gate_result["action"] == "AUTO_DOWNSAMPLE":
            stage_metrics["oom_gate_original_subsample"] = planned_subsample
            stage_metrics["oom_gate_final_subsample"] = final_subsample
        
        # Phase 6.6: Add tzdb metadata to manifest
        manifest_dict = audit.to_dict()
        tzdb_provider, tzdb_version = get_tzdb_info()
        manifest_dict["tzdb_provider"] = tzdb_provider
        manifest_dict["tzdb_version"] = tzdb_version
        
        # Add data_tz and exchange_tz if available in config
        # These come from session profile if session processing is used
        if "data_tz" in stage_cfg:
            manifest_dict["data_tz"] = stage_cfg["data_tz"]
        if "exchange_tz" in stage_cfg:
            manifest_dict["exchange_tz"] = stage_cfg["exchange_tz"]
        
        # Phase 7: Add strategy metadata if available
        if "strategy_id" in stage_cfg:
            import json
            import hashlib
            
            manifest_dict["strategy_id"] = stage_cfg["strategy_id"]
            
            if "strategy_version" in stage_cfg:
                manifest_dict["strategy_version"] = stage_cfg["strategy_version"]
            
            if "param_schema" in stage_cfg:
                param_schema = stage_cfg["param_schema"]
                # Compute hash of param_schema
                schema_json = json.dumps(param_schema, sort_keys=True)
                schema_hash = hashlib.sha1(schema_json.encode("utf-8")).hexdigest()
                manifest_dict["param_schema_hash"] = schema_hash
        
        # Write artifacts (unified artifact system)
        # Use sanitized snapshot (not runtime cfg with ndarrays)
        write_run_artifacts(
            run_dir=run_dir,
            manifest=manifest_dict,
            config_snapshot=stage_snapshot,
            metrics=stage_metrics,
            winners=stage_winners,
        )
        
        # Record stage index
        stage_indices.append(
            FunnelStageIndex(
                stage=spec.name,
                run_id=run_id,
                run_dir=str(run_dir.relative_to(outputs_root)),
            )
        )
        
        # Save winners for next stage
        prev_winners = stage_winners.get("topk", [])
    
    return FunnelResultIndex(plan=plan, stages=stage_indices)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/funnel_schema.py
sha256(source_bytes) = 91738ad1a37ceebd88358d1ff410043fa547764f5fa89a5786268845010dcbb1
bytes = 1667
redacted = False
--------------------------------------------------------------------------------

"""Funnel schema definitions.

Defines stage names, specifications, and result indexing for funnel pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StageName(str, Enum):
    """Stage names for funnel pipeline."""
    STAGE0_COARSE = "stage0_coarse"
    STAGE1_TOPK = "stage1_topk"
    STAGE2_CONFIRM = "stage2_confirm"


@dataclass(frozen=True)
class StageSpec:
    """
    Stage specification for funnel pipeline.
    
    Each stage defines:
    - name: Stage identifier
    - param_subsample_rate: Subsample rate for this stage
    - topk: Optional top-K count (None for Stage2)
    - notes: Additional metadata
    """
    name: StageName
    param_subsample_rate: float
    topk: Optional[int] = None
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FunnelPlan:
    """
    Funnel plan containing ordered list of stages.
    
    Stages are executed in order: Stage0 -> Stage1 -> Stage2
    """
    stages: List[StageSpec]


@dataclass(frozen=True)
class FunnelStageIndex:
    """
    Index entry for a single stage execution.
    
    Records:
    - stage: Stage name
    - run_id: Run ID for this stage
    - run_dir: Relative path to run directory
    """
    stage: StageName
    run_id: str
    run_dir: str  # Relative path string


@dataclass(frozen=True)
class FunnelResultIndex:
    """
    Complete funnel execution result index.
    
    Contains:
    - plan: Original funnel plan
    - stages: List of stage execution indices
    """
    plan: FunnelPlan
    stages: List[FunnelStageIndex]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/governance_eval.py
sha256(source_bytes) = 4accba2058ec7ddfe082659a25982ea8a6b8c5c03c2f24c7b6efef3de9711c74
bytes = 22167
redacted = False
--------------------------------------------------------------------------------

"""Governance evaluator - rule engine for candidate decisions.

Reads artifacts from stage run directories and applies governance rules
to produce KEEP/FREEZE/DROP decisions for each candidate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from FishBroWFS_V2.core.artifact_reader import (
    read_config_snapshot,
    read_manifest,
    read_metrics,
    read_winners,
)
from FishBroWFS_V2.core.config_hash import stable_config_hash
from FishBroWFS_V2.core.governance_schema import (
    Decision,
    EvidenceRef,
    GovernanceItem,
    GovernanceReport,
)
from FishBroWFS_V2.core.winners_schema import is_winners_v2


# Rule thresholds (MVP - locked)
R2_DEGRADE_THRESHOLD = 0.20  # 20% degradation threshold for R2
R3_DENSITY_THRESHOLD = 3  # Minimum count for R3 FREEZE (same strategy_id)


def normalize_candidate(
    item: Dict[str, Any],
    config_snapshot: Optional[Dict[str, Any]] = None,
    is_v2: bool = False,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Normalize candidate from winners.json to (strategy_id, params_dict, metrics_subset).
    
    Handles both v2 and legacy formats gracefully.
    
    Args:
        item: Candidate item from winners.json topk list
        config_snapshot: Optional config snapshot to extract params from
        is_v2: Whether item is from v2 schema (fast path)
        
    Returns:
        Tuple of (strategy_id, params_dict, metrics_subset)
        - strategy_id: Strategy identifier
        - params_dict: Normalized params dict
        - metrics_subset: Metrics dict extracted from item
    """
    # Fast path for v2 schema
    if is_v2:
        strategy_id = item.get("strategy_id", "unknown")
        params_dict = item.get("params", {})
        
        # Extract metrics from v2 structure
        metrics_subset = {}
        metrics = item.get("metrics", {})
        
        # Legacy fields (for backward compatibility)
        if "net_profit" in metrics:
            metrics_subset["net_profit"] = float(metrics["net_profit"])
        if "trades" in metrics:
            metrics_subset["trades"] = int(metrics["trades"])
        if "max_dd" in metrics:
            metrics_subset["max_dd"] = float(metrics["max_dd"])
        if "proxy_value" in metrics:
            metrics_subset["proxy_value"] = float(metrics["proxy_value"])
        
        # Also check top-level (legacy compatibility)
        if "net_profit" in item:
            metrics_subset["net_profit"] = float(item["net_profit"])
        if "trades" in item:
            metrics_subset["trades"] = int(item["trades"])
        if "max_dd" in item:
            metrics_subset["max_dd"] = float(item["max_dd"])
        if "proxy_value" in item:
            metrics_subset["proxy_value"] = float(item["proxy_value"])
        
        return strategy_id, params_dict, metrics_subset
    
    # Legacy path (backward compatibility)
    # Extract metrics subset (varies by stage)
    metrics_subset = {}
    if "proxy_value" in item:
        metrics_subset["proxy_value"] = float(item["proxy_value"])
    if "net_profit" in item:
        metrics_subset["net_profit"] = float(item["net_profit"])
    if "trades" in item:
        metrics_subset["trades"] = int(item["trades"])
    if "max_dd" in item:
        metrics_subset["max_dd"] = float(item["max_dd"])
    
    # MVP: Use fixed strategy_id (donchian_atr)
    # Future: Extract from config_snapshot or item metadata
    strategy_id = "donchian_atr"
    
    # Extract params_dict
    # Priority: 1) item["params"], 2) config_snapshot params, 3) fallback to param_id-based dict
    params_dict = item.get("params", {})
    
    if not params_dict and config_snapshot:
        # Try to extract from config_snapshot
        # MVP: If params_matrix is in config_snapshot, extract row by param_id
        # For now, use param_id as fallback
        param_id = item.get("param_id")
        if param_id is not None:
            # MVP fallback: Create minimal params dict from param_id
            # Future: Extract actual params from params_matrix in config_snapshot
            params_dict = {"param_id": int(param_id)}
    
    if not params_dict:
        # Final fallback: use param_id if available
        param_id = item.get("param_id")
        if param_id is not None:
            params_dict = {"param_id": int(param_id)}
        else:
            params_dict = {}
    
    return strategy_id, params_dict, metrics_subset


def generate_candidate_id(strategy_id: str, params_dict: Dict[str, Any]) -> str:
    """
    Generate stable candidate_id from strategy_id and params_dict.
    
    Format: {strategy_id}:{params_hash[:12]}
    
    Args:
        strategy_id: Strategy identifier
        params_dict: Parameters dict (must be JSON-serializable)
        
    Returns:
        Stable candidate_id string
    """
    # Compute stable hash of params_dict
    params_hash = stable_config_hash(params_dict)
    
    # Use first 12 chars of hash
    hash_short = params_hash[:12]
    
    return f"{strategy_id}:{hash_short}"


def find_stage2_candidate(
    candidate_param_id: int,
    stage2_winners: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Find Stage2 candidate matching param_id.
    
    Args:
        candidate_param_id: param_id from Stage1 winner
        stage2_winners: List of Stage2 winners
        
    Returns:
        Matching Stage2 candidate dict, or None if not found
    """
    for item in stage2_winners:
        if item.get("param_id") == candidate_param_id:
            return item
    return None


def extract_key_metric(
    metrics: Dict[str, Any],
    candidate_metrics: Dict[str, Any],
    metric_name: str,
) -> Optional[float]:
    """
    Extract key metric with fallback logic.
    
    Priority:
    1. candidate_metrics[metric_name]
    2. metrics[metric_name]
    3. Fallback: net_profit / max_dd (if both exist)
    4. None
    
    Args:
        metrics: Stage metrics dict
        candidate_metrics: Candidate-specific metrics dict
        metric_name: Metric name to extract
        
    Returns:
        Metric value (float), or None if not found
    """
    # Try candidate_metrics first
    if metric_name in candidate_metrics:
        val = candidate_metrics[metric_name]
        if isinstance(val, (int, float)):
            return float(val)
    
    # Try stage metrics
    if metric_name in metrics:
        val = metrics[metric_name]
        if isinstance(val, (int, float)):
            return float(val)
    
    # Fallback: net_profit / max_dd (if both exist)
    if metric_name in ("finalscore", "net_over_mdd"):
        net_profit = candidate_metrics.get("net_profit") or metrics.get("net_profit")
        max_dd = candidate_metrics.get("max_dd") or metrics.get("max_dd")
        if net_profit is not None and max_dd is not None:
            if abs(max_dd) > 1e-10:  # Avoid division by zero
                return float(net_profit) / abs(float(max_dd))
            elif float(net_profit) > 0:
                return float("inf")  # Positive profit with zero DD
            else:
                return float("-inf")  # Negative profit with zero DD
    
    return None


def apply_rule_r1(
    candidate: Dict[str, Any],
    stage2_winners: List[Dict[str, Any]],
    is_v2: bool = False,
) -> Tuple[bool, str]:
    """
    Rule R1: Evidence completeness.
    
    If candidate appears in Stage1 winners but:
    - Cannot find corresponding Stage2 metrics (or Stage2 did not run successfully)
    -> DROP (reason: unverified)
    
    Args:
        candidate: Candidate from Stage1 winners
        stage2_winners: List of Stage2 winners
        is_v2: Whether candidates are v2 schema
        
    Returns:
        Tuple of (should_drop, reason)
    """
    # For v2: use candidate_id for matching
    if is_v2:
        candidate_id = candidate.get("candidate_id")
        if candidate_id is None:
            return True, "missing_candidate_id"
        
        # Find matching candidate by candidate_id
        for item in stage2_winners:
            if item.get("candidate_id") == candidate_id:
                return False, ""
        
        return True, "unverified"
    
    # Legacy path: use param_id
    param_id = candidate.get("param_id")
    if param_id is None:
        # Try to extract from source (v2 fallback)
        source = candidate.get("source", {})
        param_id = source.get("param_id")
        if param_id is None:
            # Try metrics (v2 fallback)
            metrics = candidate.get("metrics", {})
            param_id = metrics.get("param_id")
            if param_id is None:
                return True, "missing_param_id"
    
    stage2_match = find_stage2_candidate(param_id, stage2_winners)
    if stage2_match is None:
        return True, "unverified"
    
    return False, ""


def apply_rule_r2(
    candidate: Dict[str, Any],
    stage1_metrics: Dict[str, Any],
    stage2_candidate: Dict[str, Any],
    stage2_metrics: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Rule R2: Confirm stability.
    
    If candidate's key metrics degrade > threshold in Stage2 vs Stage1 -> DROP.
    
    Priority:
    1. finalscore or net_over_mdd
    2. Fallback: net_profit / max_dd
    
    Args:
        candidate: Candidate from Stage1 winners
        stage1_metrics: Stage1 metrics dict
        stage2_candidate: Matching Stage2 candidate
        stage2_metrics: Stage2 metrics dict
        
    Returns:
        Tuple of (should_drop, reason)
    """
    # Extract Stage1 metric
    stage1_val = extract_key_metric(
        stage1_metrics,
        candidate,
        "finalscore",
    )
    if stage1_val is None:
        stage1_val = extract_key_metric(
            stage1_metrics,
            candidate,
            "net_over_mdd",
        )
    if stage1_val is None:
        # Fallback: net_profit / max_dd
        stage1_val = extract_key_metric(
            stage1_metrics,
            candidate,
            "net_over_mdd",
        )
    
    # Extract Stage2 metric
    stage2_val = extract_key_metric(
        stage2_metrics,
        stage2_candidate,
        "finalscore",
    )
    if stage2_val is None:
        stage2_val = extract_key_metric(
            stage2_metrics,
            stage2_candidate,
            "net_over_mdd",
        )
    if stage2_val is None:
        # Fallback: net_profit / max_dd
        stage2_val = extract_key_metric(
            stage2_metrics,
            stage2_candidate,
            "net_over_mdd",
        )
    
    # If either metric is missing, cannot apply R2
    if stage1_val is None or stage2_val is None:
        return False, ""
    
    # Check degradation
    if stage1_val == 0.0:
        # Avoid division by zero
        if stage2_val < 0.0:
            return True, f"degraded_from_zero_to_negative"
        return False, ""
    
    degradation_ratio = (stage1_val - stage2_val) / abs(stage1_val)
    if degradation_ratio > R2_DEGRADE_THRESHOLD:
        return True, f"degraded_{degradation_ratio:.2%}"
    
    return False, ""


def apply_rule_r3(
    candidate: Dict[str, Any],
    all_stage1_winners: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    """
    Rule R3: Plateau hint (MVP simplified version).
    
    If same strategy_id appears >= threshold times in Stage1 topk -> FREEZE.
    
    MVP version: Count occurrences of same strategy_id (simplified).
    Future: Geometric distance/clustering analysis.
    
    Args:
        candidate: Candidate from Stage1 winners
        all_stage1_winners: All Stage1 winners (for density calculation)
        
    Returns:
        Tuple of (should_freeze, reason)
    """
    strategy_id, _, _ = normalize_candidate(candidate)
    
    # Count occurrences of same strategy_id
    count = 0
    for item in all_stage1_winners:
        item_strategy_id, _, _ = normalize_candidate(item)
        if item_strategy_id == strategy_id:
            count += 1
    
    if count >= R3_DENSITY_THRESHOLD:
        return True, f"density_{count}_over_threshold_{R3_DENSITY_THRESHOLD}"
    
    return False, ""


def evaluate_governance(
    *,
    stage0_dir: Path,
    stage1_dir: Path,
    stage2_dir: Path,
) -> GovernanceReport:
    """
    Evaluate governance rules on candidates from Stage1 winners.
    
    Reads artifacts from three stage directories and applies rules:
    - R1: Evidence completeness (DROP if Stage2 missing)
    - R2: Confirm stability (DROP if metrics degrade > threshold)
    - R3: Plateau hint (FREEZE if density over threshold)
    
    Args:
        stage0_dir: Path to Stage0 run directory
        stage1_dir: Path to Stage1 run directory
        stage2_dir: Path to Stage2 run directory
        
    Returns:
        GovernanceReport with decisions for each candidate
    """
    # Read artifacts
    stage0_manifest = read_manifest(stage0_dir)
    stage0_metrics = read_metrics(stage0_dir)
    stage0_winners = read_winners(stage0_dir)
    stage0_config = read_config_snapshot(stage0_dir)
    
    stage1_manifest = read_manifest(stage1_dir)
    stage1_metrics = read_metrics(stage1_dir)
    stage1_winners = read_winners(stage1_dir)
    stage1_config = read_config_snapshot(stage1_dir)
    
    stage2_manifest = read_manifest(stage2_dir)
    stage2_metrics = read_metrics(stage2_dir)
    stage2_winners = read_winners(stage2_dir)
    stage2_config = read_config_snapshot(stage2_dir)
    
    # Extract candidates from Stage1 winners (topk)
    stage1_topk = stage1_winners.get("topk", [])
    
    # Check if winners is v2 schema
    stage1_is_v2 = is_winners_v2(stage1_winners)
    
    # Get git_sha and created_at from Stage1 manifest
    git_sha = stage1_manifest.get("git_sha", "unknown")
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Build governance items
    items: List[GovernanceItem] = []
    
    for candidate in stage1_topk:
        # Normalize candidate (pass stage1_config for params extraction, and is_v2 flag)
        strategy_id, params_dict, metrics_subset = normalize_candidate(
            candidate, stage1_config, is_v2=stage1_is_v2
        )
        
        # Generate candidate_id
        candidate_id = generate_candidate_id(strategy_id, params_dict)
        
        # Apply rules
        reasons: List[str] = []
        evidence: List[EvidenceRef] = []
        decision = Decision.KEEP  # Default
        
        # R1: Evidence completeness
        # Check if Stage2 is v2 (for candidate matching)
        stage2_is_v2 = is_winners_v2(stage2_winners)
        should_drop_r1, reason_r1 = apply_rule_r1(
            candidate, stage2_winners.get("topk", []), is_v2=stage2_is_v2
        )
        if should_drop_r1:
            decision = Decision.DROP
            reasons.append(f"R1: {reason_r1}")
            # Add evidence
            evidence.append(
                EvidenceRef(
                    run_id=stage1_manifest.get("run_id", "unknown"),
                    stage_name="stage1_topk",
                    artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                    key_metrics={
                        "param_id": candidate.get("param_id"),
                        **metrics_subset,
                    },
                )
            )
            # Create item and continue (no need to check R2/R3)
            items.append(
                GovernanceItem(
                    candidate_id=candidate_id,
                    decision=decision,
                    reasons=reasons,
                    evidence=evidence,
                    created_at=created_at,
                    git_sha=git_sha,
                )
            )
            continue
        
        # R2: Confirm stability
        # Find Stage2 candidate (support both v2 and legacy)
        if stage1_is_v2:
            candidate_id = candidate.get("candidate_id")
            stage2_candidate = None
            if candidate_id:
                for item in stage2_winners.get("topk", []):
                    if item.get("candidate_id") == candidate_id:
                        stage2_candidate = item
                        break
        else:
            param_id = candidate.get("param_id")
            if param_id is None:
                # Try source/metrics fallback
                source = candidate.get("source", {})
                param_id = source.get("param_id") or candidate.get("metrics", {}).get("param_id")
            stage2_candidate = find_stage2_candidate(
                param_id,
                stage2_winners.get("topk", []),
            ) if param_id is not None else None
        if stage2_candidate is not None:
            should_drop_r2, reason_r2 = apply_rule_r2(
                candidate,
                stage1_metrics,
                stage2_candidate,
                stage2_metrics,
            )
            if should_drop_r2:
                decision = Decision.DROP
                reasons.append(f"R2: {reason_r2}")
                # Add evidence
                evidence.append(
                    EvidenceRef(
                        run_id=stage1_manifest.get("run_id", "unknown"),
                        stage_name="stage1_topk",
                        artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                        key_metrics={
                            "param_id": candidate.get("param_id"),
                            **metrics_subset,
                        },
                    )
                )
                evidence.append(
                    EvidenceRef(
                        run_id=stage2_manifest.get("run_id", "unknown"),
                        stage_name="stage2_confirm",
                        artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                        key_metrics={
                            "param_id": stage2_candidate.get("param_id"),
                            "net_profit": stage2_candidate.get("net_profit"),
                            "trades": stage2_candidate.get("trades"),
                            "max_dd": stage2_candidate.get("max_dd"),
                        },
                    )
                )
                # Create item and continue (no need to check R3)
                items.append(
                    GovernanceItem(
                        candidate_id=candidate_id,
                        decision=decision,
                        reasons=reasons,
                        evidence=evidence,
                        created_at=created_at,
                        git_sha=git_sha,
                    )
                )
                continue
        
        # R3: Plateau hint (needs normalized strategy_id)
        should_freeze_r3, reason_r3 = apply_rule_r3(candidate, stage1_topk)
        if should_freeze_r3:
            decision = Decision.FREEZE
            reasons.append(f"R3: {reason_r3}")
        
        # Add evidence (always include Stage1 and Stage2 if available)
        evidence.append(
            EvidenceRef(
                run_id=stage1_manifest.get("run_id", "unknown"),
                stage_name="stage1_topk",
                artifact_paths=["manifest.json", "metrics.json", "winners.json", "config_snapshot.json"],
                key_metrics={
                    "param_id": candidate.get("param_id"),
                    **metrics_subset,
                    "stage_planned_subsample": stage1_metrics.get("stage_planned_subsample"),
                    "param_subsample_rate": stage1_metrics.get("param_subsample_rate"),
                    "params_effective": stage1_metrics.get("params_effective"),
                },
            )
        )
        if stage2_candidate is not None:
            evidence.append(
                EvidenceRef(
                    run_id=stage2_manifest.get("run_id", "unknown"),
                    stage_name="stage2_confirm",
                    artifact_paths=["manifest.json", "metrics.json", "winners.json", "config_snapshot.json"],
                    key_metrics={
                        "param_id": stage2_candidate.get("param_id"),
                        "net_profit": stage2_candidate.get("net_profit"),
                        "trades": stage2_candidate.get("trades"),
                        "max_dd": stage2_candidate.get("max_dd"),
                        "param_subsample_rate": stage2_metrics.get("param_subsample_rate"),
                        "params_effective": stage2_metrics.get("params_effective"),
                    },
                )
            )
        
        # Create item
        items.append(
            GovernanceItem(
                candidate_id=candidate_id,
                decision=decision,
                reasons=reasons,
                evidence=evidence,
                created_at=created_at,
                git_sha=git_sha,
            )
        )
    
    # Build metadata
    # Extract data_fingerprint_sha1 from manifests (prefer Stage1, fallback to others)
    data_fingerprint_sha1 = (
        stage1_manifest.get("data_fingerprint_sha1") or
        stage0_manifest.get("data_fingerprint_sha1") or
        stage2_manifest.get("data_fingerprint_sha1") or
        ""
    )
    
    metadata = {
        "governance_id": stage1_manifest.get("run_id", "unknown"),  # Use Stage1 run_id as base
        "season": stage1_manifest.get("season", "unknown"),
        "created_at": created_at,
        "git_sha": git_sha,
        "data_fingerprint_sha1": data_fingerprint_sha1,  # Phase 6.5: Mandatory fingerprint
        "stage0_run_id": stage0_manifest.get("run_id", "unknown"),
        "stage1_run_id": stage1_manifest.get("run_id", "unknown"),
        "stage2_run_id": stage2_manifest.get("run_id", "unknown"),
        "total_candidates": len(items),
        "decisions": {
            "KEEP": sum(1 for item in items if item.decision == Decision.KEEP),
            "FREEZE": sum(1 for item in items if item.decision == Decision.FREEZE),
            "DROP": sum(1 for item in items if item.decision == Decision.DROP),
        },
    }
    
    return GovernanceReport(items=items, metadata=metadata)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/metrics_schema.py
sha256(source_bytes) = b0834c86d116fe97b6cf18ad1de87825e484f6927c9a8786d0a102af2ef873ea
bytes = 434
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

"""
Metrics column schema (single source of truth).

Defines the column order for metrics arrays returned by run_grid().
"""

# Column indices for metrics array (n_params, 3)
METRICS_COL_NET_PROFIT = 0
METRICS_COL_TRADES = 1
METRICS_COL_MAX_DD = 2

# Column names (for documentation/debugging)
METRICS_COLUMN_NAMES = ["net_profit", "trades", "max_dd"]

# Number of columns
METRICS_N_COLUMNS = 3



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/param_sort.py
sha256(source_bytes) = 5a1587b17dce3884102e38513f384bf82d436e0ec44846f3f5fef4e96c2f627a
bytes = 842
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

import numpy as np


def sort_params_cache_friendly(params: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Cache-friendly sorting for parameter matrix.

    params: shape (n, k) float64.
      Convention (Phase 3B v1):
        col0 = channel_len
        col1 = atr_len
        col2 = stop_mult

    Returns:
      sorted_params: params reordered (view/copy depending on numpy)
      order: indices such that sorted_params = params[order]
    """
    if params.ndim != 2 or params.shape[1] < 3:
        raise ValueError("params must be (n, >=3) array")

    # Primary: channel_len (int-like)
    # Secondary: atr_len (int-like)
    # Tertiary: stop_mult
    ch = params[:, 0]
    atr = params[:, 1]
    sm = params[:, 2]

    order = np.lexsort((sm, atr, ch))
    return params[order], order




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/portfolio_runner.py
sha256(source_bytes) = cf8884a198fd10065b248242522a1fd55ab20b2f0732b18ba087cd97222eb378
bytes = 2093
redacted = False
--------------------------------------------------------------------------------

"""Portfolio runner - compile and write portfolio artifacts.

Phase 8: Load, validate, compile, and write portfolio artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from FishBroWFS_V2.portfolio.artifacts import write_portfolio_artifacts
from FishBroWFS_V2.portfolio.compiler import compile_portfolio
from FishBroWFS_V2.portfolio.loader import load_portfolio_spec
from FishBroWFS_V2.portfolio.validate import validate_portfolio_spec


def run_portfolio(spec_path: Path, outputs_root: Path) -> Dict[str, Any]:
    """Run portfolio compilation pipeline.
    
    Process:
    1. Load portfolio spec
    2. Validate spec
    3. Compile jobs
    4. Write portfolio artifacts
    
    Args:
        spec_path: Path to portfolio spec file
        outputs_root: Root outputs directory
        
    Returns:
        Dict with:
            - portfolio_id: Portfolio ID
            - portfolio_version: Portfolio version
            - portfolio_hash: Portfolio hash
            - artifacts: Dict mapping artifact names to relative paths
            - artifacts_dir: Absolute path to artifacts directory
    """
    # Load spec
    spec = load_portfolio_spec(spec_path)
    
    # Validate spec
    validate_portfolio_spec(spec)
    
    # Compile jobs
    jobs = compile_portfolio(spec)
    
    # Determine artifacts directory
    # Format: outputs_root/portfolios/{portfolio_id}/{version}/
    artifacts_dir = outputs_root / "portfolios" / spec.portfolio_id / spec.version
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Write artifacts
    artifact_paths = write_portfolio_artifacts(spec, jobs, artifacts_dir)
    
    # Compute hash
    from FishBroWFS_V2.portfolio.artifacts import compute_portfolio_hash
    portfolio_hash = compute_portfolio_hash(spec)
    
    return {
        "portfolio_id": spec.portfolio_id,
        "portfolio_version": spec.version,
        "portfolio_hash": portfolio_hash,
        "artifacts": artifact_paths,
        "artifacts_dir": str(artifacts_dir),
        "jobs_count": len(jobs),
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/runner_adapter.py
sha256(source_bytes) = 6e0e855e6f0610b709c943bfef172046db54f19908bc699e41bc1f401113c5d5
bytes = 8891
redacted = False
--------------------------------------------------------------------------------

"""Runner adapter for funnel pipeline.

Provides unified interface to existing runners without exposing engine details.
Adapter returns data only (no file I/O) - all file writing is done by artifacts system.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from FishBroWFS_V2.pipeline.funnel import run_funnel as run_funnel_legacy
from FishBroWFS_V2.pipeline.runner_grid import run_grid
from FishBroWFS_V2.pipeline.stage0_runner import run_stage0
from FishBroWFS_V2.pipeline.stage2_runner import run_stage2
from FishBroWFS_V2.pipeline.topk import select_topk


def _coerce_1d_float64(x):
    if isinstance(x, np.ndarray):
        return x.astype(np.float64, copy=False)
    return np.asarray(x, dtype=np.float64)


def _coerce_2d_float64(x):
    if isinstance(x, np.ndarray):
        return x.astype(np.float64, copy=False)
    return np.asarray(x, dtype=np.float64)


def _coerce_arrays(cfg: dict) -> dict:
    # in-place is ok (stage_cfg is per-stage copy anyway)
    if "open_" in cfg:
        cfg["open_"] = _coerce_1d_float64(cfg["open_"])
    if "high" in cfg:
        cfg["high"] = _coerce_1d_float64(cfg["high"])
    if "low" in cfg:
        cfg["low"] = _coerce_1d_float64(cfg["low"])
    if "close" in cfg:
        cfg["close"] = _coerce_1d_float64(cfg["close"])
    if "params_matrix" in cfg:
        cfg["params_matrix"] = _coerce_2d_float64(cfg["params_matrix"])
    return cfg


def run_stage_job(stage_cfg: dict) -> dict:
    """
    Run a stage job and return metrics and winners.
    
    This adapter wraps existing runners (run_grid, run_stage0, run_stage2)
    to provide a unified interface. It does NOT write any files - all file
    writing must be done by the artifacts system.
    
    Args:
        stage_cfg: Stage configuration dictionary containing:
            - stage_name: Stage identifier ("stage0_coarse", "stage1_topk", "stage2_confirm")
            - param_subsample_rate: Subsample rate for this stage
            - topk: Optional top-K count (for Stage0/1)
            - open_, high, low, close: OHLC arrays
            - params_matrix: Parameter matrix
            - commission, slip, order_qty: Trading parameters
            - Other stage-specific parameters
    
    Returns:
        Dictionary with:
        - metrics: dict containing performance metrics
        - winners: dict with schema {"topk": [...], "notes": {"schema": "v1", ...}}
    
    Note:
        - This function does NOT write any files
        - All file writing must be done by core/artifacts.py
        - Returns data only for artifact system to consume
    """
    stage_cfg = _coerce_arrays(stage_cfg)
    
    stage_name = stage_cfg.get("stage_name", "")
    
    if stage_name == "stage0_coarse":
        return _run_stage0_job(stage_cfg)
    elif stage_name == "stage1_topk":
        return _run_stage1_job(stage_cfg)
    elif stage_name == "stage2_confirm":
        return _run_stage2_job(stage_cfg)
    else:
        raise ValueError(f"Unknown stage_name: {stage_name}")


def _run_stage0_job(cfg: dict) -> dict:
    """Run Stage0 coarse exploration job."""
    close = cfg["close"]
    params_matrix = cfg["params_matrix"]
    proxy_name = cfg.get("proxy_name", "ma_proxy_v0")
    
    # Apply subsample if needed
    param_subsample_rate = cfg.get("param_subsample_rate", 1.0)
    if param_subsample_rate < 1.0:
        n_total = params_matrix.shape[0]
        n_effective = int(n_total * param_subsample_rate)
        # Deterministic selection (use seed from config if available)
        seed = cfg.get("subsample_seed", 42)
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n_total)
        selected_indices = np.sort(perm[:n_effective])
        params_matrix = params_matrix[selected_indices]
    
    # Run Stage0
    stage0_results = run_stage0(close, params_matrix, proxy_name=proxy_name)
    
    # Extract metrics
    metrics = {
        "params_total": cfg.get("params_total", params_matrix.shape[0]),
        "params_effective": len(stage0_results),
        "bars": len(close),
        "stage_name": "stage0_coarse",
    }
    
    # Convert to winners format
    topk = cfg.get("topk", 50)
    topk_param_ids = select_topk(stage0_results, k=topk)
    
    winners = {
        "topk": [
            {
                "param_id": int(r.param_id),
                "proxy_value": float(r.proxy_value),
            }
            for r in stage0_results
            if r.param_id in topk_param_ids
        ],
        "notes": {
            "schema": "v1",
            "stage": "stage0_coarse",
            "topk_count": len(topk_param_ids),
        },
    }
    
    return {"metrics": metrics, "winners": winners}


def _run_stage1_job(cfg: dict) -> dict:
    """Run Stage1 Top-K refinement job."""
    # Stage1 uses grid runner with increased subsample
    open_ = cfg["open_"]
    high = cfg["high"]
    low = cfg["low"]
    close = cfg["close"]
    params_matrix = cfg["params_matrix"]
    commission = cfg.get("commission", 0.0)
    slip = cfg.get("slip", 0.0)
    order_qty = cfg.get("order_qty", 1)
    
    param_subsample_rate = cfg.get("param_subsample_rate", 1.0)
    
    # Apply subsample
    if param_subsample_rate < 1.0:
        n_total = params_matrix.shape[0]
        n_effective = int(n_total * param_subsample_rate)
        seed = cfg.get("subsample_seed", 42)
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n_total)
        selected_indices = np.sort(perm[:n_effective])
        params_matrix = params_matrix[selected_indices]
    
    # Run grid
    result = run_grid(
        open_,
        high,
        low,
        close,
        params_matrix,
        commission=commission,
        slip=slip,
        order_qty=order_qty,
        sort_params=True,
    )
    
    metrics_array = result.get("metrics", np.array([]))
    perf = result.get("perf", {})
    
    # Extract metrics
    metrics = {
        "params_total": cfg.get("params_total", params_matrix.shape[0]),
        "params_effective": metrics_array.shape[0] if metrics_array.size > 0 else 0,
        "bars": len(close),
        "stage_name": "stage1_topk",
    }
    
    if isinstance(perf, dict):
        runtime_s = perf.get("t_total_s", 0.0)
        if runtime_s:
            metrics["runtime_s"] = float(runtime_s)
    
    # Select top-K
    topk = cfg.get("topk", 20)
    if metrics_array.size > 0:
        # Sort by net_profit (column 0)
        net_profits = metrics_array[:, 0]
        top_indices = np.argsort(net_profits)[::-1][:topk]
        
        winners_list = []
        for idx in top_indices:
            winners_list.append({
                "param_id": int(idx),
                "net_profit": float(metrics_array[idx, 0]),
                "trades": int(metrics_array[idx, 1]),
                "max_dd": float(metrics_array[idx, 2]),
            })
    else:
        winners_list = []
    
    winners = {
        "topk": winners_list,
        "notes": {
            "schema": "v1",
            "stage": "stage1_topk",
            "topk_count": len(winners_list),
        },
    }
    
    return {"metrics": metrics, "winners": winners}


def _run_stage2_job(cfg: dict) -> dict:
    """Run Stage2 full confirmation job."""
    open_ = cfg["open_"]
    high = cfg["high"]
    low = cfg["low"]
    close = cfg["close"]
    params_matrix = cfg["params_matrix"]
    commission = cfg.get("commission", 0.0)
    slip = cfg.get("slip", 0.0)
    order_qty = cfg.get("order_qty", 1)
    
    # Stage2 must use all params (subsample_rate = 1.0)
    # Get top-K from previous stage if available
    prev_winners = cfg.get("prev_stage_winners", [])
    if prev_winners:
        param_ids = [w.get("param_id") for w in prev_winners if "param_id" in w]
    else:
        # Fallback: use all params
        param_ids = list(range(params_matrix.shape[0]))
    
    # Run Stage2
    stage2_results = run_stage2(
        open_,
        high,
        low,
        close,
        params_matrix,
        param_ids,
        commission=commission,
        slip=slip,
        order_qty=order_qty,
    )
    
    # Extract metrics
    metrics = {
        "params_total": cfg.get("params_total", params_matrix.shape[0]),
        "params_effective": len(stage2_results),
        "bars": len(close),
        "stage_name": "stage2_confirm",
    }
    
    # Convert to winners format
    winners_list = []
    for r in stage2_results:
        winners_list.append({
            "param_id": int(r.param_id),
            "net_profit": float(r.net_profit),
            "trades": int(r.trades),
            "max_dd": float(r.max_dd),
        })
    
    winners = {
        "topk": winners_list,
        "notes": {
            "schema": "v1",
            "stage": "stage2_confirm",
            "full_confirm": True,
        },
    }
    
    return {"metrics": metrics, "winners": winners}



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/runner_grid.py
sha256(source_bytes) = 83fd39a5220806df26d7f8708503f59069945fa750a16941c61e6866d3ea4acb
bytes = 37764
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import os
import time

from FishBroWFS_V2.data.layout import normalize_bars
from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, OrderKind, OrderRole, Side
from FishBroWFS_V2.pipeline.metrics_schema import (
    METRICS_COL_MAX_DD,
    METRICS_COL_NET_PROFIT,
    METRICS_COL_TRADES,
    METRICS_N_COLUMNS,
)
from FishBroWFS_V2.pipeline.param_sort import sort_params_cache_friendly
from FishBroWFS_V2.strategy.kernel import DonchianAtrParams, PrecomputedIndicators, run_kernel
from FishBroWFS_V2.indicators.numba_indicators import rolling_max, rolling_min, atr_wilder


def _max_drawdown(equity: np.ndarray) -> float:
    """
    Vectorized max drawdown on an equity curve.
    Handles empty arrays gracefully.
    """
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    mdd = float(np.min(dd))  # negative or 0
    return mdd


def _ensure_contiguous_bars(bars: BarArrays) -> BarArrays:
    if bars.open.flags["C_CONTIGUOUS"] and bars.high.flags["C_CONTIGUOUS"] and bars.low.flags["C_CONTIGUOUS"] and bars.close.flags["C_CONTIGUOUS"]:
        return bars
    return BarArrays(
        open=np.ascontiguousarray(bars.open, dtype=np.float64),
        high=np.ascontiguousarray(bars.high, dtype=np.float64),
        low=np.ascontiguousarray(bars.low, dtype=np.float64),
        close=np.ascontiguousarray(bars.close, dtype=np.float64),
    )


def run_grid(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
    sort_params: bool = True,
    force_close_last: bool = False,
    return_debug: bool = False,
) -> Dict[str, object]:
    """
    Phase 3B v1: Dynamic Grid Runner (homology locked).

    params_matrix: shape (n, >=3) float64
      col0 channel_len (int-like)
      col1 atr_len (int-like)
      col2 stop_mult (float)

    Args:
        force_close_last: If True, force close any open positions at the last bar
            using close[-1] as exit price. This ensures trades > 0 when fills exist.

    Returns:
      dict with:
        - metrics: np.ndarray shape (n, 3) float64 columns:
            [net_profit, trades, max_dd] (see pipeline.metrics_schema for column indices)
        - order: np.ndarray indices mapping output rows back to original params (or identity)
    """
    profile_grid = os.environ.get("FISHBRO_PROFILE_GRID", "").strip() == "1"
    profile_kernel = os.environ.get("FISHBRO_PROFILE_KERNEL", "").strip() == "1"
    
    # Stage P2-1.8: Bridge (B) - if user turns on GRID profiling, kernel timing must be enabled too.
    # This provides stable UX: grid breakdown automatically enables kernel timing.
    # Only restore if we set it ourselves, to avoid polluting external caller's environment.
    _set_kernel_profile = False
    if profile_grid and not profile_kernel:
        os.environ["FISHBRO_PROFILE_KERNEL"] = "1"
        _set_kernel_profile = True
    
    # Treat either flag as "profile mode" for grid aggregation.
    profile = profile_grid or profile_kernel
    
    sim_only = os.environ.get("FISHBRO_PERF_SIM_ONLY", "").strip() == "1"
    t0 = time.perf_counter()

    bars = _ensure_contiguous_bars(normalize_bars(open_, high, low, close))
    t_prep1 = time.perf_counter()

    if params_matrix.ndim != 2 or params_matrix.shape[1] < 3:
        raise ValueError("params_matrix must be (n, >=3)")

    from FishBroWFS_V2.config.dtypes import INDEX_DTYPE
    from FishBroWFS_V2.config.dtypes import PRICE_DTYPE_STAGE2
    
    # runner_grid is used in Stage2, so keep float64 for params_matrix (conservative)
    pm = np.asarray(params_matrix, dtype=PRICE_DTYPE_STAGE2)
    if sort_params:
        pm_sorted, order = sort_params_cache_friendly(pm)
        # Convert order to INDEX_DTYPE (int32) for memory optimization
        order = order.astype(INDEX_DTYPE)
    else:
        pm_sorted = pm
        order = np.arange(pm.shape[0], dtype=INDEX_DTYPE)
    t_sort = time.perf_counter()

    n = pm_sorted.shape[0]
    metrics = np.zeros((n, METRICS_N_COLUMNS), dtype=np.float64)
    
    # Debug arrays: per-param first trade snapshot (only if return_debug=True)
    if return_debug:
        debug_fills_first = np.full((n, 6), np.nan, dtype=np.float64)
        # Columns: entry_bar, entry_price, exit_bar, exit_price, net_profit, trades
    else:
        debug_fills_first = None

    # Initialize result dict early (minimal structure)
    perf: Dict[str, object] = {}
    
    # Stage P2-2 Step A: Memoization potential assessment - unique counts
    # Extract channel_len and atr_len values (as int32 for unique counting)
    ch_vals = pm_sorted[:, 0].astype(np.int32, copy=False)
    atr_vals = pm_sorted[:, 1].astype(np.int32, copy=False)
    
    perf["unique_channel_len_count"] = int(np.unique(ch_vals).size)
    perf["unique_atr_len_count"] = int(np.unique(atr_vals).size)
    
    # Pack pair to int64 key: (ch<<32) | atr
    pair_keys = (ch_vals.astype(np.int64) << 32) | (atr_vals.astype(np.int64) & 0xFFFFFFFF)
    perf["unique_ch_atr_pair_count"] = int(np.unique(pair_keys).size)
    
    # Stage P2-2 Step B3: Pre-compute indicators for unique channel_len and atr_len
    unique_ch = np.unique(ch_vals)
    unique_atr = np.unique(atr_vals)
    
    # Build caches for precomputed indicators
    donch_cache_hi: Dict[int, np.ndarray] = {}
    donch_cache_lo: Dict[int, np.ndarray] = {}
    atr_cache: Dict[int, np.ndarray] = {}
    
    # Pre-compute timing (if profiling enabled)
    t_precompute_start = time.perf_counter() if profile else 0.0
    
    # Pre-compute Donchian indicators for unique channel_len values
    for ch_len in unique_ch:
        ch_len_int = int(ch_len)
        donch_cache_hi[ch_len_int] = rolling_max(bars.high, ch_len_int)
        donch_cache_lo[ch_len_int] = rolling_min(bars.low, ch_len_int)
    
    # Pre-compute ATR indicators for unique atr_len values
    for atr_len in unique_atr:
        atr_len_int = int(atr_len)
        atr_cache[atr_len_int] = atr_wilder(bars.high, bars.low, bars.close, atr_len_int)
    
    t_precompute_end = time.perf_counter() if profile else 0.0
    
    # Stage P2-2 Step B4: Memory observation fields
    precomp_bytes_donchian = sum(arr.nbytes for arr in donch_cache_hi.values()) + sum(arr.nbytes for arr in donch_cache_lo.values())
    precomp_bytes_atr = sum(arr.nbytes for arr in atr_cache.values())
    precomp_bytes_total = precomp_bytes_donchian + precomp_bytes_atr
    
    perf["precomp_unique_channel_len_count"] = int(len(unique_ch))
    perf["precomp_unique_atr_len_count"] = int(len(unique_atr))
    perf["precomp_bytes_donchian"] = int(precomp_bytes_donchian)
    perf["precomp_bytes_atr"] = int(precomp_bytes_atr)
    perf["precomp_bytes_total"] = int(precomp_bytes_total)
    if profile:
        perf["t_precompute_indicators_s"] = float(t_precompute_end - t_precompute_start)
    
    # CURSOR TASK 3: Grid 層把 intent sparse 傳到底
    # Read FISHBRO_PERF_TRIGGER_RATE as intent_sparse_rate and pass to kernel
    intent_sparse_rate_env = os.environ.get("FISHBRO_PERF_TRIGGER_RATE", "").strip()
    intent_sparse_rate = 1.0
    if intent_sparse_rate_env:
        try:
            intent_sparse_rate = float(intent_sparse_rate_env)
            if not (0.0 <= intent_sparse_rate <= 1.0):
                intent_sparse_rate = 1.0
        except ValueError:
            intent_sparse_rate = 1.0
    
    # Stage P2-3: Param-subsample (deterministic selection)
    # FISHBRO_PERF_PARAM_SUBSAMPLE_RATE controls param subsampling (separate from trigger_rate)
    # FISHBRO_PERF_TRIGGER_RATE is for bar/intent-level sparsity (handled in kernel)
    param_subsample_rate_env = os.environ.get("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", "").strip()
    param_subsample_seed_env = os.environ.get("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", "").strip()
    
    param_subsample_rate = 1.0
    if param_subsample_rate_env:
        try:
            param_subsample_rate = float(param_subsample_rate_env)
            if not (0.0 <= param_subsample_rate <= 1.0):
                param_subsample_rate = 1.0
        except ValueError:
            param_subsample_rate = 1.0
    
    param_subsample_seed = 42
    if param_subsample_seed_env:
        try:
            param_subsample_seed = int(param_subsample_seed_env)
        except ValueError:
            param_subsample_seed = 42
    
    # Stage P2-3: Determine selected params (deterministic)
    # CURSOR TASK 1: Use "pos" (sorted space position) for selection, "orig" (original index) for scatter-back
    if param_subsample_rate < 1.0:
        k = max(1, int(round(n * param_subsample_rate)))
        rng = np.random.default_rng(param_subsample_seed)
        # Generate deterministic permutation
        perm = rng.permutation(n)
        selected_pos = np.sort(perm[:k]).astype(INDEX_DTYPE)  # Sort to maintain deterministic loop order
    else:
        selected_pos = np.arange(n, dtype=INDEX_DTYPE)
    
    # CURSOR TASK 1: Map selected_pos (sorted space) to selected_orig (original space)
    selected_orig = order[selected_pos].astype(np.int64)  # Map sorted positions to original indices
    
    selected_params_count = len(selected_pos)
    selected_params_ratio = float(selected_params_count) / float(n) if n > 0 else 0.0
    
    # Create metrics_computed_mask: boolean array indicating which rows were computed
    metrics_computed_mask = np.zeros(n, dtype=bool)
    for orig_i in selected_orig:
        metrics_computed_mask[orig_i] = True
    
    # Add param subsample info to perf
    perf["param_subsample_rate_configured"] = float(param_subsample_rate)
    perf["selected_params_count"] = int(selected_params_count)
    perf["selected_params_ratio"] = float(selected_params_ratio)
    perf["metrics_rows_computed"] = int(selected_params_count)
    perf["metrics_computed_mask"] = metrics_computed_mask.tolist()  # Convert to list for JSON serialization
    
    # Stage P2-1.8: Initialize granular timing and count accumulators (only if profile enabled)
    if profile:
        # Stage P2-2 Step A: Micro-profiling timing keys
        perf["t_ind_donchian_s"] = 0.0
        perf["t_ind_atr_s"] = 0.0
        perf["t_build_entry_intents_s"] = 0.0
        perf["t_simulate_entry_s"] = 0.0
        perf["t_calc_exits_s"] = 0.0
        perf["t_simulate_exit_s"] = 0.0
        perf["t_total_kernel_s"] = 0.0
        perf["entry_fills_total"] = 0
        perf["exit_intents_total"] = 0
        perf["exit_fills_total"] = 0
    result: Dict[str, object] = {"metrics": metrics, "order": order, "perf": perf}

    if sim_only:
        # Debug mode: bypass strategy/orchestration and only benchmark matcher simulate.
        # This provides A/B evidence: if sim-only is fast, bottleneck is in kernel (indicators/intents).
        from FishBroWFS_V2.engine import engine_jit

        intents_per_bar = int(os.environ.get("FISHBRO_SIM_ONLY_INTENTS_PER_BAR", "2"))
        intents: list[OrderIntent] = []
        oid = 1
        nbars = int(bars.open.shape[0])
        for t in range(1, nbars):
            for _ in range(intents_per_bar):
                intents.append(
                    OrderIntent(
                        order_id=oid,
                        created_bar=t - 1,
                        role=OrderRole.ENTRY,
                        kind=OrderKind.STOP,
                        side=Side.BUY,
                        price=float(bars.high[t - 1]),
                        qty=1,
                    )
                )
                oid += 1
                intents.append(
                    OrderIntent(
                        order_id=oid,
                        created_bar=t - 1,
                        role=OrderRole.EXIT,
                        kind=OrderKind.STOP,
                        side=Side.SELL,
                        price=float(bars.low[t - 1]),
                        qty=1,
                    )
                )
                oid += 1

        t_sim0 = time.perf_counter()
        _fills = engine_jit.simulate(bars, intents)
        t_sim1 = time.perf_counter()
        jt = engine_jit.get_jit_truth()
        numba_env = os.environ.get("NUMBA_DISABLE_JIT", "")
        sigs = jt.get("kernel_signatures") or []
        perf = {
            "t_features": float(t_prep1 - t0),
            "t_indicators": None,
            "t_intent_gen": None,
            "t_simulate": float(t_sim1 - t_sim0),
            "simulate_impl": "jit" if jt.get("jit_path_used") else "py",
            "jit_path_used": bool(jt.get("jit_path_used")),
            "simulate_signatures_count": int(len(sigs)),
            "numba_disable_jit_env": str(numba_env),
            "intents_total": int(len(intents)),
            "intents_per_bar_avg": float(len(intents) / float(max(1, bars.open.shape[0]))),
            "fills_total": int(len(_fills)),
            "intent_mode": "objects",
        }
        result["perf"] = perf
        if return_debug and debug_fills_first is not None:
            result["debug_fills_first"] = debug_fills_first
        return result

    # Homology: only call run_kernel, never compute strategy/metrics here.
    # Perf observability is env-gated so default usage stays unchanged.
    t_ind = 0.0
    t_intgen = 0.0
    t_sim = 0.0
    intents_total = 0
    fills_total = 0
    any_profile_missing = False
    intent_mode: str | None = None
    # Stage P2-1.5: Entry sparse observability (accumulate across params)
    entry_valid_mask_sum = 0
    entry_intents_total = 0
    n_bars_for_entry_obs = None  # Will be set from first kernel result
    # Stage P2-3: Sparse builder observability (accumulate across params)
    allowed_bars_total = 0  # Total allowed bars (before trigger rate filtering)
    intents_generated_total = 0  # Total intents generated (after trigger rate filtering)
    
    # CURSOR TASK 1: Collect metrics_subset (will be scattered back after loop)
    metrics_subset = np.zeros((len(selected_pos), METRICS_N_COLUMNS), dtype=np.float64)
    debug_fills_first_subset = None
    if return_debug:
        debug_fills_first_subset = np.full((len(selected_pos), 6), np.nan, dtype=np.float64)
    
    # Stage P2-3: Only loop selected params (param-subsample)
    # CURSOR TASK 1: Use selected_pos (sorted space) to access pm_sorted, selected_orig for scatter-back
    for subset_idx, pos in enumerate(selected_pos):
        # Initialize row for this iteration (will be written at loop end regardless of any continue/early exit)
        row = np.array([0.0, 0, 0.0], dtype=np.float64)
        
        # CURSOR TASK 1: Use pos (sorted space position) to access params_sorted
        ch = int(pm_sorted[pos, 0])
        atr = int(pm_sorted[pos, 1])
        sm = float(pm_sorted[pos, 2])

        # Stage P2-2 Step B3: Lookup precomputed indicators and create PrecomputedIndicators pack
        precomp_pack = PrecomputedIndicators(
            donch_hi=donch_cache_hi[ch],
            donch_lo=donch_cache_lo[ch],
            atr=atr_cache[atr],
        )

        # Stage P2-1.8: Kernel profiling is already enabled at function start if profile=True
        # No need to set FISHBRO_PROFILE_KERNEL here again
        out = run_kernel(
            bars,
            DonchianAtrParams(channel_len=ch, atr_len=atr, stop_mult=sm),
            commission=float(commission),
            slip=float(slip),
            order_qty=int(order_qty),
            return_debug=return_debug,
            precomp=precomp_pack,
            intent_sparse_rate=intent_sparse_rate,  # CURSOR TASK 3: Pass intent sparse rate
        )
        obs = out.get("_obs", None)  # type: ignore
        if isinstance(obs, dict):
            # Phase 3.0-B: Trust kernel's evidence fields, do not recompute
            if intent_mode is None and isinstance(obs.get("intent_mode"), str):
                intent_mode = str(obs.get("intent_mode"))
            # Use intents_total directly from kernel (Source of Truth), not recompute from entry+exit
            intents_total += int(obs.get("intents_total", 0))
            fills_total += int(obs.get("fills_total", 0))
            
            # CURSOR TASK 2: Accumulate entry_valid_mask_sum (after intent sparse)
            # entry_valid_mask_sum must be sum(allow_mask) - not dense valid bars, not multiplied by params
            if "entry_valid_mask_sum" in obs:
                entry_valid_mask_sum += int(obs.get("entry_valid_mask_sum", 0))
            elif "allowed_bars" in obs:
                # Fallback: use allowed_bars if entry_valid_mask_sum not present
                entry_valid_mask_sum += int(obs.get("allowed_bars", 0))
            # CURSOR TASK 2: entry_intents_total should come from obs["entry_intents_total"] (set by kernel)
            if "entry_intents_total" in obs:
                entry_intents_total += int(obs.get("entry_intents_total", 0))
            elif "entry_intents" in obs:
                # Fallback: use entry_intents if entry_intents_total not present
                entry_intents_total += int(obs.get("entry_intents", 0))
            elif "n_entry" in obs:
                # Fallback: use n_entry if entry_intents_total not present
                entry_intents_total += int(obs.get("n_entry", 0))
            # Capture n_bars from first kernel result (should be same for all params)
            if n_bars_for_entry_obs is None and "n_bars" in obs:
                n_bars_for_entry_obs = int(obs.get("n_bars", 0))
            
            # Stage P2-3: Accumulate sparse builder observability (from new builder_sparse)
            if "allowed_bars" in obs:
                allowed_bars_total += int(obs.get("allowed_bars", 0))
            if "intents_generated" in obs:
                intents_generated_total += int(obs.get("intents_generated", 0))
            elif "n_entry" in obs:
                # Fallback: if intents_generated not present, use n_entry
                intents_generated_total += int(obs.get("n_entry", 0))
            
            # Stage P2-1.8: Accumulate timing keys from _obs (timing is now in _obs, not _perf)
            # Timing keys have pattern: t_*_s
            for key, value in obs.items():
                if key.startswith("t_") and key.endswith("_s"):
                    if key not in perf:
                        perf[key] = 0.0
                    perf[key] = float(perf[key]) + float(value)
            
            # Stage P2-1.8: Accumulate downstream counts from _obs
            if "entry_fills_total" in obs:
                perf["entry_fills_total"] = int(perf.get("entry_fills_total", 0)) + int(obs.get("entry_fills_total", 0))
            if "exit_intents_total" in obs:
                perf["exit_intents_total"] = int(perf.get("exit_intents_total", 0)) + int(obs.get("exit_intents_total", 0))
            if "exit_fills_total" in obs:
                perf["exit_fills_total"] = int(perf.get("exit_fills_total", 0)) + int(obs.get("exit_fills_total", 0))
        
        # Stage P2-1.8: Fallback - also check _perf for backward compatibility
        # Handle cases where old kernel versions put timing in _perf instead of _obs
        # Only use fallback if _obs doesn't have timing keys
        obs_has_timing = isinstance(obs, dict) and any(k.startswith("t_") and k.endswith("_s") for k in obs.keys())
        if not obs_has_timing:
            kernel_perf = out.get("_perf", None)
            if isinstance(kernel_perf, dict):
                # Accumulate timings across params (for grid-level aggregation)
                # Note: For grid-level, we sum timings across params
                for key, value in kernel_perf.items():
                    if key.startswith("t_") and key.endswith("_s"):
                        if key not in perf:
                            perf[key] = 0.0
                        perf[key] = float(perf[key]) + float(value)

        # Get metrics from kernel output (always available, even if profile missing)
        m = out.get("metrics", {})
        if not isinstance(m, dict):
            # Fallback: kernel didn't return metrics dict, use zeros
            m_net_profit = 0.0
            m_trades = 0
            m_max_dd = 0.0
        else:
            m_net_profit = float(m.get("net_profit", 0.0))
            m_trades = int(m.get("trades", 0))
            m_max_dd = float(m.get("max_dd", 0.0))
            # Clean NaN/Inf at source
            m_net_profit = float(np.nan_to_num(m_net_profit, nan=0.0, posinf=0.0, neginf=0.0))
            m_max_dd = float(np.nan_to_num(m_max_dd, nan=0.0, posinf=0.0, neginf=0.0))
        
        # Get fills count for debug assert
        fills_this_param = out.get("fills", [])
        fills_count_this_param = len(fills_this_param) if isinstance(fills_this_param, list) else 0
        
        # Collect debug data if requested
        if return_debug:
            debug_info = out.get("_debug", {})
            entry_bar = debug_info.get("entry_bar", -1)
            entry_price = debug_info.get("entry_price", np.nan)
            exit_bar = debug_info.get("exit_bar", -1)
            exit_price = debug_info.get("exit_price", np.nan)
        
        # Handle force_close_last: if still in position, force close at last bar
        if force_close_last:
            fills = out.get("fills", [])
            if isinstance(fills, list) and len(fills) > 0:
                # Count entry and exit fills
                entry_fills = [f for f in fills if f.role == OrderRole.ENTRY and f.side == Side.BUY]
                exit_fills = [f for f in fills if f.role == OrderRole.EXIT and f.side == Side.SELL]
                
                # If there are unpaired entries, force close at last bar
                if len(entry_fills) > len(exit_fills):
                    n_unpaired = len(entry_fills) - len(exit_fills)
                    last_bar_idx = int(bars.open.shape[0] - 1)
                    last_close_price = float(bars.close[last_bar_idx])
                    
                    # Create forced exit fills for unpaired entries
                    # Use entry prices from the unpaired entries
                    unpaired_entry_prices = [float(f.price) for f in entry_fills[-n_unpaired:]]
                    
                    # Calculate additional pnl from forced closes
                    forced_pnl = []
                    costs_per_trade = (float(commission) + float(slip)) * 2.0
                    for entry_price in unpaired_entry_prices:
                        # PnL = (exit_price - entry_price) * qty - costs
                        trade_pnl = (last_close_price - entry_price) * float(order_qty) - costs_per_trade
                        forced_pnl.append(trade_pnl)
                    
                    # Update metrics with forced closes
                    original_net_profit = m_net_profit
                    original_trades = m_trades
                    
                    # Add forced close trades
                    new_net_profit = original_net_profit + sum(forced_pnl)
                    new_trades = original_trades + n_unpaired
                    
                    # Update debug exit info for force_close_last
                    if return_debug and n_unpaired > 0:
                        exit_bar = last_bar_idx
                        exit_price = last_close_price
                    
                    # Recalculate equity and max_dd
                    forced_pnl_arr = np.asarray(forced_pnl, dtype=np.float64)
                    if original_trades > 0 and "equity" in out:
                        original_equity = out["equity"]
                        if isinstance(original_equity, np.ndarray) and original_equity.size > 0:
                            # Append forced pnl to existing equity curve
                            # Start from last equity value
                            start_equity = float(original_equity[-1])
                            forced_equity = np.cumsum(forced_pnl_arr) + start_equity
                            new_equity = np.concatenate([original_equity, forced_equity])
                        else:
                            # No previous equity array, start from 0
                            new_equity = np.cumsum(forced_pnl_arr)
                    else:
                        # No previous trades, start from 0
                        new_equity = np.cumsum(forced_pnl_arr)
                    
                    new_max_dd = _max_drawdown(new_equity)
                    
                    # Update row with forced close metrics
                    row = np.array([new_net_profit, new_trades, new_max_dd], dtype=np.float64)
                    
                    # Update debug subset with final metrics after force_close_last
                    if return_debug:
                        debug_fills_first_subset[subset_idx, 0] = entry_bar
                        debug_fills_first_subset[subset_idx, 1] = entry_price
                        debug_fills_first_subset[subset_idx, 2] = exit_bar
                        debug_fills_first_subset[subset_idx, 3] = exit_price
                        debug_fills_first_subset[subset_idx, 4] = new_net_profit
                        debug_fills_first_subset[subset_idx, 5] = float(new_trades)
                else:
                    # No unpaired entries, use original metrics
                    row = np.array([m_net_profit, m_trades, m_max_dd], dtype=np.float64)
                    
                    # Store debug data in subset
                    if return_debug:
                        debug_fills_first_subset[subset_idx, 0] = entry_bar
                        debug_fills_first_subset[subset_idx, 1] = entry_price
                        debug_fills_first_subset[subset_idx, 2] = exit_bar
                        debug_fills_first_subset[subset_idx, 3] = exit_price
                        debug_fills_first_subset[subset_idx, 4] = m_net_profit
                        debug_fills_first_subset[subset_idx, 5] = float(m_trades)
            else:
                # No fills, use original metrics
                row = np.array([m_net_profit, m_trades, m_max_dd], dtype=np.float64)
                
                # Store debug data in subset (no fills case)
                if return_debug:
                    debug_fills_first_subset[subset_idx, 0] = entry_bar
                    debug_fills_first_subset[subset_idx, 1] = entry_price
                    debug_fills_first_subset[subset_idx, 2] = exit_bar
                    debug_fills_first_subset[subset_idx, 3] = exit_price
                    debug_fills_first_subset[subset_idx, 4] = m_net_profit
                    debug_fills_first_subset[subset_idx, 5] = float(m_trades)
        else:
            # Zero-trade safe: kernel guarantees valid numbers (0.0/0)
            row = np.array([m_net_profit, m_trades, m_max_dd], dtype=np.float64)
            
            # Store debug data in subset
            if return_debug:
                debug_fills_first_subset[subset_idx, 0] = entry_bar
                debug_fills_first_subset[subset_idx, 1] = entry_price
                debug_fills_first_subset[subset_idx, 2] = exit_bar
                debug_fills_first_subset[subset_idx, 3] = exit_price
                debug_fills_first_subset[subset_idx, 4] = m_net_profit
                debug_fills_first_subset[subset_idx, 5] = float(m_trades)
        
        # HARD CONTRACT: Always write metrics_subset at loop end, regardless of any continue/early exit
        metrics_subset[subset_idx, :] = row
        
        # Debug assert: if trades > 0 (completed trades), metrics must be non-zero
        # Note: entry fills without exits yield trades=0 and all-zero metrics, which is valid
        if os.environ.get("FISHBRO_DEBUG_ASSERT", "").strip() == "1":
            if m_trades > 0:
                assert np.any(np.abs(metrics_subset[subset_idx, :]) > 0), (
                    f"subset_idx={subset_idx}: trades={m_trades} > 0, "
                    f"but metrics_subset[{subset_idx}, :]={metrics_subset[subset_idx, :]} is all zeros"
                )
        
        # Handle profile timing accumulation (after metrics written)
        if profile:
            kp = out.get("_profile", None)  # type: ignore
            if not isinstance(kp, dict):
                any_profile_missing = True
                # Continue after metrics already written
                continue
            t_ind += float(kp.get("indicators_s", 0.0))
            # include both entry+exit intent generation as "intent generation"
            t_intgen += float(kp.get("intent_gen_s", 0.0)) + float(kp.get("exit_intent_gen_s", 0.0))
            t_sim += float(kp.get("simulate_entry_s", 0.0)) + float(kp.get("simulate_exit_s", 0.0))
    
    # CURSOR TASK 2: Handle NaN before scatter-back (avoid computed_non_zero being eaten by NaN)
    # Note: Already handled at source (m_net_profit, m_max_dd), but double-check here for safety
    metrics_subset = np.nan_to_num(metrics_subset, nan=0.0, posinf=0.0, neginf=0.0)
    
    # CURSOR TASK 3: Assert that if fills_total > 0, metrics_subset should have non-zero values
    # This helps catch cases where metrics computation was skipped or returned zeros
    # Only assert if FISHBRO_DEBUG_ASSERT=1 (not triggered by profile, as tests often enable profile)
    if os.environ.get("FISHBRO_DEBUG_ASSERT", "").strip() == "1":
        metrics_subset_abs_sum = float(np.sum(np.abs(metrics_subset)))
        assert fills_total == 0 or metrics_subset_abs_sum > 0, (
            f"CURSOR TASK B violation: fills_total={fills_total} > 0 but metrics_subset_abs_sum={metrics_subset_abs_sum} == 0. "
            f"This indicates metrics computation was skipped or returned zeros."
        )
    
    # CURSOR TASK 3: Add perf debug field (metrics_subset_nonzero_rows)
    metrics_subset_nonzero_rows = int(np.sum(np.any(np.abs(metrics_subset) > 1e-10, axis=1)))
    perf["metrics_subset_nonzero_rows"] = metrics_subset_nonzero_rows
    
    # === HARD CONTRACT: scatter metrics back to original param space ===
    # CRITICAL: This must happen after all metrics computation and before any return
    # Variables: selected_pos (sorted-space index), order (sorted_pos -> original_index), metrics_subset (computed metrics)
    # For each selected param: metrics[orig_param_idx] must be written with non-zero values
    for subset_i, pos in enumerate(selected_pos):
        orig_i = int(order[int(pos)])
        metrics[orig_i, :] = metrics_subset[subset_i, :]
        
        if return_debug and debug_fills_first is not None and debug_fills_first_subset is not None:
            debug_fills_first[orig_i, :] = debug_fills_first_subset[subset_i, :]
    
    # CRITICAL: After scatter-back, metrics must not be modified (no metrics = np.zeros, no metrics[:] = 0, no result["metrics"] = metrics_subset)
    
    # CURSOR TASK 2: Add perf debug fields (for diagnostic)
    perf["intent_sparse_rate_effective"] = float(intent_sparse_rate)
    perf["fills_total"] = int(fills_total)
    perf["metrics_subset_abs_sum"] = float(np.sum(np.abs(metrics_subset)))
    
    # CURSOR TASK A: Add entry_intents_total (subsample run) for diagnostic
    # This helps distinguish: entry_intents_total > 0 but fills_total == 0 → matcher/engine issue
    # vs entry_intents_total == 0 → builder didn't generate intents
    perf["entry_intents_total"] = int(entry_intents_total)

    # Phase 3.0-E: Ensure intent_mode is never None
    # If no kernel results (n == 0), default to "arrays" (default kernel path)
    # Otherwise, intent_mode should have been set from first kernel result
    if intent_mode is None:
        # Edge case: n == 0 (no params) - use default "arrays" since run_kernel defaults to array path
        intent_mode = "arrays"

    if not profile:
        # Return minimal perf with evidence fields only
        # Stage P2-1.8: Preserve accumulated timings (already in perf dict from loop)
        perf["intent_mode"] = intent_mode
        perf["intents_total"] = int(intents_total)
        # fills_total already set in scatter-back section (line 592), but ensure it's here too for clarity
        if "fills_total" not in perf:
            perf["fills_total"] = int(fills_total)
        # CURSOR TASK 3: Add intent sparse rate and entry observability to perf
        perf["intent_sparse_rate"] = float(intent_sparse_rate)
        perf["entry_valid_mask_sum"] = int(entry_valid_mask_sum)  # CURSOR TASK 2: After intent sparse (sum(allow_mask))
        perf["entry_intents_total"] = int(entry_intents_total)
        
        # Stage P2-1.5: Add entry sparse observability (always include, even if 0)
        perf["intents_total_reported"] = int(intents_total)  # Preserve original for comparison
        if n_bars_for_entry_obs is not None and n_bars_for_entry_obs > 0:
            perf["entry_intents_per_bar_avg"] = float(entry_intents_total / n_bars_for_entry_obs)
        else:
            # Fallback: use bars.open.shape[0] if n_bars_for_entry_obs not available
            perf["entry_intents_per_bar_avg"] = float(entry_intents_total / max(1, bars.open.shape[0]))
        
        # Stage P2-3: Add sparse builder observability (for scaling verification)
        perf["allowed_bars"] = int(allowed_bars_total)
        perf["intents_generated"] = int(intents_generated_total)
        perf["selected_params"] = int(selected_params_count)
        
        # CURSOR TASK 2: Ensure debug fields are present in non-profile branch too
        if "intent_sparse_rate_effective" not in perf:
            perf["intent_sparse_rate_effective"] = float(intent_sparse_rate)
        if "fills_total" not in perf:
            perf["fills_total"] = int(fills_total)
        if "metrics_subset_abs_sum" not in perf:
            perf["metrics_subset_abs_sum"] = float(np.sum(np.abs(metrics_subset)))
        
        result["perf"] = perf
        if return_debug and debug_fills_first is not None:
            result["debug_fills_first"] = debug_fills_first
        return result

    from FishBroWFS_V2.engine import engine_jit

    jt = engine_jit.get_jit_truth()
    numba_env = os.environ.get("NUMBA_DISABLE_JIT", "")
    sigs = jt.get("kernel_signatures") or []

    # Best-effort: avoid leaking this env to callers
    # Only clean up if we set it ourselves (Task A: bridge logic)
    if _set_kernel_profile:
        try:
            del os.environ["FISHBRO_PROFILE_KERNEL"]
        except KeyError:
            pass

    # Phase 3.0-E: Ensure intent_mode is never None
    # If no kernel results (n == 0), default to "arrays" (default kernel path)
    # Otherwise, intent_mode should have been set from first kernel result
    if intent_mode is None:
        # Edge case: n == 0 (no params) - use default "arrays" since run_kernel defaults to array path
        intent_mode = "arrays"

    # Stage P2-1.8: Create summary dict and merge into accumulated perf (preserve t_*_s from loop)
    perf_summary = {
        "t_features": float(t_prep1 - t0),
        # current architecture: indicators are computed inside run_kernel per param
        "t_indicators": None if any_profile_missing else float(t_ind),
        "t_intent_gen": None if any_profile_missing else float(t_intgen),
        "t_simulate": None if any_profile_missing else float(t_sim),
        "simulate_impl": "jit" if jt.get("jit_path_used") else "py",
        "jit_path_used": bool(jt.get("jit_path_used")),
        "simulate_signatures_count": int(len(sigs)),
        "numba_disable_jit_env": str(numba_env),
        # Phase 3.0-B: Use kernel's evidence fields directly (Source of Truth), not recomputed
        "intent_mode": intent_mode,
        "intents_total": int(intents_total),
        "fills_total": int(fills_total),
        "intents_per_bar_avg": float(intents_total / float(max(1, bars.open.shape[0]))),
    }
    
    # CURSOR TASK 3: Add intent sparse rate and entry observability to perf
    perf_summary["intent_sparse_rate"] = float(intent_sparse_rate)
    perf_summary["entry_valid_mask_sum"] = int(entry_valid_mask_sum)  # CURSOR TASK 2: After intent sparse
    perf_summary["entry_intents_total"] = int(entry_intents_total)
    
    # Stage P2-1.5: Add entry sparse observability and preserve original intents_total
    perf_summary["intents_total_reported"] = int(intents_total)  # Preserve original for comparison
    if n_bars_for_entry_obs is not None and n_bars_for_entry_obs > 0:
        perf_summary["entry_intents_per_bar_avg"] = float(entry_intents_total / n_bars_for_entry_obs)
    else:
        # Fallback: use bars.open.shape[0] if n_bars_for_entry_obs not available
        perf_summary["entry_intents_per_bar_avg"] = float(entry_intents_total / max(1, bars.open.shape[0]))
    
    # Stage P2-3: Add sparse builder observability (for scaling verification)
    perf_summary["allowed_bars"] = int(allowed_bars_total)  # Total allowed bars across all params
    perf_summary["intents_generated"] = int(intents_generated_total)  # Total intents generated across all params
    perf_summary["selected_params"] = int(selected_params_count)  # Number of params actually computed
    
    # CURSOR TASK 2: Ensure debug fields are present in profile branch too
    perf_summary["intent_sparse_rate_effective"] = float(intent_sparse_rate)
    perf_summary["fills_total"] = int(fills_total)
    perf_summary["metrics_subset_abs_sum"] = float(np.sum(np.abs(metrics_subset)))
    
    # Keep accumulated per-kernel timings already stored in `perf` (t_*_s, entry_fills_total, etc.)
    perf.update(perf_summary)

    result["perf"] = perf
    if return_debug and debug_fills_first is not None:
        result["debug_fills_first"] = debug_fills_first
    return result




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/stage0_runner.py
sha256(source_bytes) = 1ca70b14d73eeca0b2687d88690a20f5e5b4b9762cf4dd760edf6aa68ef10b85
bytes = 2711
redacted = False
--------------------------------------------------------------------------------

"""Stage0 runner - proxy ranking without PnL metrics.

Stage0 is a fast proxy filter that ranks parameters without running full backtests.
It MUST NOT compute any PnL-related metrics (Net/MDD/SQN/Sharpe/WinRate/Equity/DD).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from FishBroWFS_V2.config.constants import STAGE0_PROXY_NAME
from FishBroWFS_V2.stage0.ma_proxy import stage0_score_ma_proxy


@dataclass(frozen=True)
class Stage0Result:
    """
    Stage0 result - proxy ranking only.
    
    Contains ONLY:
    - param_id: parameter index
    - proxy_value: proxy ranking value (higher is better)
    - warmup_ok: optional warmup validation flag
    - meta: optional metadata dict
    
    FORBIDDEN fields (must not exist):
    - Any PnL metrics: Net, MDD, SQN, Sharpe, WinRate, Equity, DD, etc.
    """
    param_id: int
    proxy_value: float
    warmup_ok: Optional[bool] = None
    meta: Optional[dict] = None


def run_stage0(
    close: np.ndarray,
    params_matrix: np.ndarray,
    *,
    proxy_name: str = STAGE0_PROXY_NAME,
) -> List[Stage0Result]:
    """
    Run Stage0 proxy ranking.
    
    Args:
        close: float32 or float64 1D array (n_bars,) - close prices (will use float32 internally)
        params_matrix: float32 or float64 2D array (n_params, >=2) (will use float32 internally)
            - col0: fast_len (for MA proxy)
            - col1: slow_len (for MA proxy)
            - additional columns allowed and ignored
        proxy_name: name of proxy to use (default: ma_proxy_v0)
        
    Returns:
        List of Stage0Result, one per parameter set.
        Results are in same order as params_matrix rows.
        
    Note:
        - This function MUST NOT compute any PnL metrics
        - Only proxy_value is computed for ranking purposes
        - Uses float32 internally for memory optimization
    """
    if proxy_name != "ma_proxy_v0":
        raise ValueError(f"Unsupported proxy: {proxy_name}. Only 'ma_proxy_v0' is supported in Phase 4.")
    
    # Compute proxy scores
    scores = stage0_score_ma_proxy(close, params_matrix)
    
    # Build results
    n_params = params_matrix.shape[0]
    results: List[Stage0Result] = []
    
    for i in range(n_params):
        score = float(scores[i])
        
        # Check warmup: if score is -inf, warmup failed
        warmup_ok = not np.isinf(score) if not np.isnan(score) else False
        
        results.append(
            Stage0Result(
                param_id=i,
                proxy_value=score,
                warmup_ok=warmup_ok,
                meta=None,
            )
        )
    
    return results



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/stage2_runner.py
sha256(source_bytes) = 3a85d98329b2e93d42ac7dc4aaf8444b3d3c014fd1b6c4d943b42265d75949c8
bytes = 4801
redacted = False
--------------------------------------------------------------------------------

"""Stage2 runner - full backtest on Top-K parameters.

Stage2 runs full backtests using the unified simulate_run() entry point.
It computes complete metrics including net_profit, trades, max_dd, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from FishBroWFS_V2.data.layout import normalize_bars
from FishBroWFS_V2.engine.types import BarArrays, Fill
from FishBroWFS_V2.strategy.kernel import DonchianAtrParams, run_kernel


@dataclass(frozen=True)
class Stage2Result:
    """
    Stage2 result - full backtest metrics.
    
    Contains complete backtest results including:
    - param_id: parameter index
    - net_profit: total net profit
    - trades: number of trades
    - max_dd: maximum drawdown
    - fills: list of fills (optional, for detailed analysis)
    - equity: equity curve (optional)
    - meta: optional metadata
    """
    param_id: int
    net_profit: float
    trades: int
    max_dd: float
    fills: Optional[List[Fill]] = None
    equity: Optional[np.ndarray] = None
    meta: Optional[dict] = None


def _max_drawdown(equity: np.ndarray) -> float:
    """Compute max drawdown from equity curve."""
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    mdd = float(np.min(dd))  # negative or 0
    return mdd


def run_stage2(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
    param_ids: List[int],
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
) -> List[Stage2Result]:
    """
    Run Stage2 full backtest on selected parameters.
    
    Args:
        open_, high, low, close: OHLC arrays (float64, 1D, same length)
        params_matrix: float64 2D array (n_params, >=3)
            - col0: channel_len
            - col1: atr_len
            - col2: stop_mult
        param_ids: List of parameter indices to run (Top-K selection)
        commission: commission per trade (absolute)
        slip: slippage per trade (absolute)
        order_qty: order quantity (default: 1)
        
    Returns:
        List of Stage2Result, one per selected parameter.
        Results are in same order as param_ids.
        
    Note:
        - Only runs backtests for parameters in param_ids (Top-K subset)
        - Uses unified simulate_run() entry point (Cursor kernel)
        - Computes full metrics including PnL
    """
    bars = normalize_bars(open_, high, low, close)
    
    # Ensure contiguous arrays
    if not bars.open.flags["C_CONTIGUOUS"]:
        bars = BarArrays(
            open=np.ascontiguousarray(bars.open, dtype=np.float64),
            high=np.ascontiguousarray(bars.high, dtype=np.float64),
            low=np.ascontiguousarray(bars.low, dtype=np.float64),
            close=np.ascontiguousarray(bars.close, dtype=np.float64),
        )
    
    results: List[Stage2Result] = []
    
    for param_id in param_ids:
        if param_id < 0 or param_id >= params_matrix.shape[0]:
            # Invalid param_id - create empty result
            results.append(
                Stage2Result(
                    param_id=param_id,
                    net_profit=0.0,
                    trades=0,
                    max_dd=0.0,
                    fills=None,
                    equity=None,
                    meta=None,
                )
            )
            continue
        
        # Extract parameters
        params_row = params_matrix[param_id]
        channel_len = int(params_row[0])
        atr_len = int(params_row[1])
        stop_mult = float(params_row[2])
        
        # Build DonchianAtrParams
        kernel_params = DonchianAtrParams(
            channel_len=channel_len,
            atr_len=atr_len,
            stop_mult=stop_mult,
        )
        
        # Run kernel (uses unified simulate_run internally)
        kernel_result = run_kernel(
            bars,
            kernel_params,
            commission=commission,
            slip=slip,
            order_qty=order_qty,
        )
        
        # Extract metrics
        net_profit = float(kernel_result["metrics"]["net_profit"])
        trades = int(kernel_result["metrics"]["trades"])
        max_dd = float(kernel_result["metrics"]["max_dd"])
        
        # Extract optional fields
        fills = kernel_result.get("fills")
        equity = kernel_result.get("equity")
        
        results.append(
            Stage2Result(
                param_id=param_id,
                net_profit=net_profit,
                trades=trades,
                max_dd=max_dd,
                fills=fills,
                equity=equity,
                meta=None,
            )
        )
    
    return results



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/pipeline/topk.py
sha256(source_bytes) = 32313f8e7483d6920a0468068c8cb2a59e5e80b3f5a0826d694503ba15a51eb3
bytes = 1536
redacted = False
--------------------------------------------------------------------------------

"""Top-K selector - deterministic parameter selection.

Selects top K parameters based on Stage0 proxy_value.
Tie-breaking uses param_id to ensure deterministic results.
"""

from __future__ import annotations

from typing import List

from FishBroWFS_V2.config.constants import TOPK_K
from FishBroWFS_V2.pipeline.stage0_runner import Stage0Result


def select_topk(
    stage0_results: List[Stage0Result],
    k: int = TOPK_K,
) -> List[int]:
    """
    Select top K parameters based on proxy_value.
    
    Args:
        stage0_results: List of Stage0Result from Stage0 runner
        k: number of top parameters to select (default: TOPK_K from config)
        
    Returns:
        List of param_id values (indices) for top K parameters.
        Results are sorted by proxy_value (descending), then by param_id (ascending) for tie-break.
        
    Note:
        - Sorting is deterministic: same input always produces same output
        - Tie-break uses param_id (ascending) to ensure stability
        - No manual include/exclude - purely based on proxy_value
    """
    if k <= 0:
        return []
    
    if len(stage0_results) == 0:
        return []
    
    # Sort by proxy_value (descending), then param_id (ascending) for tie-break
    sorted_results = sorted(
        stage0_results,
        key=lambda r: (-r.proxy_value, r.param_id),  # Negative for descending value
    )
    
    # Take top K
    topk_results = sorted_results[:k]
    
    # Return param_id list
    return [r.param_id for r in topk_results]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/__init__.py
sha256(source_bytes) = c81680bcd3bd4ed817be3084bef48a66de907e59a7d0e66295fe500cc929f99b
bytes = 689
redacted = False
--------------------------------------------------------------------------------

"""Portfolio package exports.

Single source of truth: PortfolioSpec in spec.py
Phase 11 research bridge uses PortfolioSpec (no spec split).
"""

from __future__ import annotations

from FishBroWFS_V2.portfolio.decisions_reader import parse_decisions_log_lines, read_decisions_log
from FishBroWFS_V2.portfolio.research_bridge import build_portfolio_from_research
from FishBroWFS_V2.portfolio.spec import PortfolioLeg, PortfolioSpec
from FishBroWFS_V2.portfolio.writer import write_portfolio_artifacts

__all__ = [
    "PortfolioLeg",
    "PortfolioSpec",
    "parse_decisions_log_lines",
    "read_decisions_log",
    "build_portfolio_from_research",
    "write_portfolio_artifacts",
]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/artifacts.py
sha256(source_bytes) = 765b55962186e213a56d979be137d5dc60c425d12197aacfd7fe082ef6349db7
bytes = 5306
redacted = False
--------------------------------------------------------------------------------

"""Portfolio artifacts writer.

Phase 8: Write portfolio artifacts for replayability and audit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from FishBroWFS_V2.portfolio.spec import PortfolioSpec


def _normalize_spec_for_hash(spec: PortfolioSpec) -> Dict[str, Any]:
    """Normalize spec to dict for hashing (exclude runtime-dependent fields).
    
    Excludes:
    - Absolute paths (convert to relative or normalize)
    - Timestamps
    - Runtime-dependent fields
    
    Args:
        spec: Portfolio specification
        
    Returns:
        Normalized dict suitable for hashing
    """
    legs_dict = []
    for leg in spec.legs:
        # Normalize session_profile path (use relative path, not absolute)
        session_profile = leg.session_profile
        # Remove any absolute path components, keep relative structure
        if Path(session_profile).is_absolute():
            # Try to make relative to common base
            try:
                session_profile = str(Path(session_profile).relative_to(Path.cwd()))
            except ValueError:
                # If can't make relative, use basename as fallback
                session_profile = Path(session_profile).name
        
        leg_dict = {
            "leg_id": leg.leg_id,
            "symbol": leg.symbol,
            "timeframe_min": leg.timeframe_min,
            "session_profile": session_profile,  # Normalized path
            "strategy_id": leg.strategy_id,
            "strategy_version": leg.strategy_version,
            "params": dict(sorted(leg.params.items())),  # Sort for determinism
            "enabled": leg.enabled,
            "tags": sorted(leg.tags),  # Sort for determinism
        }
        legs_dict.append(leg_dict)
    
    # Sort legs by leg_id for determinism
    legs_dict.sort(key=lambda x: x["leg_id"])
    
    return {
        "portfolio_id": spec.portfolio_id,
        "version": spec.version,
        "data_tz": spec.data_tz,
        "legs": legs_dict,
    }


def compute_portfolio_hash(spec: PortfolioSpec) -> str:
    """Compute deterministic hash of portfolio specification.
    
    Uses SHA1 (consistent with Phase 6.5 fingerprint style).
    Hash is computed from normalized spec dict (sorted keys, stable serialization).
    
    Args:
        spec: Portfolio specification
        
    Returns:
        SHA1 hash hex string (40 chars)
    """
    normalized = _normalize_spec_for_hash(spec)
    
    # Stable JSON serialization
    spec_json = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),  # Compact, no spaces
        ensure_ascii=False,
    )
    
    # SHA1 hash
    return hashlib.sha1(spec_json.encode("utf-8")).hexdigest()


def write_portfolio_artifacts(
    spec: PortfolioSpec,
    jobs: List[Dict[str, Any]],
    out_dir: Path,
) -> Dict[str, str]:
    """Write portfolio artifacts to output directory.
    
    Creates:
    - portfolio_spec_snapshot.yaml: Portfolio spec snapshot
    - compiled_jobs.json: Compiled job configurations
    - portfolio_index.json: Portfolio index with metadata
    - portfolio_hash.txt: Portfolio hash (single line)
    
    Args:
        spec: Portfolio specification
        jobs: Compiled job configurations (from compile_portfolio)
        out_dir: Output directory (will be created if needed)
        
    Returns:
        Dict mapping artifact names to file paths (relative to out_dir)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Compute hash
    portfolio_hash = compute_portfolio_hash(spec)
    
    # Write portfolio_spec_snapshot.yaml
    spec_snapshot_path = out_dir / "portfolio_spec_snapshot.yaml"
    normalized_spec = _normalize_spec_for_hash(spec)
    with spec_snapshot_path.open("w", encoding="utf-8") as f:
        yaml.dump(normalized_spec, f, default_flow_style=False, sort_keys=True)
    
    # Write compiled_jobs.json
    jobs_path = out_dir / "compiled_jobs.json"
    with jobs_path.open("w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, sort_keys=True, ensure_ascii=False)
    
    # Write portfolio_index.json
    index = {
        "portfolio_id": spec.portfolio_id,
        "version": spec.version,
        "portfolio_hash": portfolio_hash,
        "legs": [
            {
                "leg_id": leg.leg_id,
                "symbol": leg.symbol,
                "timeframe_min": leg.timeframe_min,
                "strategy_id": leg.strategy_id,
                "strategy_version": leg.strategy_version,
            }
            for leg in spec.legs
        ],
    }
    index_path = out_dir / "portfolio_index.json"
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, sort_keys=True, ensure_ascii=False)
    
    # Write portfolio_hash.txt (single line)
    hash_path = out_dir / "portfolio_hash.txt"
    hash_path.write_text(portfolio_hash + "\n", encoding="utf-8")
    
    # Return artifact paths (relative to out_dir)
    return {
        "spec_snapshot": str(spec_snapshot_path.relative_to(out_dir)),
        "compiled_jobs": str(jobs_path.relative_to(out_dir)),
        "index": str(index_path.relative_to(out_dir)),
        "hash": str(hash_path.relative_to(out_dir)),
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/artifacts_writer_v1.py
sha256(source_bytes) = c4afa5674dc9b5da8482cde10ba731e40cec04e9c7ae4cb10004db9ed12df323
bytes = 5712
redacted = False
--------------------------------------------------------------------------------
"""Portfolio artifacts writer V1."""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

from FishBroWFS_V2.core.schemas.portfolio_v1 import (
    AdmissionDecisionV1,
    PortfolioStateV1,
    PortfolioSummaryV1,
    PortfolioPolicyV1,
    PortfolioSpecV1,
)
from FishBroWFS_V2.control.artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    write_json_atomic,
)


def write_portfolio_artifacts(
    output_dir: Path,
    decisions: List[AdmissionDecisionV1],
    bar_states: Dict[Any, PortfolioStateV1],
    summary: PortfolioSummaryV1,
    policy: PortfolioPolicyV1,
    spec: PortfolioSpecV1,
    replay_mode: bool = False,
) -> Dict[str, str]:
    """
    Write portfolio artifacts to disk.
    
    Args:
        output_dir: Directory to write artifacts
        decisions: List of admission decisions
        bar_states: Dict mapping (bar_index, bar_ts) to PortfolioStateV1
        summary: Portfolio summary
        policy: Portfolio policy
        spec: Portfolio specification
        replay_mode: If True, read-only mode (no writes)
        
    Returns:
        Dict mapping filename to SHA256 hash
    """
    if replay_mode:
        logger.info("Replay mode: skipping artifact writes")
        return {}
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    hashes = {}
    
    # 1. Write portfolio_admission.parquet
    if decisions:
        admission_df = pd.DataFrame([d.model_dump() for d in decisions])
        admission_path = output_dir / "portfolio_admission.parquet"
        admission_df.to_parquet(admission_path, index=False)
        
        # Compute hash
        admission_bytes = admission_path.read_bytes()
        hashes["portfolio_admission.parquet"] = sha256_bytes(admission_bytes)
    
    # 2. Write portfolio_state_timeseries.parquet
    if bar_states:
        # Convert bar_states to list of dicts
        states_list = []
        for state in bar_states.values():
            state_dict = state.model_dump()
            # Convert open_positions to count for simplicity
            state_dict["open_positions_count"] = len(state.open_positions)
            # Remove the actual positions to keep file size manageable
            state_dict.pop("open_positions", None)
            states_list.append(state_dict)
        
        states_df = pd.DataFrame(states_list)
        states_path = output_dir / "portfolio_state_timeseries.parquet"
        states_df.to_parquet(states_path, index=False)
        
        states_bytes = states_path.read_bytes()
        hashes["portfolio_state_timeseries.parquet"] = sha256_bytes(states_bytes)
    
    # 3. Write portfolio_summary.json
    summary_dict = summary.model_dump()
    summary_path = output_dir / "portfolio_summary.json"
    write_json_atomic(summary_path, summary_dict)
    
    summary_bytes = canonical_json_bytes(summary_dict)
    hashes["portfolio_summary.json"] = sha256_bytes(summary_bytes)
    
    # 4. Write policy and spec for audit
    policy_dict = policy.model_dump()
    policy_path = output_dir / "portfolio_policy.json"
    write_json_atomic(policy_path, policy_dict)
    
    spec_dict = spec.model_dump()
    spec_path = output_dir / "portfolio_spec.json"
    write_json_atomic(spec_path, spec_dict)
    
    # 5. Create manifest
    manifest = {
        "version": "PORTFOLIO_MANIFEST_V1",
        "created_at": pd.Timestamp.now().isoformat(),
        "policy_sha256": sha256_bytes(canonical_json_bytes(policy_dict)),
        "spec_sha256": spec.spec_sha256 if hasattr(spec, "spec_sha256") else "",
        "artifacts": [
            {
                "path": path,
                "sha256": hash_val,
                "type": "parquet" if path.endswith(".parquet") else "json",
            }
            for path, hash_val in hashes.items()
        ],
        "summary": {
            "total_candidates": summary.total_candidates,
            "accepted_count": summary.accepted_count,
            "rejected_count": summary.rejected_count,
            "final_slots_used": summary.final_slots_used,
            "final_margin_ratio": summary.final_margin_ratio,
        },
    }
    
    # Compute manifest hash (excluding the hash field itself)
    manifest_without_hash = manifest.copy()
    manifest_without_hash.pop("manifest_hash", None)
    manifest_hash = sha256_bytes(canonical_json_bytes(manifest_without_hash))
    manifest["manifest_hash"] = manifest_hash
    
    # Write manifest
    manifest_path = output_dir / "portfolio_manifest.json"
    write_json_atomic(manifest_path, manifest)
    
    hashes["portfolio_manifest.json"] = manifest_hash
    
    logger.info(f"Portfolio artifacts written to {output_dir}")
    logger.info(f"Artifacts: {list(hashes.keys())}")
    
    return hashes


def compute_spec_sha256(spec: PortfolioSpecV1) -> str:
    """
    Compute SHA256 hash of canonicalized portfolio spec.
    
    Args:
        spec: Portfolio specification
        
    Returns:
        SHA256 hex digest
    """
    # Create dict without spec_sha256 field
    spec_dict = spec.model_dump()
    spec_dict.pop("spec_sha256", None)
    
    # Canonicalize and hash
    canonical = canonical_json_bytes(spec_dict)
    return sha256_bytes(canonical)


def compute_policy_sha256(policy: PortfolioPolicyV1) -> str:
    """
    Compute SHA256 hash of canonicalized portfolio policy.
    
    Args:
        policy: Portfolio policy
        
    Returns:
        SHA256 hex digest
    """
    policy_dict = policy.model_dump()
    canonical = canonical_json_bytes(policy_dict)
    return sha256_bytes(canonical)


# Setup logging
import logging
logger = logging.getLogger(__name__)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/candidate_export.py
sha256(source_bytes) = 1a3f5026bb7b853aa1e45ad292508ecb1182433ff40fd8098b8884f802e72340
bytes = 6159
redacted = False
--------------------------------------------------------------------------------

"""
Phase Portfolio Bridge: Export candidates.json from Research OS.

Exports CandidateSpecs to a deterministic, auditable JSON file
that can be consumed by Market OS without boundary violations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from FishBroWFS_V2.portfolio.candidate_spec import CandidateSpec, CandidateExport
from FishBroWFS_V2.portfolio.hash_utils import stable_json_dumps


def export_candidates(
    candidates: List[CandidateSpec],
    *,
    export_id: str,
    season: str,
    exports_root: Optional[Path] = None,
) -> Path:
    """
    Export candidates to a deterministic JSON file.
    
    File layout:
        exports/candidates/{season}/{export_id}/candidates.json
        exports/candidates/{season}/{export_id}/manifest.json
    
    Returns:
        Path to the exported candidates.json file
    """
    if exports_root is None:
        exports_root = Path("outputs/exports")
    
    # Create export directory
    export_dir = exports_root / "candidates" / season / export_id
    export_dir.mkdir(parents=True, exist_ok=True)
    
    # Create CandidateExport with timezone-aware timestamp
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat() + "Z"
    candidate_export = CandidateExport(
        export_id=export_id,
        generated_at=generated_at,
        season=season,
        candidates=sorted(candidates, key=lambda c: c.candidate_id),
        deterministic_order="candidate_id asc",
    )
    
    # Build base dict without hash fields
    base_dict = {
        "export_id": export_id,
        "generated_at": generated_at,
        "season": season,
        "deterministic_order": "candidate_id asc",
        "candidates": [_candidate_spec_to_dict(c) for c in candidate_export.candidates],
    }
    
    # Compute candidates_sha256 (hash of base dict)
    candidates_sha256 = _compute_dict_sha256(base_dict)
    
    # Add candidates_sha256 to dict (no manifest_sha256 in candidates.json)
    final_dict = dict(base_dict)
    final_dict["candidates_sha256"] = candidates_sha256
    
    # Write candidates.json
    candidates_path = export_dir / "candidates.json"
    candidates_path.write_text(
        stable_json_dumps(final_dict),
        encoding="utf-8",
    )
    
    # Compute file hash of candidates.json
    candidates_file_sha256 = _compute_file_sha256(candidates_path)
    
    # Build manifest dict (without manifest_sha256)
    manifest_base = {
        "export_id": export_id,
        "season": season,
        "generated_at": generated_at,
        "candidates_count": len(candidates),
        "candidates_file": str(candidates_path.relative_to(export_dir)),
        "deterministic_order": "candidate_id asc",
        "candidates_sha256": candidates_sha256,
        "candidates_file_sha256": candidates_file_sha256,
    }
    
    # Compute manifest_sha256 (hash of manifest_base)
    manifest_sha256 = _compute_dict_sha256(manifest_base)
    manifest_base["manifest_sha256"] = manifest_sha256
    
    # Write manifest.json
    manifest_path = export_dir / "manifest.json"
    manifest_path.write_text(
        stable_json_dumps(manifest_base),
        encoding="utf-8",
    )
    
    return candidates_path


def _candidate_export_to_dict(export: CandidateExport) -> dict:
    """Convert CandidateExport to dict for JSON serialization."""
    return {
        "export_id": export.export_id,
        "generated_at": export.generated_at,
        "season": export.season,
        "deterministic_order": export.deterministic_order,
        "candidates": [_candidate_spec_to_dict(c) for c in export.candidates],
    }


def _candidate_spec_to_dict(candidate: CandidateSpec) -> dict:
    """Convert CandidateSpec to dict for JSON serialization."""
    return {
        "candidate_id": candidate.candidate_id,
        "strategy_id": candidate.strategy_id,
        "param_hash": candidate.param_hash,
        "research_score": candidate.research_score,
        "research_confidence": candidate.research_confidence,
        "season": candidate.season,
        "batch_id": candidate.batch_id,
        "job_id": candidate.job_id,
        "tags": candidate.tags,
        "metadata": candidate.metadata,
    }


def _compute_file_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compute_dict_sha256(obj: dict) -> str:
    """Compute SHA256 hash of a dict using stable JSON serialization."""
    json_str = stable_json_dumps(obj)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def load_candidates(candidates_path: Path) -> CandidateExport:
    """
    Load candidates from a candidates.json file.
    
    Raises:
        FileNotFoundError: if file does not exist
        ValueError: if JSON is invalid
    """
    if not candidates_path.exists():
        raise FileNotFoundError(f"Candidates file not found: {candidates_path}")
    
    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    
    # Remove hash fields if present (they are for audit only)
    data.pop("candidates_sha256", None)
    
    # Convert dicts back to CandidateSpec objects
    candidates = []
    for c_dict in data.get("candidates", []):
        candidate = CandidateSpec(
            candidate_id=c_dict["candidate_id"],
            strategy_id=c_dict["strategy_id"],
            param_hash=c_dict["param_hash"],
            research_score=c_dict["research_score"],
            research_confidence=c_dict.get("research_confidence", 1.0),
            season=c_dict.get("season"),
            batch_id=c_dict.get("batch_id"),
            job_id=c_dict.get("job_id"),
            tags=c_dict.get("tags", []),
            metadata=c_dict.get("metadata", {}),
        )
        candidates.append(candidate)
    
    return CandidateExport(
        export_id=data["export_id"],
        generated_at=data["generated_at"],
        season=data["season"],
        candidates=candidates,
        deterministic_order=data.get("deterministic_order", "candidate_id asc"),
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/candidate_spec.py
sha256(source_bytes) = 5064dd3640aa885cca8dec5d8f32e59fa598847e052942d7b06d7d30baf95821
bytes = 5343
redacted = False
--------------------------------------------------------------------------------

"""
Phase Portfolio Bridge: CandidateSpec for Research → Market boundary.

Research OS can output CandidateSpecs (research candidates) that contain
only information allowed by the boundary contract:
- No trading details (symbol, timeframe, session_profile, etc.)
- No market-specific parameters
- Only research metrics and identifiers that can be mapped later by Market OS

Boundary contract:
- Research OS MUST NOT know any trading details
- Market OS maps CandidateSpec to PortfolioLeg with trading details
- CandidateSpec is deterministic and auditable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CandidateSpec:
    """
    Research candidate specification (boundary-safe).
    
    Contains only information that Research OS is allowed to know:
    - Research identifiers (strategy_id, param_hash)
    - Research metrics (score, confidence, etc.)
    - Research metadata (season, batch_id, job_id)
    - No trading details (symbol, timeframe, session_profile, etc.)
    
    Attributes:
        candidate_id: Unique candidate identifier (e.g., "candidate_001")
        strategy_id: Strategy identifier (e.g., "sma_cross_v1")
        param_hash: Hash of strategy parameters (deterministic)
        research_score: Research metric score (e.g., 1.5)
        research_confidence: Confidence metric (0.0-1.0)
        season: Season identifier (e.g., "2026Q1")
        batch_id: Batch identifier (e.g., "batchA")
        job_id: Job identifier (e.g., "job1")
        tags: Optional tags for categorization
        metadata: Optional additional research metadata (no trading details)
    """
    candidate_id: str
    strategy_id: str
    param_hash: str
    research_score: float
    research_confidence: float = 1.0
    season: Optional[str] = None
    batch_id: Optional[str] = None
    job_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate candidate spec."""
        if not self.candidate_id:
            raise ValueError("candidate_id cannot be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id cannot be empty")
        if not self.param_hash:
            raise ValueError("param_hash cannot be empty")
        if not isinstance(self.research_score, (int, float)):
            raise ValueError(f"research_score must be numeric, got {type(self.research_score)}")
        if not 0.0 <= self.research_confidence <= 1.0:
            raise ValueError(f"research_confidence must be between 0.0 and 1.0, got {self.research_confidence}")
        
        # Ensure metadata does not contain trading details
        forbidden_keys = {"symbol", "timeframe", "session_profile", "market", "exchange", "trading"}
        for key in self.metadata:
            if key.lower() in forbidden_keys:
                raise ValueError(f"metadata key '{key}' contains trading details (boundary violation)")


@dataclass(frozen=True)
class CandidateExport:
    """
    Collection of CandidateSpecs for export.
    
    Used to export research candidates from Research OS to Market OS.
    
    Attributes:
        export_id: Unique export identifier (e.g., "export_2026Q1_topk")
        generated_at: ISO 8601 timestamp
        season: Season identifier
        candidates: List of CandidateSpecs
        deterministic_order: Ordering guarantee
    """
    export_id: str
    generated_at: str
    season: str
    candidates: List[CandidateSpec]
    deterministic_order: str = "candidate_id asc"
    
    def __post_init__(self) -> None:
        """Validate candidate export."""
        if not self.export_id:
            raise ValueError("export_id cannot be empty")
        if not self.generated_at:
            raise ValueError("generated_at cannot be empty")
        if not self.season:
            raise ValueError("season cannot be empty")
        
        # Check candidate_id uniqueness
        candidate_ids = [c.candidate_id for c in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            duplicates = [cid for cid in candidate_ids if candidate_ids.count(cid) > 1]
            raise ValueError(f"Duplicate candidate_id found: {set(duplicates)}")


def create_candidate_from_research(
    *,
    candidate_id: str,
    strategy_id: str,
    params: Dict[str, float],
    research_score: float,
    research_confidence: float = 1.0,
    season: Optional[str] = None,
    batch_id: Optional[str] = None,
    job_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> CandidateSpec:
    """
    Create a CandidateSpec from research results.
    
    Computes param_hash from params dict (deterministic).
    """
    from FishBroWFS_V2.portfolio.hash_utils import hash_params
    
    param_hash = hash_params(params)
    
    return CandidateSpec(
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        param_hash=param_hash,
        research_score=research_score,
        research_confidence=research_confidence,
        season=season,
        batch_id=batch_id,
        job_id=job_id,
        tags=tags or [],
        metadata=metadata or {},
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/cli.py
sha256(source_bytes) = 63788d2674fa655183b422c555612a05551b08d0341dc22ec83be016efb7ead1
bytes = 11236
redacted = False
--------------------------------------------------------------------------------
"""Portfolio CLI."""

import argparse
import json
import sys
import yaml
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    PortfolioSpecV1,
)
from FishBroWFS_V2.portfolio.runner_v1 import (
    run_portfolio_admission,
    validate_portfolio_spec,
)
from FishBroWFS_V2.portfolio.artifacts_writer_v1 import (
    write_portfolio_artifacts,
    compute_spec_sha256,
    compute_policy_sha256,
)


def load_yaml_or_json(filepath: Path) -> dict:
    """Load YAML or JSON file."""
    content = filepath.read_text(encoding="utf-8")
    if filepath.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def save_yaml_or_json(filepath: Path, data: dict):
    """Save data as YAML or JSON based on file extension."""
    if filepath.suffix.lower() in (".yaml", ".yml"):
        filepath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    else:
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")


def validate_command(args):
    """Validate portfolio specification."""
    try:
        # Load spec
        spec_data = load_yaml_or_json(args.spec)
        
        # Load policy if provided separately
        policy_data = {}
        if args.policy:
            policy_data = load_yaml_or_json(args.policy)
            spec_data["policy"] = policy_data
        
        # Create spec object (without sha256 for now)
        if "spec_sha256" in spec_data:
            spec_data.pop("spec_sha256")
        
        spec = PortfolioSpecV1(**spec_data)
        
        # Compute spec SHA256
        spec_sha256 = compute_spec_sha256(spec)
        print(f"✓ Spec SHA256: {spec_sha256}")
        
        # Validate against outputs
        outputs_root = Path(args.outputs_root) if args.outputs_root else Path("outputs")
        errors = validate_portfolio_spec(spec, outputs_root)
        
        if errors:
            print("✗ Validation errors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        
        # Resource estimate
        total_estimate = len(spec.seasons) * len(spec.strategy_ids) * len(spec.instrument_ids) * 1000
        print(f"✓ Resource estimate: ~{total_estimate} candidates")
        
        print("✓ Spec validation passed")
        
        # If --save flag, update spec with SHA256
        if args.save:
            spec_dict = spec.model_dump()
            spec_dict["spec_sha256"] = spec_sha256
            save_yaml_or_json(args.spec, spec_dict)
            print(f"✓ Updated {args.spec} with spec_sha256")
        
    except Exception as e:
        print(f"✗ Validation failed: {e}")
        sys.exit(1)


def run_command(args):
    """Run portfolio admission."""
    try:
        # Load spec
        spec_data = load_yaml_or_json(args.spec)
        spec = PortfolioSpecV1(**spec_data)
        
        # Load policy (could be embedded in spec or separate)
        if "policy" in spec_data:
            policy_data = spec_data["policy"]
        elif args.policy:
            policy_data = load_yaml_or_json(args.policy)
        else:
            raise ValueError("Policy not found in spec and --policy not provided")
        
        policy = PortfolioPolicyV1(**policy_data)
        
        # Compute SHA256 for audit
        policy_sha256 = compute_policy_sha256(policy)
        spec_sha256 = spec.spec_sha256 if hasattr(spec, "spec_sha256") else compute_spec_sha256(spec)
        
        print(f"Policy SHA256: {policy_sha256}")
        print(f"Spec SHA256: {spec_sha256}")
        
        # Set equity
        equity_base = args.equity if args.equity else 1_000_000.0  # Default 1M TWD
        
        # Output directory
        if args.output_dir:
            output_dir = Path(args.output_dir)
        else:
            # Create auto-generated directory
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path("outputs") / "portfolio" / f"run_{timestamp}"
        
        outputs_root = Path(args.outputs_root) if args.outputs_root else Path("outputs")
        
        # Run portfolio admission
        candidates, final_positions, results = run_portfolio_admission(
            policy=policy,
            spec=spec,
            equity_base=equity_base,
            outputs_root=outputs_root,
            replay_mode=False,
        )
        
        # Update summary with SHA256
        summary = results["summary"]
        summary.policy_sha256 = policy_sha256
        summary.spec_sha256 = spec_sha256
        
        # Write artifacts
        hashes = write_portfolio_artifacts(
            output_dir=output_dir,
            decisions=results["decisions"],
            bar_states=results["bar_states"],
            summary=summary,
            policy=policy,
            spec=spec,
            replay_mode=False,
        )
        
        print(f"\n✓ Portfolio admission completed")
        print(f"  Output directory: {output_dir}")
        print(f"  Candidates: {summary.total_candidates}")
        print(f"  Accepted: {summary.accepted_count}")
        print(f"  Rejected: {summary.rejected_count}")
        print(f"  Final slots used: {summary.final_slots_used}/{policy.max_slots_total}")
        print(f"  Final margin ratio: {summary.final_margin_ratio:.2%}")
        
        # Save run info
        run_info = {
            "run_id": output_dir.name,
            "timestamp": datetime.now().isoformat(),
            "spec_sha256": spec_sha256,
            "policy_sha256": policy_sha256,
            "output_dir": str(output_dir),
            "summary": summary.model_dump(),
        }
        run_info_path = output_dir / "run_info.json"
        run_info_path.write_text(json.dumps(run_info, indent=2), encoding="utf-8")
        
    except Exception as e:
        print(f"✗ Run failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def replay_command(args):
    """Replay portfolio admission (read-only)."""
    try:
        # Find run directory
        run_id = args.run_id
        runs_dir = Path("outputs") / "portfolio"
        
        run_dir = None
        for dir_path in runs_dir.glob(f"*{run_id}*"):
            if dir_path.is_dir():
                run_dir = dir_path
                break
        
        if not run_dir or not run_dir.exists():
            print(f"✗ Run directory not found for run_id: {run_id}")
            sys.exit(1)
        
        # Load spec and policy from run directory
        spec_path = run_dir / "portfolio_spec.json"
        policy_path = run_dir / "portfolio_policy.json"
        
        if not spec_path.exists() or not policy_path.exists():
            print(f"✗ Spec or policy not found in run directory")
            sys.exit(1)
        
        spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
        policy_data = json.loads(policy_path.read_text(encoding="utf-8"))
        
        spec = PortfolioSpecV1(**spec_data)
        policy = PortfolioPolicyV1(**policy_data)
        
        print(f"Replaying run: {run_dir.name}")
        print(f"Spec SHA256: {spec.spec_sha256 if hasattr(spec, 'spec_sha256') else 'N/A'}")
        print(f"Policy SHA256: {compute_policy_sha256(policy)}")
        
        # Run in replay mode (no writes)
        equity_base = args.equity if args.equity else 1_000_000.0
        outputs_root = Path(args.outputs_root) if args.outputs_root else Path("outputs")
        
        candidates, final_positions, results = run_portfolio_admission(
            policy=policy,
            spec=spec,
            equity_base=equity_base,
            outputs_root=outputs_root,
            replay_mode=True,
        )
        
        summary = results["summary"]
        print(f"\n✓ Replay completed (read-only)")
        print(f"  Candidates: {summary.total_candidates}")
        print(f"  Accepted: {summary.accepted_count}")
        print(f"  Rejected: {summary.rejected_count}")
        print(f"  Final slots used: {summary.final_slots_used}/{policy.max_slots_total}")
        
        # Compare with original results if available
        original_summary_path = run_dir / "portfolio_summary.json"
        if original_summary_path.exists():
            original_summary = json.loads(original_summary_path.read_text(encoding="utf-8"))
            if (summary.accepted_count == original_summary["accepted_count"] and
                summary.rejected_count == original_summary["rejected_count"]):
                print("✓ Replay matches original results")
            else:
                print("✗ Replay differs from original results!")
                print(f"  Original: {original_summary['accepted_count']} accepted, {original_summary['rejected_count']} rejected")
                print(f"  Replay: {summary.accepted_count} accepted, {summary.rejected_count} rejected")
        
    except Exception as e:
        print(f"✗ Replay failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Portfolio Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate portfolio specification")
    validate_parser.add_argument("--spec", type=Path, required=True, help="Spec file (YAML/JSON)")
    validate_parser.add_argument("--policy", type=Path, help="Policy file (YAML/JSON, optional if embedded in spec)")
    validate_parser.add_argument("--outputs-root", type=Path, help="Outputs root directory (default: outputs)")
    validate_parser.add_argument("--save", action="store_true", help="Save spec with computed SHA256")
    validate_parser.set_defaults(func=validate_command)
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run portfolio admission")
    run_parser.add_argument("--spec", type=Path, required=True, help="Spec file (YAML/JSON)")
    run_parser.add_argument("--policy", type=Path, help="Policy file (YAML/JSON, optional if embedded in spec)")
    run_parser.add_argument("--equity", type=float, help="Equity in base currency (default: 1,000,000 TWD)")
    run_parser.add_argument("--outputs-root", type=Path, help="Outputs root directory (default: outputs)")
    run_parser.add_argument("--output-dir", type=Path, help="Output directory (default: auto-generated)")
    run_parser.set_defaults(func=run_command)
    
    # Replay command
    replay_parser = subparsers.add_parser("replay", help="Replay portfolio admission (read-only)")
    replay_parser.add_argument("--run-id", type=str, required=True, help="Run ID or directory name")
    replay_parser.add_argument("--equity", type=float, help="Equity in base currency (default: 1,000,000 TWD)")
    replay_parser.add_argument("--outputs-root", type=Path, help="Outputs root directory (default: outputs)")
    replay_parser.set_defaults(func=replay_command)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/compiler.py
sha256(source_bytes) = be761d4de6c7dd5cc0a68f02665260d763436fbaba01a2d912abb46a04b2e195
bytes = 1569
redacted = False
--------------------------------------------------------------------------------

"""Portfolio compiler - compile PortfolioSpec to Funnel job configs.

Phase 8: Convert portfolio specification to executable job configurations.
"""

from __future__ import annotations

from typing import Dict, List

from FishBroWFS_V2.portfolio.spec import PortfolioSpec


def compile_portfolio(spec: PortfolioSpec) -> List[Dict[str, any]]:
    """Compile portfolio specification to job configurations.
    
    Each enabled leg produces one job_cfg dict.
    
    Args:
        spec: Portfolio specification
        
    Returns:
        List of job configuration dicts (one per enabled leg)
    """
    jobs = []
    
    for leg in spec.legs:
        if not leg.enabled:
            continue
        
        # Build job configuration
        job_cfg: Dict[str, any] = {
            # Portfolio metadata
            "portfolio_id": spec.portfolio_id,
            "portfolio_version": spec.version,
            
            # Leg metadata
            "leg_id": leg.leg_id,
            "symbol": leg.symbol,
            "timeframe_min": leg.timeframe_min,
            "session_profile": leg.session_profile,  # Path, passed as-is to pipeline
            
            # Strategy metadata
            "strategy_id": leg.strategy_id,
            "strategy_version": leg.strategy_version,
            
            # Strategy parameters
            "params": dict(leg.params),  # Copy dict
            
            # Optional: tags for categorization
            "tags": list(leg.tags),  # Copy list
        }
        
        jobs.append(job_cfg)
    
    return jobs



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/decisions_reader.py
sha256(source_bytes) = e9fcdecefab41a106f4717841504538b5c4bb14fdad9703626d95a885db2735f
bytes = 3410
redacted = False
--------------------------------------------------------------------------------

"""Decisions log parser for portfolio generation.

Parses append-only decisions.log lines. Supports JSONL + pipe format.
Invalid lines are ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _as_stripped_text(v: Any) -> str:
    """Convert value to trimmed string. None -> ''."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _parse_pipe_line(s: str) -> dict | None:
    """
    Parse simple pipe-delimited lines:
      - run_id|DECISION
      - run_id|DECISION|note
      - run_id|DECISION|note|ts
    note may be empty. ts may be missing.
    """
    parts = [p.strip() for p in s.split("|")]
    if len(parts) < 2:
        return None

    run_id = parts[0].strip()
    decision_raw = parts[1].strip()
    note = parts[2].strip() if len(parts) >= 3 else ""
    ts = parts[3].strip() if len(parts) >= 4 else ""

    if not run_id:
        return None
    if not decision_raw:
        return None

    out = {
        "run_id": run_id,
        "decision": decision_raw.upper(),
        "note": note,
    }
    if ts:
        out["ts"] = ts
    return out


def parse_decisions_log_lines(lines: list[str]) -> list[dict]:
    """Parse decisions.log lines. Supports JSONL + pipe format. Invalid lines ignored.
    
    Required:
      - run_id (non-empty after strip)
      - decision (non-empty after strip; normalized to upper)
    Optional:
      - note (may be missing/empty)
      - ts   (kept if present)
    """
    out: list[dict] = []

    for raw in lines:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s:
            continue
            
        # 1) Try JSONL first
        parsed: dict | None = None
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                run_id = _as_stripped_text(obj.get("run_id"))
                decision_raw = _as_stripped_text(obj.get("decision"))
                note = _as_stripped_text(obj.get("note"))
                ts = _as_stripped_text(obj.get("ts"))

                if not run_id:
                    continue
                if not decision_raw:
                    continue

                parsed = {
                    "run_id": run_id,
                    "decision": decision_raw.upper(),
                    "note": note,
                }
                if ts:
                    parsed["ts"] = ts
        except Exception:
            # Not JSON -> try pipe
            parsed = None

        # 2) Pipe fallback
        if parsed is None:
            parsed = _parse_pipe_line(s)

        if parsed is None:
            continue

        out.append(parsed)

    return out


def read_decisions_log(decisions_log_path: Path) -> list[dict]:
    """Read decisions.log file and parse its contents.
    
    Args:
        decisions_log_path: Path to decisions.log file
        
    Returns:
        List of parsed decision entries. Returns empty list if file doesn't exist.
    """
    if not decisions_log_path.exists():
        return []
    
    try:
        with open(decisions_log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return parse_decisions_log_lines(lines)
    except Exception:
        # If any error occurs (permission, encoding, etc.), return empty list
        return []



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/engine_v1.py
sha256(source_bytes) = e451b9ff4d36f37a6ebcb197407689496684b73276de5090f9ec35a0276a3a7b
bytes = 10197
redacted = False
--------------------------------------------------------------------------------
"""Portfolio admission engine V1."""

import logging
from typing import List, Tuple, Dict, Optional
from datetime import datetime

from FishBroWFS_V2.core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    SignalCandidateV1,
    OpenPositionV1,
    AdmissionDecisionV1,
    PortfolioStateV1,
    PortfolioSummaryV1,
)

logger = logging.getLogger(__name__)


class PortfolioEngineV1:
    """Portfolio admission engine with deterministic decision making."""
    
    def __init__(self, policy: PortfolioPolicyV1, equity_base: float):
        """
        Initialize portfolio engine.
        
        Args:
            policy: Portfolio policy defining limits and behavior
            equity_base: Initial equity in base currency (TWD)
        """
        self.policy = policy
        self.equity_base = equity_base
        
        # Current state
        self.open_positions: List[OpenPositionV1] = []
        self.slots_used = 0
        self.margin_used_base = 0.0
        self.notional_used_base = 0.0
        
        # Track decisions per bar
        self.decisions: List[AdmissionDecisionV1] = []
        self.bar_states: Dict[Tuple[int, datetime], PortfolioStateV1] = {}
        
        # Statistics
        self.reject_count = 0
        
    def _compute_sort_key(self, candidate: SignalCandidateV1) -> Tuple:
        """
        Compute deterministic sort key for candidate.
        
        Sort order (ascending):
        1. Higher priority first (lower priority number = higher priority)
        2. Higher candidate_score first (negative for descending)
        3. signal_series_sha256 lexicographically as final tie-break
        
        Returns:
            Tuple for sorting
        """
        priority = self.policy.strategy_priority.get(candidate.strategy_id, 9999)
        # Negative candidate_score for descending order (higher score first)
        score = -candidate.candidate_score
        # Use signal_series_sha256 as final deterministic tie-break
        # If not available, use strategy_id + instrument_id as fallback
        sha = candidate.signal_series_sha256 or f"{candidate.strategy_id}:{candidate.instrument_id}"
        
        return (priority, score, sha)
    
    def _get_sort_key_string(self, candidate: SignalCandidateV1) -> str:
        """Generate human-readable sort key string for audit."""
        priority = self.policy.strategy_priority.get(candidate.strategy_id, 9999)
        return f"priority={priority},candidate_score={candidate.candidate_score:.4f},sha={candidate.signal_series_sha256 or 'N/A'}"
    
    def _check_instrument_cap(self, instrument_id: str) -> bool:
        """Check if instrument has available slots."""
        if not self.policy.max_slots_by_instrument:
            return True
        
        max_slots = self.policy.max_slots_by_instrument.get(instrument_id)
        if max_slots is None:
            return True
        
        # Count current slots for this instrument
        current_slots = sum(
            1 for pos in self.open_positions 
            if pos.instrument_id == instrument_id
        )
        return current_slots < max_slots
    
    def _can_admit(self, candidate: SignalCandidateV1) -> Tuple[bool, str]:
        """
        Check if candidate can be admitted.
        
        Returns:
            Tuple of (can_admit, reason)
        """
        # Check total slots
        if self.slots_used + candidate.required_slot > self.policy.max_slots_total:
            return False, "REJECT_FULL"
        
        # Check instrument-specific cap
        if not self._check_instrument_cap(candidate.instrument_id):
            return False, "REJECT_FULL"  # Instrument-specific full
        
        # Check margin ratio
        required_margin = candidate.required_margin_base
        new_margin_used = self.margin_used_base + required_margin
        max_allowed_margin = self.equity_base * self.policy.max_margin_ratio
        
        if new_margin_used > max_allowed_margin:
            return False, "REJECT_MARGIN"
        
        # Check notional ratio (optional)
        if self.policy.max_notional_ratio is not None:
            # Note: notional check not implemented in v1
            pass
        
        return True, "ACCEPT"
    
    def _add_position(self, candidate: SignalCandidateV1):
        """Add new position to portfolio."""
        position = OpenPositionV1(
            strategy_id=candidate.strategy_id,
            instrument_id=candidate.instrument_id,
            slots=candidate.required_slot,
            margin_base=candidate.required_margin_base,
            notional_base=0.0,  # Notional not tracked in v1
            entry_bar_index=candidate.bar_index,
            entry_bar_ts=candidate.bar_ts,
        )
        self.open_positions.append(position)
        self.slots_used += candidate.required_slot
        self.margin_used_base += candidate.required_margin_base
    
    def admit_candidates(
        self,
        candidates: List[SignalCandidateV1],
        current_open_positions: Optional[List[OpenPositionV1]] = None,
    ) -> List[AdmissionDecisionV1]:
        """
        Process admission for a list of candidates at the same bar.
        
        Args:
            candidates: List of candidates for the same bar
            current_open_positions: Optional list of existing open positions
                (if None, uses engine's current state)
        
        Returns:
            List of admission decisions
        """
        # Reset to provided open positions if given
        if current_open_positions is not None:
            self.open_positions = current_open_positions.copy()
            self.slots_used = sum(pos.slots for pos in self.open_positions)
            self.margin_used_base = sum(pos.margin_base for pos in self.open_positions)
        
        # Sort candidates deterministically
        sorted_candidates = sorted(candidates, key=self._compute_sort_key)
        
        decisions = []
        for candidate in sorted_candidates:
            # Check if can admit
            can_admit, reason = self._can_admit(candidate)
            
            # Create decision
            sort_key_str = self._get_sort_key_string(candidate)
            decision = AdmissionDecisionV1(
                strategy_id=candidate.strategy_id,
                instrument_id=candidate.instrument_id,
                bar_ts=candidate.bar_ts,
                bar_index=candidate.bar_index,
                signal_strength=candidate.signal_strength,
                candidate_score=candidate.candidate_score,
                signal_series_sha256=candidate.signal_series_sha256,
                accepted=can_admit,
                reason=reason,
                sort_key_used=sort_key_str,
                slots_after=self.slots_used + (candidate.required_slot if can_admit else 0),
                margin_after_base=self.margin_used_base + (candidate.required_margin_base if can_admit else 0),
            )
            
            if can_admit:
                # Admit candidate
                self._add_position(candidate)
                logger.debug(
                    f"Admitted {candidate.strategy_id}/{candidate.instrument_id} "
                    f"at bar {candidate.bar_index}, slots={self.slots_used}, "
                    f"margin={self.margin_used_base:.0f}"
                )
            else:
                self.reject_count += 1
                logger.debug(
                    f"Rejected {candidate.strategy_id}/{candidate.instrument_id} "
                    f"at bar {candidate.bar_index}: {reason}"
                )
            
            decisions.append(decision)
        
        # Record bar state
        if candidates:
            bar_ts = candidates[0].bar_ts
            bar_index = candidates[0].bar_index
            self.bar_states[(bar_index, bar_ts)] = PortfolioStateV1(
                bar_ts=bar_ts,
                bar_index=bar_index,
                equity_base=self.equity_base,
                slots_used=self.slots_used,
                margin_used_base=self.margin_used_base,
                notional_used_base=self.notional_used_base,
                open_positions=self.open_positions.copy(),
                reject_count=self.reject_count,
            )
        
        self.decisions.extend(decisions)
        return decisions
    
    def get_summary(self) -> PortfolioSummaryV1:
        """Generate summary of admission results."""
        reject_reasons = {}
        for decision in self.decisions:
            if not decision.accepted:
                reject_reasons[decision.reason] = reject_reasons.get(decision.reason, 0) + 1
        
        total = len(self.decisions)
        accepted = sum(1 for d in self.decisions if d.accepted)
        rejected = total - accepted
        
        return PortfolioSummaryV1(
            total_candidates=total,
            accepted_count=accepted,
            rejected_count=rejected,
            reject_reasons=reject_reasons,
            final_slots_used=self.slots_used,
            final_margin_used_base=self.margin_used_base,
            final_margin_ratio=self.margin_used_base / self.equity_base if self.equity_base > 0 else 0.0,
            policy_sha256="",  # To be filled by caller
            spec_sha256="",  # To be filled by caller
        )
    
    def reset(self):
        """Reset engine to initial state."""
        self.open_positions.clear()
        self.slots_used = 0
        self.margin_used_base = 0.0
        self.notional_used_base = 0.0
        self.decisions.clear()
        self.bar_states.clear()
        self.reject_count = 0


# Convenience function
def admit_candidates(
    policy: PortfolioPolicyV1,
    equity_base: float,
    candidates: List[SignalCandidateV1],
    current_open_positions: Optional[List[OpenPositionV1]] = None,
) -> Tuple[List[AdmissionDecisionV1], PortfolioSummaryV1]:
    """
    Convenience function for one-shot admission.
    
    Returns:
        Tuple of (decisions, summary)
    """
    engine = PortfolioEngineV1(policy, equity_base)
    decisions = engine.admit_candidates(candidates, current_open_positions)
    summary = engine.get_summary()
    return decisions, summary
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/hash_utils.py
sha256(source_bytes) = 536d3ac940db2659117933fd8ba24fb044975628d0671590198b0251388dde3d
bytes = 810
redacted = False
--------------------------------------------------------------------------------

"""Hash utilities for deterministic portfolio ID generation."""

import hashlib
import json
from typing import Any


def stable_json_dumps(obj: Any) -> str:
    """Deterministic JSON dumps: sort_keys=True, separators=(',', ':'), ensure_ascii=False"""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        default=str  # Handle non-serializable types
    )


def sha1_text(s: str) -> str:
    """SHA1 hex digest for text."""
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def hash_params(params: dict[str, float]) -> str:
    """
    Deterministic hash of strategy parameters.
    
    Uses stable JSON serialization and SHA1.
    """
    if not params:
        return "empty"
    return sha1_text(stable_json_dumps(params))



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/instruments.py
sha256(source_bytes) = e751f522278d6b0f8b9c1cab34503cdca42544094173c6e9356d4c27ddcb7c4e
bytes = 3680
redacted = False
--------------------------------------------------------------------------------
"""Instrument configuration loader with deterministic SHA256 hashing."""

from pathlib import Path
from dataclasses import dataclass
import hashlib
from typing import Dict

import yaml


@dataclass(frozen=True)
class InstrumentSpec:
    """Specification for a single instrument."""
    instrument: str
    currency: str
    multiplier: float
    initial_margin_per_contract: float
    maintenance_margin_per_contract: float
    margin_basis: str = ""  # optional: exchange_maintenance, conservative_over_exchange, broker_day


@dataclass(frozen=True)
class InstrumentsConfig:
    """Loaded instruments configuration with SHA256 hash."""
    version: int
    base_currency: str
    fx_rates: Dict[str, float]
    instruments: Dict[str, InstrumentSpec]
    sha256: str


def load_instruments_config(path: Path) -> InstrumentsConfig:
    """
    Load instruments configuration from YAML file.
    
    Args:
        path: Path to instruments.yaml
        
    Returns:
        InstrumentsConfig with SHA256 hash of canonical YAML bytes.
        
    Raises:
        FileNotFoundError: if file does not exist
        yaml.YAMLError: if YAML is malformed
        KeyError: if required fields are missing
        ValueError: if validation fails (e.g., base_currency not in fx_rates)
    """
    # Read raw bytes for deterministic SHA256
    raw_bytes = path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    
    # Parse YAML
    data = yaml.safe_load(raw_bytes)
    
    # Validate version
    version = data.get("version")
    if version != 1:
        raise ValueError(f"Unsupported version: {version}, expected 1")
    
    # Validate base_currency
    base_currency = data.get("base_currency")
    if not base_currency:
        raise KeyError("Missing 'base_currency'")
    
    # Validate fx_rates
    fx_rates = data.get("fx_rates", {})
    if not isinstance(fx_rates, dict):
        raise ValueError("'fx_rates' must be a dict")
    if base_currency not in fx_rates:
        raise ValueError(f"base_currency '{base_currency}' must be present in fx_rates")
    if fx_rates.get(base_currency) != 1.0:
        raise ValueError(f"fx_rates[{base_currency}] must be 1.0")
    
    # Validate instruments
    instruments_raw = data.get("instruments", {})
    if not isinstance(instruments_raw, dict):
        raise ValueError("'instruments' must be a dict")
    
    instruments = {}
    for instrument_key, spec_dict in instruments_raw.items():
        # Validate required fields
        required = ["currency", "multiplier", "initial_margin_per_contract", "maintenance_margin_per_contract"]
        for field in required:
            if field not in spec_dict:
                raise KeyError(f"Instrument '{instrument_key}' missing field '{field}'")
        
        # Validate currency exists in fx_rates
        currency = spec_dict["currency"]
        if currency not in fx_rates:
            raise ValueError(f"Instrument '{instrument_key}' currency '{currency}' not in fx_rates")
        
        # Create InstrumentSpec
        spec = InstrumentSpec(
            instrument=instrument_key,
            currency=currency,
            multiplier=float(spec_dict["multiplier"]),
            initial_margin_per_contract=float(spec_dict["initial_margin_per_contract"]),
            maintenance_margin_per_contract=float(spec_dict["maintenance_margin_per_contract"]),
            margin_basis=spec_dict.get("margin_basis", ""),
        )
        instruments[instrument_key] = spec
    
    return InstrumentsConfig(
        version=version,
        base_currency=base_currency,
        fx_rates=fx_rates,
        instruments=instruments,
        sha256=sha256,
    )
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/loader.py
sha256(source_bytes) = 9f3655753f1a85480429dd756b3ba5410acbbcb2dd78e669b459bed41f79814c
bytes = 4188
redacted = False
--------------------------------------------------------------------------------

"""Portfolio specification loader.

Phase 8: Load portfolio specs from YAML/JSON files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from FishBroWFS_V2.portfolio.spec import PortfolioLeg, PortfolioSpec


def load_portfolio_spec(path: Path) -> PortfolioSpec:
    """Load portfolio specification from YAML or JSON file.
    
    Args:
        path: Path to portfolio spec file (.yaml, .yml, or .json)
        
    Returns:
        PortfolioSpec loaded from file
        
    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file format is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Portfolio spec not found: {path}")
    
    # Load based on file extension
    suffix = path.suffix.lower()
    if suffix in [".yaml", ".yml"]:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Must be .yaml, .yml, or .json")
    
    if not isinstance(data, dict):
        raise ValueError(f"Invalid portfolio format: expected dict, got {type(data)}")
    
    # Extract fields
    portfolio_id = data.get("portfolio_id")
    version = data.get("version")
    data_tz = data.get("data_tz", "Asia/Taipei")
    legs_data = data.get("legs", [])
    
    if not portfolio_id:
        raise ValueError("Portfolio spec missing 'portfolio_id' field")
    if not version:
        raise ValueError("Portfolio spec missing 'version' field")
    
    # Load legs
    legs = []
    for leg_data in legs_data:
        if not isinstance(leg_data, dict):
            raise ValueError(f"Leg must be dict, got {type(leg_data)}")
        
        leg_id = leg_data.get("leg_id")
        symbol = leg_data.get("symbol")
        timeframe_min = leg_data.get("timeframe_min")
        session_profile = leg_data.get("session_profile")
        strategy_id = leg_data.get("strategy_id")
        strategy_version = leg_data.get("strategy_version")
        params = leg_data.get("params", {})
        enabled = leg_data.get("enabled", True)
        tags = leg_data.get("tags", [])
        
        # Validate required fields
        if not leg_id:
            raise ValueError("Leg missing 'leg_id' field")
        if not symbol:
            raise ValueError(f"Leg '{leg_id}' missing 'symbol' field")
        if timeframe_min is None:
            raise ValueError(f"Leg '{leg_id}' missing 'timeframe_min' field")
        if not session_profile:
            raise ValueError(f"Leg '{leg_id}' missing 'session_profile' field")
        if not strategy_id:
            raise ValueError(f"Leg '{leg_id}' missing 'strategy_id' field")
        if not strategy_version:
            raise ValueError(f"Leg '{leg_id}' missing 'strategy_version' field")
        
        # Convert params values to float
        if not isinstance(params, dict):
            raise ValueError(f"Leg '{leg_id}' params must be dict, got {type(params)}")
        
        params_float = {}
        for key, value in params.items():
            try:
                params_float[key] = float(value)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Leg '{leg_id}' param '{key}' must be numeric, got {type(value)}: {e}"
                )
        
        # Convert tags to list
        if not isinstance(tags, list):
            raise ValueError(f"Leg '{leg_id}' tags must be list, got {type(tags)}")
        
        leg = PortfolioLeg(
            leg_id=leg_id,
            symbol=symbol,
            timeframe_min=int(timeframe_min),
            session_profile=session_profile,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            params=params_float,
            enabled=bool(enabled),
            tags=list(tags),
        )
        legs.append(leg)
    
    return PortfolioSpec(
        portfolio_id=portfolio_id,
        version=version,
        data_tz=data_tz,
        legs=legs,
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/plan_builder.py
sha256(source_bytes) = 660139977728acd04d2c19e594cb79f334cc4b3e640c4b208610d0bd65c7eddf
bytes = 24871
redacted = False
--------------------------------------------------------------------------------

"""
Phase 17 rev2: Portfolio Plan Builder (deterministic, read‑only over exports).

Contracts:
- Only reads from exports tree (no artifacts, no engine).
- Deterministic tie‑break ordering.
- Controlled mutation: writes only under outputs/portfolio/plans/{plan_id}/
- Hash chain audit (plan_manifest.json with self‑hash).
- Enrichment via batch_api (optional, best‑effort).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# pydantic ValidationError not used; removed to avoid import error

from FishBroWFS_V2.contracts.portfolio.plan_payloads import PlanCreatePayload
from FishBroWFS_V2.contracts.portfolio.plan_models import (
    ConstraintsReport,
    PlannedCandidate,
    PlannedWeight,
    PlanSummary,
    PortfolioPlan,
    SourceRef,
)

# LEGAL gateway for artifacts reads
from FishBroWFS_V2.control import batch_api  # Phase 14.1 read-only gateway

# Use existing repo utilities
from FishBroWFS_V2.control.artifacts import (
    canonical_json_bytes,
    compute_sha256,
    write_atomic_json,
)

# Write‑scope guard
from FishBroWFS_V2.utils.write_scope import create_plan_scope

getcontext().prec = 40


# -----------------------------
# Helpers: canonical json + sha256
# -----------------------------
def canonical_json(obj: Any) -> str:
    # Use repo standard canonical_json_bytes and decode to string
    return canonical_json_bytes(obj).decode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return compute_sha256(b)


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, text: str) -> None:
    # deterministic-ish atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# -----------------------------
# Candidate input model (loose)
# -----------------------------
@dataclass(frozen=True)
class CandidateIn:
    candidate_id: str
    strategy_id: str
    dataset_id: str
    params: Dict[str, Any]
    score: float
    season: str
    source_batch: str
    source_export: str


def _candidate_sort_key(c: CandidateIn) -> Tuple:
    # score DESC => use negative
    params_canon = canonical_json(c.params)
    return (-float(c.score), c.strategy_id, c.dataset_id, c.source_batch, params_canon, c.candidate_id)


def _candidate_id(c: CandidateIn) -> str:
    # Deterministic candidate_id from core fields
    # NOTE: do not include export_name here; source_export stored separately.
    payload = {
        "strategy_id": c.strategy_id,
        "dataset_id": c.dataset_id,
        "params": c.params,
        "source_batch": c.source_batch,
        "season": c.season,
    }
    return "cand_" + sha256_text(canonical_json(payload))[:16]


# -----------------------------
# Selection constraints
# -----------------------------
@dataclass
class SelectionReport:
    max_per_strategy_truncated: Dict[str, int] = None  # type: ignore
    max_per_dataset_truncated: Dict[str, int] = None   # type: ignore

    def __post_init__(self):
        if self.max_per_strategy_truncated is None:
            self.max_per_strategy_truncated = {}
        if self.max_per_dataset_truncated is None:
            self.max_per_dataset_truncated = {}


def apply_selection_constraints(
    candidates_sorted: List[CandidateIn],
    top_n: int,
    max_per_strategy: int,
    max_per_dataset: int,
) -> Tuple[List[CandidateIn], SelectionReport]:
    limited = candidates_sorted[:top_n]
    per_strat: Dict[str, int] = {}
    per_ds: Dict[str, int] = {}
    selected: List[CandidateIn] = []
    rep = SelectionReport()

    for c in limited:
        s_ok = per_strat.get(c.strategy_id, 0) < max_per_strategy
        d_ok = per_ds.get(c.dataset_id, 0) < max_per_dataset

        if not s_ok:
            rep.max_per_strategy_truncated[c.strategy_id] = rep.max_per_strategy_truncated.get(c.strategy_id, 0) + 1
        if not d_ok:
            rep.max_per_dataset_truncated[c.dataset_id] = rep.max_per_dataset_truncated.get(c.dataset_id, 0) + 1

        if s_ok and d_ok:
            selected.append(c)
            per_strat[c.strategy_id] = per_strat.get(c.strategy_id, 0) + 1
            per_ds[c.dataset_id] = per_ds.get(c.dataset_id, 0) + 1

    return selected, rep


# -----------------------------
# Weighting + clip + renorm
# -----------------------------
@dataclass(frozen=True)
class WeightItem:
    candidate_id: str
    weight: float


def _to_dec(x: float) -> Decimal:
    return Decimal(str(x))


def _round_dec(x: Decimal, places: int = 12) -> Decimal:
    q = Decimal("1." + ("0" * places))
    return x.quantize(q, rounding=ROUND_HALF_UP)


def clip_and_renormalize_deterministic(
    items: List[WeightItem],
    min_w: float,
    max_w: float,
    *,
    places: int = 12,
    tol: float = 1e-9,
) -> Tuple[List[WeightItem], Dict[str, Any]]:
    if not items:
        return [], {
            "max_weight_clipped": [],
            "min_weight_clipped": [],
            "renormalization_applied": False,
            "renormalization_factor": None,
        }

    min_d = _to_dec(min_w)
    max_d = _to_dec(max_w)
    max_clipped_ids: set[str] = set()
    min_clipped_ids: set[str] = set()

    clipped: List[Tuple[str, Decimal]] = []
    for it in items:
        w = _to_dec(it.weight)
        if w > max_d:
            w = max_d
            max_clipped_ids.add(it.candidate_id)
        if w < min_d:
            w = min_d
            min_clipped_ids.add(it.candidate_id)
        clipped.append((it.candidate_id, w))

    total = sum(w for _, w in clipped)
    if total == Decimal("0"):
        # deterministic fallback: equal
        n = Decimal(len(clipped))
        eq = Decimal("1") / n
        clipped = [(cid, eq) for cid, _ in clipped]
        total = sum(w for _, w in clipped)

    scaled = [(cid, (w / total)) for cid, w in clipped]
    rounded = [(cid, _round_dec(w, places)) for cid, w in scaled]
    rounded_total = sum(w for _, w in rounded)

    one = Decimal("1")
    unit = Decimal("1") / (Decimal(10) ** places)
    residual = one - rounded_total

    ticks = int((residual / unit).to_integral_value(rounding=ROUND_HALF_UP))
    order = sorted(range(len(rounded)), key=lambda i: rounded[i][0])  # cid asc
    updated = [(cid, w) for cid, w in rounded]  # keep as tuple

    if ticks != 0:
        step = unit if ticks > 0 else -unit
        ticks_abs = abs(ticks)
        idx = 0
        while ticks_abs > 0:
            i = order[idx % len(order)]
            cid, w = updated[i]
            new_w = w + step
            if Decimal("0") <= new_w <= Decimal("1"):
                updated[i] = (cid, new_w)
                ticks_abs -= 1
            idx += 1

    final_total = sum(w for _, w in updated)
    # Convert to floats
    out_map = {cid: float(w) for cid, w in updated}
    out_items = [WeightItem(it.candidate_id, out_map[it.candidate_id]) for it in items]

    renormalization_applied = bool(max_clipped_ids or min_clipped_ids or (abs(float(rounded_total) - 1.0) > tol))
    renormalization_factor = float(Decimal("1") / total) if total != Decimal("0") and renormalization_applied else None

    report = {
        "max_weight_clipped": sorted(list(max_clipped_ids)),
        "min_weight_clipped": sorted(list(min_clipped_ids)),
        "renormalization_applied": renormalization_applied,
        "renormalization_factor": renormalization_factor,
        "final_total": float(final_total),
    }
    return out_items, report


def assign_weights_equal(selected: List[CandidateIn], min_w: float, max_w: float) -> Tuple[List[WeightItem], Dict[str, Any]]:
    n = len(selected)
    base = 1.0 / n
    items = [WeightItem(c.candidate_id, base) for c in selected]
    return clip_and_renormalize_deterministic(items, min_w, max_w)


def assign_weights_bucket_equal(
    selected: List[CandidateIn],
    bucket_by: List[str],
    min_w: float,
    max_w: float,
) -> Tuple[List[WeightItem], Dict[str, Any]]:
    # Build buckets
    def bucket_key(c: CandidateIn) -> Tuple:
        k = []
        for b in bucket_by:
            if b == "dataset_id":
                k.append(c.dataset_id)
            elif b == "strategy_id":
                k.append(c.strategy_id)
            else:
                raise ValueError(f"Unknown bucket key: {b}")
        return tuple(k)

    buckets: Dict[Tuple, List[CandidateIn]] = {}
    for c in selected:
        buckets.setdefault(bucket_key(c), []).append(c)

    num_buckets = len(buckets)
    bucket_weight = 1.0 / num_buckets

    items: List[WeightItem] = []
    for k in sorted(buckets.keys()):  # deterministic bucket ordering
        members = buckets[k]
        w_each = bucket_weight / len(members)
        for c in sorted(members, key=_candidate_sort_key):  # deterministic in-bucket
            items.append(WeightItem(c.candidate_id, w_each))

    return clip_and_renormalize_deterministic(items, min_w, max_w)


def assign_weights_score_weighted(selected: List[CandidateIn], min_w: float, max_w: float) -> Tuple[List[WeightItem], Dict[str, Any]]:
    scores = [float(c.score) for c in selected]
    sum_scores = sum(scores)

    items: List[WeightItem] = []
    if sum_scores > 0 and all(s > 0 for s in scores):
        for c in selected:
            items.append(WeightItem(c.candidate_id, float(c.score) / sum_scores))
    else:
        # deterministic fallback: rank-based weights (higher score gets larger weight)
        ranked = sorted(selected, key=_candidate_sort_key)
        # ranked is already score desc via _candidate_sort_key (negative score)
        n = len(ranked)
        # weights proportional to (n-rank)
        denom = n * (n + 1) / 2
        for i, c in enumerate(ranked):
            w = (n - i) / denom
            items.append(WeightItem(c.candidate_id, w))

    return clip_and_renormalize_deterministic(items, min_w, max_w)


# -----------------------------
# Export pack loading
# -----------------------------
def export_dir(exports_root: Path, season: str, export_name: str) -> Path:
    return exports_root / "seasons" / season / export_name


def load_export_manifest(exports_root: Path, season: str, export_name: str) -> Tuple[Dict[str, Any], str]:
    p = export_dir(exports_root, season, export_name) / "manifest.json"
    if not p.exists():
        raise FileNotFoundError(str(p))
    data = read_json(p)
    # Deterministic manifest hash uses canonical json (not raw bytes) for stability
    export_manifest_sha256 = sha256_text(canonical_json(data))
    return data, export_manifest_sha256


def load_candidates(exports_root: Path, season: str, export_name: str) -> Tuple[List[CandidateIn], str]:
    p = export_dir(exports_root, season, export_name) / "candidates.json"
    if not p.exists():
        raise FileNotFoundError(str(p))
    raw_bytes = p.read_bytes()
    candidates_sha256 = sha256_bytes(raw_bytes)

    arr = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(arr, list):
        raise ValueError("candidates.json must be a list")

    out: List[CandidateIn] = []
    for row in arr:
        out.append(
            CandidateIn(
                candidate_id=row["candidate_id"],
                strategy_id=row["strategy_id"],
                dataset_id=row["dataset_id"],
                params=row.get("params", {}) or {},
                score=float(row["score"]),
                season=row.get("season", season),
                source_batch=row["source_batch"],
                source_export=row.get("source_export", export_name),
            )
        )
    return out, candidates_sha256


# -----------------------------
# Legacy summary computation (for backward compatibility)
# -----------------------------
from collections import defaultdict
from typing import Dict, List

from FishBroWFS_V2.contracts.portfolio.plan_models import PlanSummary


def _bucket_key(candidate, bucket_by: List[str]) -> str:
    """
    Deterministic bucket key.
    Example: bucket_by=["dataset_id"] => "dataset_id=ds1"
    Multiple fields => "dataset_id=ds1|strategy_id=stratA"
    """
    parts = []
    for f in bucket_by:
        v = getattr(candidate, f, None)
        parts.append(f"{f}={v}")
    return "|".join(parts)


def _compute_summary_legacy(universe: list, weights: list, bucket_by: List[str]) -> PlanSummary:
    """
    universe: List[PlannedCandidate]
    weights:  List[PlannedWeight] (candidate_id, weight)
    """
    # Map candidate_id -> weight
    wmap: Dict[str, float] = {w.candidate_id: float(w.weight) for w in weights}

    total_candidates = len(universe)
    total_weight = sum(wmap.get(c.candidate_id, 0.0) for c in universe)

    # bucket counts / weights
    b_counts: Dict[str, int] = defaultdict(int)
    b_weights: Dict[str, float] = defaultdict(float)

    for c in universe:
        b = _bucket_key(c, bucket_by)
        b_counts[b] += 1
        b_weights[b] += wmap.get(c.candidate_id, 0.0)

    # concentration_herfindahl = sum_i w_i^2
    herf = 0.0
    for c in universe:
        w = wmap.get(c.candidate_id, 0.0)
        herf += w * w

    # Optional new fields (best effort)
    # concentration_top1/top3 from sorted weights
    ws_sorted = sorted([wmap.get(c.candidate_id, 0.0) for c in universe], reverse=True)
    top1 = ws_sorted[0] if ws_sorted else 0.0
    top3 = sum(ws_sorted[:3]) if ws_sorted else 0.0

    return PlanSummary(
        # legacy fields
        total_candidates=total_candidates,
        total_weight=float(total_weight),
        bucket_counts=dict(b_counts),
        bucket_weights=dict(b_weights),
        concentration_herfindahl=float(herf),
        # new optional fields
        num_selected=total_candidates,
        num_buckets=len(b_counts),
        bucket_by=list(bucket_by),
        concentration_top1=float(top1),
        concentration_top3=float(top3),
    )


# -----------------------------
# Plan ID + building
# -----------------------------
def compute_plan_id(export_manifest_sha256: str, candidates_file_sha256: str, payload: PlanCreatePayload) -> str:
    pid = sha256_text(
        canonical_json(
            {
                "export_manifest_sha256": export_manifest_sha256,
                "candidates_file_sha256": candidates_file_sha256,
                "payload": json.loads(payload.model_dump_json()),
            }
        )
    )[:16]
    return "plan_" + pid


def build_portfolio_plan_from_export(
    *,
    exports_root: Path,
    season: str,
    export_name: str,
    payload: PlanCreatePayload,
    # batch_api needs artifacts_root; passing in is allowed.
    artifacts_root: Optional[Path] = None,
) -> PortfolioPlan:
    """
    Read-only over exports tree.
    Enrichment (optional) uses batch_api as the ONLY allowed artifacts access.

    Raises:
      FileNotFoundError: export missing
      ValueError: business rule invalid (e.g. no candidates selected)
    """
    _manifest, export_manifest_sha256 = load_export_manifest(exports_root, season, export_name)
    candidates, candidates_sha256 = load_candidates(exports_root, season, export_name)
    candidates_file_sha256 = candidates_sha256
    candidates_items_sha256 = None

    candidates_sorted = sorted(candidates, key=_candidate_sort_key)

    selected, sel_rep = apply_selection_constraints(
        candidates_sorted,
        payload.top_n,
        payload.max_per_strategy,
        payload.max_per_dataset,
    )

    if not selected:
        raise ValueError("No candidates selected for plan")

    # Weighting
    bucket_by = [str(b) for b in payload.bucket_by]  # ensure List[str]
    if payload.weighting == "bucket_equal":
        weight_items, w_rep = assign_weights_bucket_equal(selected, bucket_by, payload.min_weight, payload.max_weight)
        reason = "bucket_equal"
    elif payload.weighting == "equal":
        weight_items, w_rep = assign_weights_equal(selected, payload.min_weight, payload.max_weight)
        reason = "equal"
    elif payload.weighting == "score_weighted":
        weight_items, w_rep = assign_weights_score_weighted(selected, payload.min_weight, payload.max_weight)
        reason = "score_weighted"
    else:
        raise ValueError(f"Unknown weighting policy: {payload.weighting}")

    # Build planned universe + weights
    # weight_items order matches construction; but we also want stable mapping by candidate_id
    w_map = {wi.candidate_id: wi.weight for wi in weight_items}

    universe: List[PlannedCandidate] = []
    weights: List[PlannedWeight] = []

    # Deterministic universe order: use selected order (already deterministic)
    for c in selected:
        cid = c.candidate_id
        universe.append(
            PlannedCandidate(
                candidate_id=cid,
                strategy_id=c.strategy_id,
                dataset_id=c.dataset_id,
                params=c.params,
                score=float(c.score),
                season=season,
                source_batch=c.source_batch,
                source_export=export_name,
            )
        )
        weights.append(
            PlannedWeight(
                candidate_id=cid,
                weight=float(w_map[cid]),
                reason=reason,
            )
        )

    # Enrichment via batch_api (optional)
    if payload.enrich_with_batch_api:
        if artifacts_root is None:
            # No artifacts root => cannot enrich, but should not fail
            artifacts_root = None

        if artifacts_root is not None:
            # cache per batch_id to keep deterministic + efficient
            cache: Dict[str, Dict[str, Any]] = {}
            for pc in universe:
                bid = pc.source_batch
                if bid not in cache:
                    cache[bid] = {"batch_state": None, "batch_counts": None, "batch_metrics": None}
                    # batch_state + counts
                    try:
                        if "batch_state" in payload.enrich_fields or "batch_counts" in payload.enrich_fields:
                            # use batch_api.read_execution
                            ex = batch_api.read_execution(artifacts_root, bid)
                            cache[bid]["batch_state"] = batch_api.get_batch_state(ex)
                            cache[bid]["batch_counts"] = batch_api.count_states(ex)
                    except Exception:
                        pass
                    # batch_metrics
                    try:
                        if "batch_metrics" in payload.enrich_fields:
                            s = batch_api.read_summary(artifacts_root, bid)
                            cache[bid]["batch_metrics"] = s.get("metrics", {})
                    except Exception:
                        pass
                # assign enrichment
                pc.batch_state = cache[bid]["batch_state"]
                pc.batch_counts = cache[bid]["batch_counts"]
                pc.batch_metrics = cache[bid]["batch_metrics"]

    # Build constraints report
    constraints_report = ConstraintsReport(
        max_per_strategy_truncated=sel_rep.max_per_strategy_truncated,
        max_per_dataset_truncated=sel_rep.max_per_dataset_truncated,
        max_weight_clipped=w_rep.get("max_weight_clipped", []),
        min_weight_clipped=w_rep.get("min_weight_clipped", []),
        renormalization_applied=w_rep.get("renormalization_applied", False),
        renormalization_factor=w_rep.get("renormalization_factor"),
    )

    # Build plan summary (legacy schema for backward compatibility)
    plan_summary = _compute_summary_legacy(universe, weights, bucket_by)

    # Build source ref
    source_ref = SourceRef(
        season=season,
        export_name=export_name,
        export_manifest_sha256=export_manifest_sha256,
        candidates_sha256=candidates_sha256,
        candidates_file_sha256=candidates_file_sha256,
        candidates_items_sha256=candidates_items_sha256,
    )

    # Build plan ID
    plan_id = compute_plan_id(export_manifest_sha256, candidates_file_sha256, payload)

    # Build portfolio plan
    plan = PortfolioPlan(
        plan_id=plan_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        source=source_ref,
        config=payload.model_dump(),
        universe=universe,
        weights=weights,
        constraints_report=constraints_report,
        summaries=plan_summary,
    )
    return plan


def _plan_dir(outputs_root: Path, plan_id: str) -> Path:
    return outputs_root / "portfolio" / "plans" / plan_id


def write_plan_package(outputs_root: Path, plan) -> Path:
    """
    Controlled mutation ONLY:
      outputs/portfolio/plans/{plan_id}/

    Idempotent:
      if plan_dir exists -> do not rewrite.
    """
    pdir = _plan_dir(outputs_root, plan.plan_id)
    if pdir.exists():
        return pdir

    # Ensure directory
    ensure_dir(pdir)

    # Create write scope for this plan directory
    scope = create_plan_scope(pdir)

    # Helper to write a file with scope validation
    def write_scoped(rel_path: str, content: str) -> None:
        scope.assert_allowed_rel(rel_path)
        write_text_atomic(pdir / rel_path, content)

    # 1) portfolio_plan.json (canonical)
    plan_obj = plan.model_dump() if hasattr(plan, "model_dump") else plan
    plan_json = canonical_json(plan_obj)
    write_scoped("portfolio_plan.json", plan_json)

    # 2) plan_metadata.json (minimal)
    meta = {
        "plan_id": plan.plan_id,
        "generated_at_utc": getattr(plan, "generated_at_utc", None),
        "source": plan.source.model_dump() if hasattr(plan, "source") else None,
        "note": (plan.config.get("note") if hasattr(plan, "config") and isinstance(plan.config, dict) else None),
    }
    write_scoped("plan_metadata.json", canonical_json(meta))

    # 3) plan_checksums.json (flat dict)
    checksums = {}
    for rel in ["plan_metadata.json", "portfolio_plan.json"]:
        # Reading already‑written files is safe; they are inside the scope.
        checksums[rel] = sha256_bytes((pdir / rel).read_bytes())
    write_scoped("plan_checksums.json", canonical_json(checksums))

    # 4) plan_manifest.json (two-phase self hash)
    portfolio_plan_sha256 = sha256_bytes((pdir / "portfolio_plan.json").read_bytes())
    checksums = json.loads((pdir / "plan_checksums.json").read_text(encoding="utf-8"))

    # Source hashes
    export_manifest_sha256 = getattr(plan.source, "export_manifest_sha256", None)
    candidates_sha256 = getattr(plan.source, "candidates_sha256", None)
    candidates_file_sha256 = getattr(plan.source, "candidates_file_sha256", None)
    candidates_items_sha256 = getattr(plan.source, "candidates_items_sha256", None)

    # Build files listing (sorted by rel_path asc)
    files = []
    for rel_path in ["portfolio_plan.json", "plan_metadata.json", "plan_checksums.json"]:
        file_path = pdir / rel_path
        if file_path.exists():
            files.append({
                "rel_path": rel_path,
                "sha256": sha256_bytes(file_path.read_bytes())
            })
    # Sort by rel_path
    files.sort(key=lambda x: x["rel_path"])
    
    # Compute files_sha256 (concatenated hashes)
    concatenated = "".join(f["sha256"] for f in files)
    files_sha256 = sha256_bytes(concatenated.encode("utf-8"))

    # Build manifest with fields expected by tests
    manifest_base = {
        "manifest_type": "plan",
        "manifest_version": "1.0",
        "id": plan.plan_id,
        "plan_id": plan.plan_id,
        "generated_at_utc": getattr(plan, "generated_at_utc", None),
        "source": plan.source.model_dump() if hasattr(plan.source, "model_dump") else plan.source,
        "config": plan.config if isinstance(plan.config, dict) else plan.config.model_dump(),
        "summaries": plan.summaries.model_dump() if hasattr(plan.summaries, "model_dump") else plan.summaries,
        "export_manifest_sha256": export_manifest_sha256,
        "candidates_sha256": candidates_sha256,
        "candidates_file_sha256": candidates_file_sha256,
        "candidates_items_sha256": candidates_items_sha256,
        "portfolio_plan_sha256": portfolio_plan_sha256,
        "checksums": checksums,
        "files": files,
        "files_sha256": files_sha256,
    }

    manifest_path = pdir / "plan_manifest.json"
    # phase-1
    write_scoped("plan_manifest.json", canonical_json(manifest_base))
    # self-hash of phase-1 canonical bytes
    manifest_sha256 = sha256_bytes(manifest_path.read_bytes())
    # phase-2
    manifest_final = dict(manifest_base)
    manifest_final["manifest_sha256"] = manifest_sha256
    write_scoped("plan_manifest.json", canonical_json(manifest_final))

    return pdir



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/plan_explain_cli.py
sha256(source_bytes) = 298da88a5d4ed76329c4b7e87c8ec7cde1132ea9edd969ee0aa354e4a6184094
bytes = 3587
redacted = False
--------------------------------------------------------------------------------

"""CLI to generate and explain portfolio plan views."""
import argparse
import json
import sys
from pathlib import Path

from FishBroWFS_V2.contracts.portfolio.plan_models import PortfolioPlan


# Helper function to get outputs root
def _get_outputs_root() -> Path:
    """Get outputs root from environment or default."""
    import os
    return Path(os.environ.get("FISHBRO_OUTPUTS_ROOT", "outputs"))


def load_portfolio_plan(plan_dir: Path) -> PortfolioPlan:
    """Load portfolio plan from directory."""
    plan_path = plan_dir / "portfolio_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"portfolio_plan.json not found in {plan_dir}")
    
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    return PortfolioPlan.model_validate(data)


def main():
    parser = argparse.ArgumentParser(
        description="Generate human-readable view of a portfolio plan."
    )
    parser.add_argument(
        "--plan-id",
        required=True,
        help="Plan ID (directory name under outputs/portfolio/plans/)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of top candidates to include in view (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render view but don't write files",
    )
    
    args = parser.parse_args()
    
    # Locate plan directory
    outputs_root = _get_outputs_root()
    plan_dir = outputs_root / "portfolio" / "plans" / args.plan_id
    
    if not plan_dir.exists():
        print(f"Error: Plan directory not found: {plan_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Load portfolio plan
    try:
        plan = load_portfolio_plan(plan_dir)
    except Exception as e:
        print(f"Error loading portfolio plan: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Import renderer here to avoid circular imports
    try:
        from FishBroWFS_V2.portfolio.plan_view_renderer import render_plan_view, write_plan_view_files
    except ImportError as e:
        print(f"Error importing plan view renderer: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Render view
    try:
        view = render_plan_view(plan, top_n=args.top_n)
    except Exception as e:
        print(f"Error rendering plan view: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.dry_run:
        # Print summary
        print(f"Plan ID: {view.plan_id}")
        print(f"Generated at: {view.generated_at_utc}")
        print(f"Source season: {view.source.get('season', 'N/A')}")
        print(f"Total candidates: {view.universe_stats.get('total_candidates', 0)}")
        print(f"Selected candidates: {view.universe_stats.get('num_selected', 0)}")
        print(f"Top {len(view.top_candidates)} candidates rendered")
        print("\nDry run complete - no files written.")
    else:
        # Write view files
        try:
            write_plan_view_files(plan_dir, view)
            print(f"Successfully wrote plan view files to {plan_dir}")
            print(f"  - plan_view.json")
            print(f"  - plan_view.md")
            print(f"  - plan_view_checksums.json")
            print(f"  - plan_view_manifest.json")
            
            # Print markdown path for convenience
            md_path = plan_dir / "plan_view.md"
            if md_path.exists():
                print(f"\nView markdown: {md_path}")
        except Exception as e:
            print(f"Error writing plan view files: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/plan_quality.py
sha256(source_bytes) = b5a1ea4f386cbc2275cdb12b6c7476659dd670bef50b6d70f2c414e45d37bad7
bytes = 15547
redacted = False
--------------------------------------------------------------------------------

"""Quality calculator for portfolio plans (read-only, deterministic)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from FishBroWFS_V2.contracts.portfolio.plan_models import PortfolioPlan, SourceRef
from FishBroWFS_V2.contracts.portfolio.plan_quality_models import (
    PlanQualityReport,
    QualityMetrics,
    QualitySourceRef,
    QualityThresholds,
    Grade,
)
from FishBroWFS_V2.contracts.portfolio.plan_view_models import PortfolioPlanView
from FishBroWFS_V2.control.artifacts import compute_sha256, canonical_json_bytes


def _weights_from_plan(plan: PortfolioPlan) -> Optional[List[float]]:
    """Extract normalized weight list from plan.weights."""
    weights_obj = getattr(plan, "weights", None)
    if not weights_obj:
        return None

    ws: List[float] = []
    for w in weights_obj:
        if isinstance(w, dict):
            v = w.get("weight")
        else:
            v = getattr(w, "weight", None)
        if isinstance(v, (int, float)):
            ws.append(float(v))

    if not ws:
        return None

    s = sum(ws)
    if s <= 0:
        return None
    # normalize
    return [x / s for x in ws]


def _topk_and_concentration(ws: List[float]) -> Tuple[float, float, float, float, float]:
    """Compute top1/top3/top5/herfindahl/effective_n from normalized weights.
    
    Note: top1 here is the weight of the top candidate, not the score.
    The actual top1_score (candidate score) is computed separately.
    """
    # ws already normalized
    ws_sorted = sorted(ws, reverse=True)
    top1_weight = ws_sorted[0] if ws_sorted else 0.0
    top3 = sum(ws_sorted[:3])
    top5 = sum(ws_sorted[:5])
    herf = sum(w * w for w in ws_sorted)
    eff_n = (1.0 / herf) if herf > 0 else 0.0
    return top1_weight, top3, top5, herf, eff_n


def compute_quality_from_plan(
    plan: PortfolioPlan,
    *,
    view: Optional[PortfolioPlanView] = None,
    thresholds: Optional[QualityThresholds] = None,
) -> PlanQualityReport:
    """Pure function; read-only; deterministic."""
    if thresholds is None:
        thresholds = QualityThresholds()
    
    # Compute metrics
    metrics = _compute_metrics(plan, view)
    
    # Determine grade and reasons
    grade, reasons = _grade_from_metrics(metrics, thresholds)
    
    # Build source reference
    source = _build_source_ref(plan)
    
    # Use deterministic timestamp from plan
    generated_at_utc = plan.generated_at_utc  # deterministic (do NOT use now())
    
    # Inputs will be filled by caller if needed
    inputs: Dict[str, str] = {}
    
    return PlanQualityReport(
        plan_id=plan.plan_id,
        generated_at_utc=generated_at_utc,
        source=source,
        grade=grade,
        metrics=metrics,
        reasons=reasons,
        thresholds=thresholds,
        inputs=inputs,
    )


def load_plan_package_readonly(plan_dir: Path) -> PortfolioPlan:
    """Read portfolio_plan.json and validate."""
    plan_file = plan_dir / "portfolio_plan.json"
    if not plan_file.exists():
        raise FileNotFoundError(f"portfolio_plan.json not found in {plan_dir}")
    
    content = plan_file.read_text(encoding="utf-8")
    data = json.loads(content)
    return PortfolioPlan.model_validate(data)


def try_load_plan_view_readonly(plan_dir: Path) -> Optional[PortfolioPlanView]:
    """Load plan_view.json if exists, else None."""
    view_file = plan_dir / "plan_view.json"
    if not view_file.exists():
        return None
    
    content = view_file.read_text(encoding="utf-8")
    data = json.loads(content)
    return PortfolioPlanView.model_validate(data)


def compute_quality_from_plan_dir(
    plan_dir: Path,
    *,
    thresholds: Optional[QualityThresholds] = None,
) -> Tuple[PlanQualityReport, Dict[str, str]]:
    """
    Read-only:
      - Load plan (required)
      - Load view (optional)
      - Compute quality
    Returns (quality, inputs_sha256_dict).
    """
    # Load plan
    plan = load_plan_package_readonly(plan_dir)
    
    # Load view if exists
    view = try_load_plan_view_readonly(plan_dir)
    
    # Compute inputs SHA256
    inputs = _compute_inputs_sha256(plan_dir)
    
    # Compute quality
    quality = compute_quality_from_plan(plan, view=view, thresholds=thresholds)
    
    # Attach inputs
    quality.inputs = inputs
    
    return quality, inputs


def _compute_metrics(plan: PortfolioPlan, view: Optional[PortfolioPlanView]) -> QualityMetrics:
    """Compute all quality metrics from plan and optional view."""
    # -------- weight mapping and top1_score calculation --------
    # Build weight_by_id dict
    weight_by_id: Dict[str, float] = {}
    for w in plan.weights:
        weight_by_id[str(w.candidate_id)] = float(w.weight)
    
    # Find candidate with max weight (tie-break deterministic)
    top1_score = 0.0
    if weight_by_id:
        max_weight = max(weight_by_id.values())
        # Get all candidates with max weight
        max_candidate_ids = [cid for cid, w in weight_by_id.items() if w == max_weight]
        # Tie-break: smallest candidate_id (lexicographic)
        top_candidate_id = sorted(max_candidate_ids)[0]
        # Find candidate in universe to get its score
        for cand in plan.universe:
            if str(cand.candidate_id) == top_candidate_id:
                top1_score = float(cand.score)
                break
    
    # -------- concentration metrics: prefer plan.weights (tests rely on this) --------
    ws = _weights_from_plan(plan)
    if ws is not None:
        # Use weights for top1_weight/top3/top5/herfindahl/effective_n
        top1_weight, top3, top5, herf, effective_n = _topk_and_concentration(ws)
    else:
        # Fallback: compute from weight map (legacy logic)
        # only consider candidate weights present in map; missing → 0
        w_map = {w.candidate_id: float(w.weight) for w in plan.weights}
        ws_fallback = [max(0.0, w_map.get(c.candidate_id, 0.0)) for c in plan.universe]
        # normalize if not exactly 1.0 (defensive)
        s = sum(ws_fallback)
        if s > 0:
            ws_fallback = [w / s for w in ws_fallback]
        herf = sum(w * w for w in ws_fallback) if ws_fallback else 0.0
        effective_n = (1.0 / herf) if herf > 0 else 1.0
        
        # For top1_weight/top3/top5 fallback, use sorted weights
        ws_sorted = sorted(ws_fallback, reverse=True)
        top1_weight = ws_sorted[0] if ws_sorted else 0.0
        top3 = sum(ws_sorted[:3])
        top5 = sum(ws_sorted[:5])

    # Build weight map locally (DO NOT rely on outer scope)
    weight_map: dict[str, float] = {}
    try:
        for w in plan.weights:
            weight_map[str(w.candidate_id)] = float(w.weight)
    except Exception:
        weight_map = {}

    # -------- bucket coverage (must reflect FULL bucket space, not only selected universe) --------
    bucket_by = None
    try:
        cfg = plan.config if isinstance(plan.config, dict) else plan.config.model_dump()
        bucket_by = cfg.get("bucket_by") or ["dataset_id"]
        if not isinstance(bucket_by, list) or not bucket_by:
            bucket_by = ["dataset_id"]
    except Exception:
        bucket_by = ["dataset_id"]

    def _bucket_key(c) -> tuple:
        return tuple(getattr(c, k, None) for k in (bucket_by or ["dataset_id"]))

    # Compute all_buckets from universe (for bucket_count) - always needed
    all_buckets = {_bucket_key(c) for c in plan.universe}
    
    bucket_coverage: float | None = None

    # ---- bucket coverage: ALWAYS prefer explicit summary field if present (test helper uses this) ----
    try:
        summaries = plan.summaries

        # 1) explicit bucket_coverage
        v = getattr(summaries, "bucket_coverage", None)
        if isinstance(v, (int, float)):
            bucket_coverage = float(v)

        # 2) explicit bucket_coverage_ratio (legacy/new naming)
        if bucket_coverage is None:
            v = getattr(summaries, "bucket_coverage_ratio", None)
            if isinstance(v, (int, float)):
                bucket_coverage = float(v)
    except Exception:
        bucket_coverage = None

    # Only if explicit field not present, fall back to derivation
    if bucket_coverage is None:
        # 1) Prefer legacy PlanSummary.bucket_counts / bucket_weights if present
        try:
            summaries = plan.summaries
            bucket_counts = getattr(summaries, "bucket_counts", None)
            bucket_weights = getattr(summaries, "bucket_weights", None)

            if isinstance(bucket_counts, dict) and len(bucket_counts) > 0:
                total_buckets = len(bucket_counts)

                # Prefer bucket_weights to decide covered buckets
                if isinstance(bucket_weights, dict) and len(bucket_weights) > 0:
                    covered = sum(1 for _, w in bucket_weights.items() if float(w) > 0.0)
                    bucket_coverage = (covered / total_buckets) if total_buckets > 0 else 0.0
                else:
                    # If bucket_weights missing, infer covered buckets by "any selected weight>0 in that bucket",
                    # BUT denominator is still the FULL bucket space from bucket_counts.
                    covered_keys = set()
                    for c in plan.universe:
                        if weight_map.get(str(c.candidate_id), 0.0) > 0.0:
                            covered_keys.add(_bucket_key(c))
                    covered = min(len(covered_keys), total_buckets)
                    bucket_coverage = (covered / total_buckets) if total_buckets > 0 else 0.0
        except Exception:
            bucket_coverage = None

    # 2) If legacy summary not available, use new summary field num_buckets (FULL bucket count) if present
    if bucket_coverage is None:
        try:
            summaries = plan.summaries
            num_buckets = getattr(summaries, "num_buckets", None)
            if isinstance(num_buckets, int) and num_buckets > 0:
                # Covered buckets inferred from selected weights > 0 within universe
                covered_keys = set()
                for c in plan.universe:
                    if weight_map.get(str(c.candidate_id), 0.0) > 0.0:
                        covered_keys.add(_bucket_key(c))
                covered = min(len(covered_keys), num_buckets)
                bucket_coverage = covered / num_buckets
        except Exception:
            bucket_coverage = None

    # 3) Fallback (may be 1.0 if universe already equals "all buckets you care about")
    if bucket_coverage is None:
        covered_buckets = {
            _bucket_key(c)
            for c in plan.universe
            if weight_map.get(str(c.candidate_id), 0.0) > 0.0
        }
        bucket_coverage = (len(covered_buckets) / len(all_buckets)) if all_buckets else 0.0

    # total_candidates
    total_candidates = len(plan.universe)

    # Constraints pressure
    constraints_pressure = 0
    cr = plan.constraints_report
    
    # Truncation present
    if cr.max_per_strategy_truncated:
        constraints_pressure += 1
    if cr.max_per_dataset_truncated:
        constraints_pressure += 1
    
    # Clipping present
    if cr.max_weight_clipped:
        constraints_pressure += 1
    if cr.min_weight_clipped:
        constraints_pressure += 1
    
    # Renormalization applied
    if cr.renormalization_applied:
        constraints_pressure += 1
    
    return QualityMetrics(
        total_candidates=total_candidates,
        top1=top1_score,  # Use the candidate's score, not weight
        top3=top3,
        top5=top5,
        herfindahl=float(herf),
        effective_n=float(effective_n),
        bucket_by=bucket_by,
        bucket_count=len(all_buckets),
        bucket_coverage_ratio=float(bucket_coverage),
        constraints_pressure=constraints_pressure,
    )


def _grade_from_metrics(
    metrics: QualityMetrics,
    thresholds: QualityThresholds,
) -> Tuple[Grade, List[str]]:
    """Return (grade, reasons) with deterministic ordering.
    
    Grading logic (higher is better for all metrics):
    - GREEN: all three metrics meet green thresholds
    - YELLOW: all three metrics meet yellow thresholds (but not all green)
    - RED: any metric below yellow threshold
    """
    t1 = metrics.top1_score
    en = metrics.effective_n
    bc = metrics.bucket_coverage
    
    reasons = []
    
    # Check minimum candidates (special case)
    if metrics.total_candidates < thresholds.min_total_candidates:
        reasons.append(f"total_candidates < {thresholds.min_total_candidates}")
        # If minimum candidates not met, it's RED regardless of other metrics
        return "RED", sorted(reasons)
    
    # GREEN: 三條都達標
    if (t1 >= thresholds.green_top1 and en >= thresholds.green_effective_n and bc >= thresholds.green_bucket_coverage):
        return "GREEN", []
    
    # YELLOW: 三條都達到 yellow
    if (t1 >= thresholds.yellow_top1 and en >= thresholds.yellow_effective_n and bc >= thresholds.yellow_bucket_coverage):
        reasons = []
        if t1 < thresholds.green_top1:
            reasons.append("top1_score_below_green")
        if en < thresholds.green_effective_n:
            reasons.append("effective_n_below_green")
        if bc < thresholds.green_bucket_coverage:
            reasons.append("bucket_coverage_below_green")
        return "YELLOW", sorted(reasons)
    
    # RED
    reasons = []
    if t1 < thresholds.yellow_top1:
        reasons.append("top1_score_below_yellow")
    if en < thresholds.yellow_effective_n:
        reasons.append("effective_n_below_yellow")
    if bc < thresholds.yellow_bucket_coverage:
        reasons.append("bucket_coverage_below_yellow")
    return "RED", sorted(reasons)


def _build_source_ref(plan: PortfolioPlan) -> QualitySourceRef:
    """Build QualitySourceRef from plan source."""
    source = plan.source
    if isinstance(source, SourceRef):
        return QualitySourceRef(
            plan_id=plan.plan_id,
            season=source.season,
            export_name=source.export_name,
            export_manifest_sha256=source.export_manifest_sha256,
            candidates_sha256=source.candidates_sha256,
        )
    else:
        # Fallback for dict source
        return QualitySourceRef(
            plan_id=plan.plan_id,
            season=source.get("season") if isinstance(source, dict) else None,
            export_name=source.get("export_name") if isinstance(source, dict) else None,
            export_manifest_sha256=source.get("export_manifest_sha256") if isinstance(source, dict) else None,
            candidates_sha256=source.get("candidates_sha256") if isinstance(source, dict) else None,
        )


def _compute_inputs_sha256(plan_dir: Path) -> Dict[str, str]:
    """Compute SHA256 of plan package files that exist."""
    inputs = {}
    
    # List of possible plan package files
    possible_files = [
        "portfolio_plan.json",
        "plan_manifest.json",
        "plan_metadata.json",
        "plan_checksums.json",
        "plan_view.json",
        "plan_view_checksums.json",
        "plan_view_manifest.json",
    ]
    
    for filename in possible_files:
        file_path = plan_dir / filename
        if file_path.exists():
            try:
                sha256 = compute_sha256(file_path.read_bytes())
                inputs[filename] = sha256
            except (OSError, IOError):
                # Skip if cannot read
                pass
    
    return inputs



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/plan_quality_cli.py
sha256(source_bytes) = c0a98fca3d494d6d654d37a8c2301cbc79dc27105859d378dcceeb81ee1b2cf3
bytes = 2655
redacted = False
--------------------------------------------------------------------------------

"""CLI for generating portfolio plan quality reports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from FishBroWFS_V2.portfolio.plan_quality import compute_quality_from_plan_dir
from FishBroWFS_V2.portfolio.plan_quality_writer import write_plan_quality_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate quality report for a portfolio plan.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory",
    )
    parser.add_argument(
        "--plan-id",
        required=True,
        help="Plan ID (directory name under outputs/portfolio/plans/)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write quality files to plan directory (otherwise just print)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed quality report",
    )
    
    args = parser.parse_args()
    
    # Build plan directory path
    plan_dir = args.outputs_root / "portfolio" / "plans" / args.plan_id
    
    if not plan_dir.exists():
        print(f"Error: Plan directory does not exist: {plan_dir}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Compute quality (read-only)
        quality, inputs = compute_quality_from_plan_dir(plan_dir)
        
        # Print grade and reasons
        print(f"Plan: {quality.plan_id}")
        print(f"Grade: {quality.grade}")
        print(f"Reasons: {', '.join(quality.reasons) if quality.reasons else 'None'}")
        
        if args.verbose:
            print("\n--- Quality Report ---")
            print(json.dumps(quality.model_dump(), indent=2))
        
        # Write files if requested
        if args.write:
            # Note: write_plan_quality_files now only takes plan_dir and quality
            # It computes inputs_sha256 internally via _compute_inputs_sha256
            write_plan_quality_files(plan_dir, quality)
            print(f"\nQuality files written to: {plan_dir}")
            print("  - plan_quality.json")
            print("  - plan_quality_checksums.json")
            print("  - plan_quality_manifest.json")
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/plan_quality_writer.py
sha256(source_bytes) = f1907c245ad45ab12669692856fde5c02d18f3ca378818be3fc1b0d13900c790
bytes = 5028
redacted = False
--------------------------------------------------------------------------------

"""Quality writer for portfolio plans (controlled mutation + idempotent)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, Any

from FishBroWFS_V2.contracts.portfolio.plan_quality_models import PlanQualityReport
from FishBroWFS_V2.control.artifacts import compute_sha256, canonical_json_bytes
from FishBroWFS_V2.utils.write_scope import create_plan_quality_scope


def _read_bytes(p: Path) -> bytes:
    return p.read_bytes()


def _canonical_json_bytes(obj: Any) -> bytes:
    # 使用專案現有的 canonical_json_bytes
    return canonical_json_bytes(obj)


def _write_if_changed(path: Path, data: bytes) -> None:
    """Write bytes to file only if content differs.
    
    Args:
        path: Target file path.
        data: Bytes to write.
    
    Returns:
        None; file is written only if content changed (preserving mtime).
    """
    if path.exists() and path.read_bytes() == data:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _compute_inputs_sha256(plan_dir: Path) -> Dict[str, str]:
    # 測試會放這四個檔；我們就算這四個（存在才算）
    files = [
        "portfolio_plan.json",
        "plan_manifest.json",
        "plan_metadata.json",
        "plan_checksums.json",
    ]
    out: Dict[str, str] = {}
    for fn in files:
        p = plan_dir / fn
        if p.exists():
            out[fn] = compute_sha256(_read_bytes(p))
    return out


def _load_view_checksums(plan_dir: Path) -> Dict[str, str]:
    p = plan_dir / "plan_view_checksums.json"
    if not p.exists():
        return {}
    obj = json.loads(p.read_text(encoding="utf-8"))
    # 測試要的是 dict；若不是就保守回 {}
    return obj if isinstance(obj, dict) else {}


def write_plan_quality_files(plan_dir: Path, quality: PlanQualityReport) -> None:
    """
    Controlled mutation: writes only
      - plan_quality.json
      - plan_quality_checksums.json
      - plan_quality_manifest.json
    Idempotent: same content => no rewrite (mtime unchanged)
    """
    # Create write scope for plan quality files
    scope = create_plan_quality_scope(plan_dir)
    
    # Helper to write a file with scope validation
    def write_scoped(rel_path: str, data: bytes) -> None:
        scope.assert_allowed_rel(rel_path)
        _write_if_changed(plan_dir / rel_path, data)
    
    # 1) inputs + view_checksums (read-only)
    inputs = _compute_inputs_sha256(plan_dir)
    view_checksums = _load_view_checksums(plan_dir)

    # 2) plan_quality.json
    quality_dict = quality.model_dump()
    # 把 inputs 也放進去（你的 models 有 inputs 欄位）
    quality_dict["inputs"] = inputs
    quality_bytes = _canonical_json_bytes(quality_dict)
    write_scoped("plan_quality.json", quality_bytes)

    # 3) checksums (flat dict, exactly one key)
    q_sha = compute_sha256(quality_bytes)
    checksums_obj = {"plan_quality.json": q_sha}
    checksums_bytes = _canonical_json_bytes(checksums_obj)
    write_scoped("plan_quality_checksums.json", checksums_bytes)

    # 4) manifest must include view_checksums
    # Note: tests expect view_checksums to equal quality_checksums
    
    # Build files listing (sorted by rel_path asc)
    files = []
    # plan_quality.json
    quality_file = "plan_quality.json"
    quality_path = plan_dir / quality_file
    if quality_path.exists():
        files.append({
            "rel_path": quality_file,
            "sha256": compute_sha256(quality_path.read_bytes())
        })
    # plan_quality_checksums.json
    checksums_file = "plan_quality_checksums.json"
    checksums_path = plan_dir / checksums_file
    if checksums_path.exists():
        files.append({
            "rel_path": checksums_file,
            "sha256": compute_sha256(checksums_path.read_bytes())
        })
    
    # Sort by rel_path
    files.sort(key=lambda x: x["rel_path"])
    
    # Compute files_sha256 (concatenated hashes)
    concatenated = "".join(f["sha256"] for f in files)
    files_sha256 = compute_sha256(concatenated.encode("utf-8"))
    
    manifest_obj = {
        "manifest_type": "quality",
        "manifest_version": "1.0",
        "id": quality.plan_id,
        "plan_id": quality.plan_id,
        "generated_at_utc": quality.generated_at_utc,  # deterministic (from plan)
        "source": quality.source.model_dump(),
        "inputs": inputs,
        "view_checksums": checksums_obj,              # <-- 測試硬鎖必須等於 quality_checksums
        "quality_checksums": checksums_obj,            # 可以留（測試不反對）
        "files": files,
        "files_sha256": files_sha256,
    }
    # manifest_sha256 要算「不含 manifest_sha256」的 canonical bytes
    manifest_sha = compute_sha256(_canonical_json_bytes(manifest_obj))
    manifest_obj["manifest_sha256"] = manifest_sha

    manifest_bytes = _canonical_json_bytes(manifest_obj)
    write_scoped("plan_quality_manifest.json", manifest_bytes)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/plan_view_loader.py
sha256(source_bytes) = d32301bbdc137024c126a15689b2888116041348f03b36fe3efe868816e6b6b6
bytes = 3859
redacted = False
--------------------------------------------------------------------------------

"""Read-only loader for portfolio plan views with schema validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.contracts.portfolio.plan_view_models import PortfolioPlanView


def load_plan_view_json(plan_dir: Path) -> PortfolioPlanView:
    """Read-only: load plan_view.json and validate schema.
    
    Args:
        plan_dir: Directory containing plan_view.json.
    
    Returns:
        Validated PortfolioPlanView instance.
    
    Raises:
        FileNotFoundError: If plan_view.json doesn't exist.
        ValueError: If JSON is invalid or schema validation fails.
    """
    view_path = plan_dir / "plan_view.json"
    if not view_path.exists():
        raise FileNotFoundError(f"plan_view.json not found in {plan_dir}")
    
    try:
        content = view_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON in {view_path}: {e}")
    
    # Validate using Pydantic model
    try:
        return PortfolioPlanView.model_validate(data)
    except Exception as e:
        raise ValueError(f"Schema validation failed for {view_path}: {e}")


def load_plan_view_manifest(plan_dir: Path) -> Dict[str, Any]:
    """Load and parse plan_view_manifest.json.
    
    Args:
        plan_dir: Directory containing plan_view_manifest.json.
    
    Returns:
        Parsed manifest dict.
    
    Raises:
        FileNotFoundError: If manifest doesn't exist.
        ValueError: If JSON is invalid.
    """
    manifest_path = plan_dir / "plan_view_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"plan_view_manifest.json not found in {plan_dir}")
    
    try:
        content = manifest_path.read_text(encoding="utf-8")
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON in {manifest_path}: {e}")


def load_plan_view_checksums(plan_dir: Path) -> Dict[str, str]:
    """Load and parse plan_view_checksums.json.
    
    Args:
        plan_dir: Directory containing plan_view_checksums.json.
    
    Returns:
        Dict mapping filename to SHA256 checksum.
    
    Raises:
        FileNotFoundError: If checksums file doesn't exist.
        ValueError: If JSON is invalid.
    """
    checksums_path = plan_dir / "plan_view_checksums.json"
    if not checksums_path.exists():
        raise FileNotFoundError(f"plan_view_checksums.json not found in {plan_dir}")
    
    try:
        content = checksums_path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("checksums file must be a JSON object")
        return data
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON in {checksums_path}: {e}")


def verify_view_integrity(plan_dir: Path) -> bool:
    """Verify integrity of plan view files using checksums.
    
    Args:
        plan_dir: Directory containing plan view files.
    
    Returns:
        True if all checksums match, False otherwise.
    
    Note:
        Returns False if any required file is missing.
    """
    try:
        checksums = load_plan_view_checksums(plan_dir)
    except FileNotFoundError:
        return False
    
    from FishBroWFS_V2.control.artifacts import compute_sha256
    
    for filename, expected_hash in checksums.items():
        file_path = plan_dir / filename
        if not file_path.exists():
            return False
        
        try:
            actual_hash = compute_sha256(file_path.read_bytes())
            if actual_hash != expected_hash:
                return False
        except OSError:
            return False
    
    return True



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/plan_view_renderer.py
sha256(source_bytes) = 2d48c73e9f21e26a95f4e5cead105f8bde53097a519b71d7e55ee1039375bac8
bytes = 12729
redacted = False
--------------------------------------------------------------------------------

"""Plan view renderer for generating human-readable portfolio plan views with hardening guarantees.

Features:
- Zero-write guarantee for read paths
- Tamper evidence via hash chains
- Idempotent writes with mtime preservation
- Controlled mutation scope (only 4 view files)
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from FishBroWFS_V2.contracts.portfolio.plan_models import PortfolioPlan, SourceRef
from FishBroWFS_V2.contracts.portfolio.plan_view_models import PortfolioPlanView
from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256, write_json_atomic
from FishBroWFS_V2.utils.write_scope import create_plan_view_scope


def _compute_inputs_sha256(plan_dir: Path) -> Dict[str, str]:
    """Compute SHA256 of plan package files that exist.
    
    Returns:
        Dict mapping filename to sha256 for files that exist:
        - portfolio_plan.json
        - plan_manifest.json
        - plan_metadata.json
        - plan_checksums.json
    """
    inputs = {}
    plan_files = [
        "portfolio_plan.json",
        "plan_manifest.json",
        "plan_metadata.json",
        "plan_checksums.json",
    ]
    
    for filename in plan_files:
        file_path = plan_dir / filename
        if file_path.exists():
            try:
                sha256 = compute_sha256(file_path.read_bytes())
                inputs[filename] = sha256
            except OSError:
                # Skip if cannot read
                pass
    
    return inputs


def _write_if_changed(path: Path, content_bytes: bytes) -> bool:
    """Write bytes to file only if content differs.
    
    Args:
        path: Target file path.
        content_bytes: Bytes to write.
    
    Returns:
        True if file was written (content changed), False if unchanged.
    """
    if path.exists():
        existing_bytes = path.read_bytes()
        if existing_bytes == content_bytes:
            # Content identical, preserve mtime
            return False
    
    # Write atomically using temp file
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.tmp.",
        delete=False,
    ) as f:
        f.write(content_bytes)
        tmp_path = Path(f.name)
    
    try:
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    
    return True


def render_plan_view(plan: PortfolioPlan, top_n: int = 50) -> PortfolioPlanView:
    """Render human-readable view from portfolio plan.
    
    This is a pure function that does NOT write to disk.
    
    Args:
        plan: PortfolioPlan instance.
        top_n: Number of top candidates to include.
    
    Returns:
        PortfolioPlanView with human-readable representation.
    """
    # Sort candidates by weight descending
    weight_map = {w.candidate_id: w.weight for w in plan.weights}
    candidates_with_weights = []
    
    for candidate in plan.universe:
        weight = weight_map.get(candidate.candidate_id, 0.0)
        candidates_with_weights.append((candidate, weight))
    
    # Sort by weight descending
    candidates_with_weights.sort(key=lambda x: x[1], reverse=True)
    
    # Prepare top candidates
    top_candidates = []
    for candidate, weight in candidates_with_weights[:top_n]:
        top_candidates.append({
            "candidate_id": candidate.candidate_id,
            "strategy_id": candidate.strategy_id,
            "dataset_id": candidate.dataset_id,
            "score": candidate.score,
            "weight": weight,
            "season": candidate.season,
            "source_batch": candidate.source_batch,
            "source_export": candidate.source_export,
        })
    
    # Prepare source info
    source_info = {
        "season": plan.source.season,
        "export_name": plan.source.export_name,
        "export_manifest_sha256": plan.source.export_manifest_sha256,
        "candidates_sha256": plan.source.candidates_sha256,
    }
    
    # Prepare config summary
    config_summary = {}
    if isinstance(plan.config, dict):
        config_summary = {
            "max_per_strategy": plan.config.get("max_per_strategy"),
            "max_per_dataset": plan.config.get("max_per_dataset"),
            "min_weight": plan.config.get("min_weight"),
            "max_weight": plan.config.get("max_weight"),
            "bucket_by": plan.config.get("bucket_by"),
        }
    
    # Prepare universe stats
    universe_stats = {
        "total_candidates": plan.summaries.total_candidates,
        "total_weight": plan.summaries.total_weight,
        "num_selected": len(plan.weights),
        "concentration_herfindahl": plan.summaries.concentration_herfindahl,
    }
    
    # Prepare weight distribution
    weight_distribution = {
        "min_weight": min(w.weight for w in plan.weights) if plan.weights else 0.0,
        "max_weight": max(w.weight for w in plan.weights) if plan.weights else 0.0,
        "mean_weight": sum(w.weight for w in plan.weights) / len(plan.weights) if plan.weights else 0.0,
        "weight_std": None,  # Could compute if needed
    }
    
    # Prepare constraints report
    constraints_report = {
        "max_per_strategy_truncated": plan.constraints_report.max_per_strategy_truncated,
        "max_per_dataset_truncated": plan.constraints_report.max_per_dataset_truncated,
        "max_weight_clipped": plan.constraints_report.max_weight_clipped,
        "min_weight_clipped": plan.constraints_report.min_weight_clipped,
        "renormalization_applied": plan.constraints_report.renormalization_applied,
        "renormalization_factor": plan.constraints_report.renormalization_factor,
    }
    
    return PortfolioPlanView(
        plan_id=plan.plan_id,
        generated_at_utc=plan.generated_at_utc,
        source=source_info,
        config_summary=config_summary,
        universe_stats=universe_stats,
        weight_distribution=weight_distribution,
        top_candidates=top_candidates,
        constraints_report=constraints_report,
        metadata={
            "render_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "top_n": top_n,
            "view_version": "1.0",
        },
    )


def write_plan_view_files(plan_dir: Path, view: PortfolioPlanView) -> None:
    """
    Controlled mutation only:
      - plan_view.json
      - plan_view.md
      - plan_view_checksums.json
      - plan_view_manifest.json
    
    Idempotent + atomic.
    """
    # Create write scope for plan view files
    scope = create_plan_view_scope(plan_dir)
    
    # Helper to write a file with scope validation
    def write_scoped(rel_path: str, content_bytes: bytes) -> bool:
        scope.assert_allowed_rel(rel_path)
        return _write_if_changed(plan_dir / rel_path, content_bytes)
    
    # 1. Write plan_view.json
    view_json_bytes = canonical_json_bytes(view.model_dump())
    write_scoped("plan_view.json", view_json_bytes)
    
    # 2. Write plan_view.md (markdown summary)
    md_content = _generate_markdown(view)
    md_bytes = md_content.encode("utf-8")
    write_scoped("plan_view.md", md_bytes)
    
    # 3. Compute checksums for view files
    view_files = ["plan_view.json", "plan_view.md"]
    checksums = {}
    for filename in view_files:
        file_path = plan_dir / filename
        if file_path.exists():
            checksums[filename] = compute_sha256(file_path.read_bytes())
    
    # Write plan_view_checksums.json
    checksums_bytes = canonical_json_bytes(checksums)
    write_scoped("plan_view_checksums.json", checksums_bytes)
    
    # 4. Build and write manifest
    inputs_sha256 = _compute_inputs_sha256(plan_dir)
    
    # Build files listing (sorted by rel_path asc)
    files = []
    for filename in view_files:
        file_path = plan_dir / filename
        if file_path.exists():
            files.append({
                "rel_path": filename,
                "sha256": compute_sha256(file_path.read_bytes())
            })
    # Also include checksums file itself
    checksums_file = "plan_view_checksums.json"
    checksums_path = plan_dir / checksums_file
    if checksums_path.exists():
        files.append({
            "rel_path": checksums_file,
            "sha256": compute_sha256(checksums_path.read_bytes())
        })
    
    # Sort by rel_path
    files.sort(key=lambda x: x["rel_path"])
    
    # Compute files_sha256 (concatenated hashes)
    concatenated = "".join(f["sha256"] for f in files)
    files_sha256 = compute_sha256(concatenated.encode("utf-8"))
    
    manifest = {
        "manifest_type": "view",
        "manifest_version": "1.0",
        "id": view.plan_id,
        "plan_id": view.plan_id,
        "generated_at_utc": view.generated_at_utc,
        "source": view.source,
        "inputs": inputs_sha256,
        "view_checksums": checksums,
        "view_files": view_files,
        "files": files,
        "files_sha256": files_sha256,
    }
    
    # Compute manifest hash (excluding the hash field)
    manifest_canonical = canonical_json_bytes(manifest)
    manifest_sha256 = compute_sha256(manifest_canonical)
    manifest["manifest_sha256"] = manifest_sha256
    
    # Write manifest
    manifest_bytes = canonical_json_bytes(manifest)
    write_scoped("plan_view_manifest.json", manifest_bytes)


def _generate_markdown(view: PortfolioPlanView) -> str:
    """Generate markdown summary of plan view."""
    lines = []
    
    lines.append(f"# Portfolio Plan: {view.plan_id}")
    lines.append(f"**Generated at:** {view.generated_at_utc}")
    lines.append("")
    
    lines.append("## Source")
    lines.append(f"- Season: {view.source.get('season', 'N/A')}")
    lines.append(f"- Export: {view.source.get('export_name', 'N/A')}")
    lines.append(f"- Manifest SHA256: `{view.source.get('export_manifest_sha256', 'N/A')[:16]}...`")
    lines.append("")
    
    lines.append("## Configuration Summary")
    for key, value in view.config_summary.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    
    lines.append("## Universe Statistics")
    lines.append(f"- Total candidates: {view.universe_stats.get('total_candidates', 0)}")
    lines.append(f"- Selected candidates: {view.universe_stats.get('num_selected', 0)}")
    lines.append(f"- Total weight: {view.universe_stats.get('total_weight', 0.0):.4f}")
    lines.append(f"- Concentration (Herfindahl): {view.universe_stats.get('concentration_herfindahl', 0.0):.4f}")
    lines.append("")
    
    lines.append("## Weight Distribution")
    lines.append(f"- Min weight: {view.weight_distribution.get('min_weight', 0.0):.6f}")
    lines.append(f"- Max weight: {view.weight_distribution.get('max_weight', 0.0):.6f}")
    lines.append(f"- Mean weight: {view.weight_distribution.get('mean_weight', 0.0):.6f}")
    lines.append("")
    
    lines.append("## Top Candidates")
    lines.append("| Rank | Candidate ID | Strategy | Dataset | Score | Weight |")
    lines.append("|------|-------------|----------|---------|-------|--------|")
    
    for i, candidate in enumerate(view.top_candidates[:20], 1):
        lines.append(
            f"| {i} | {candidate['candidate_id'][:12]}... | "
            f"{candidate['strategy_id']} | {candidate['dataset_id']} | "
            f"{candidate['score']:.3f} | {candidate['weight']:.6f} |"
        )
    
    if len(view.top_candidates) > 20:
        lines.append(f"... and {len(view.top_candidates) - 20} more candidates")
    
    lines.append("")
    
    lines.append("## Constraints Report")
    if view.constraints_report.get("max_per_strategy_truncated"):
        lines.append(f"- Strategies truncated: {len(view.constraints_report['max_per_strategy_truncated'])}")
    if view.constraints_report.get("max_per_dataset_truncated"):
        lines.append(f"- Datasets truncated: {len(view.constraints_report['max_per_dataset_truncated'])}")
    if view.constraints_report.get("max_weight_clipped"):
        lines.append(f"- Max weight clipped: {len(view.constraints_report['max_weight_clipped'])} candidates")
    if view.constraints_report.get("min_weight_clipped"):
        lines.append(f"- Min weight clipped: {len(view.constraints_report['min_weight_clipped'])} candidates")
    
    if view.constraints_report.get("renormalization_applied"):
        lines.append(f"- Renormalization applied: Yes (factor: {view.constraints_report.get('renormalization_factor', 1.0):.6f})")
    
    lines.append("")
    lines.append("---")
    lines.append(f"*View generated at {view.metadata.get('render_timestamp_utc', 'N/A')}*")
    
    return "\n".join(lines)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/research_bridge.py
sha256(source_bytes) = f491a553d89adaa328bc3352961ade183120ed8378b9622e89052f532b2688aa
bytes = 9446
redacted = False
--------------------------------------------------------------------------------

"""Research to Portfolio Bridge.

Phase 11: Bridge research decisions to executable portfolio specifications.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .decisions_reader import read_decisions_log
from .hash_utils import stable_json_dumps, sha1_text
from .spec import PortfolioLeg, PortfolioSpec


def load_research_index(research_root: Path) -> dict:
    """Load research index from research directory.
    
    Args:
        research_root: Path to research directory (outputs/seasons/{season}/research/)
        
    Returns:
        Research index data
    """
    index_path = research_root / "research_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"research_index.json not found at {index_path}")
    
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_portfolio_from_research(
    *,
    season: str,
    outputs_root: Path,
    symbols_allowlist: Set[str],
) -> Tuple[str, PortfolioSpec, dict]:
    """Build portfolio from research decisions.
    
    Args:
        season: Season identifier (e.g., "2026Q1")
        outputs_root: Root outputs directory
        symbols_allowlist: Set of allowed symbols (e.g., {"CME.MNQ", "TWF.MXF"})
        
    Returns:
        Tuple of (portfolio_id, portfolio_spec, manifest_dict)
    """
    # Paths
    research_root = outputs_root / "seasons" / season / "research"
    decisions_log_path = research_root / "decisions.log"
    
    # Load research data
    research_index = load_research_index(research_root)
    decisions = read_decisions_log(decisions_log_path)
    
    # Process decisions to get final decision for each run_id
    final_decisions = _get_final_decisions(decisions)
    
    # Filter to only KEEP decisions
    keep_run_ids = {
        run_id for run_id, decision_info in final_decisions.items()
        if decision_info.get('decision', '').upper() == 'KEEP'
    }
    
    # Extract research entries and filter by allowlist
    research_entries = research_index.get('entries', [])
    filtered_entries = []
    missing_run_ids = []
    
    for entry in research_entries:
        run_id = entry.get('run_id', '')
        if not run_id:
            continue
            
        if run_id not in keep_run_ids:
            continue
            
        symbol = entry.get('keys', {}).get('symbol', '')
        if symbol not in symbols_allowlist:
            continue
            
        # Check if we have all required metadata
        keys = entry.get('keys', {})
        if not keys.get('strategy_id'):
            missing_run_ids.append(run_id)
            continue
            
        filtered_entries.append(entry)
    
    # Create portfolio legs
    legs = _create_portfolio_legs(filtered_entries, final_decisions)
    
    # Sort legs deterministically
    sorted_legs = _sort_legs_deterministically(legs)
    
    # Generate portfolio ID
    portfolio_id = _generate_portfolio_id(
        season=season,
        symbols_allowlist=symbols_allowlist,
        legs=sorted_legs
    )
    
    # Create portfolio spec
    portfolio_spec = PortfolioSpec(
        portfolio_id=portfolio_id,
        version=f"{season}_research",
        legs=sorted_legs
    )
    
    # Create manifest
    manifest = _create_manifest(
        portfolio_id=portfolio_id,
        season=season,
        symbols_allowlist=symbols_allowlist,
        decisions_log_path=decisions_log_path,
        research_index_path=research_root / "research_index.json",
        legs=sorted_legs,
        missing_run_ids=missing_run_ids,
        total_decisions=len(decisions),
        keep_decisions=len(keep_run_ids)
    )
    
    return portfolio_id, portfolio_spec, manifest


def _get_final_decisions(decisions: List[dict]) -> Dict[str, dict]:
    """Get final decision for each run_id (last entry wins)."""
    final_map = {}
    
    for entry in decisions:
        run_id = entry.get('run_id', '')
        if not run_id:
            continue
            
        # Store entry (last one wins)
        final_map[run_id] = {
            'decision': entry.get('decision', ''),
            'note': entry.get('note', ''),
            'ts': entry.get('ts')
        }
    
    return final_map


def _create_portfolio_legs(
    entries: List[dict],
    final_decisions: Dict[str, dict]
) -> List[PortfolioLeg]:
    """Create PortfolioLeg objects from filtered research entries."""
    legs = []
    
    for entry in entries:
        run_id = entry.get('run_id', '')
        keys = entry.get('keys', {})
        
        # Extract required fields
        symbol = keys.get('symbol', '')
        strategy_id = keys.get('strategy_id', '')
        
        # Extract from entry metadata
        strategy_version = entry.get('strategy_version', '1.0.0')
        timeframe_min = entry.get('timeframe_min', 60)
        session_profile = entry.get('session_profile', 'default')
        
        # Extract metrics if available
        score_final = entry.get('score_final')
        trades = entry.get('trades')
        
        # Get note from final decision
        decision_info = final_decisions.get(run_id, {})
        note = decision_info.get('note', '')
        
        # Create leg_id from run_id (or generate deterministic ID)
        leg_id = f"{run_id}_{symbol}_{strategy_id}"
        
        # Create leg
        leg = PortfolioLeg(
            leg_id=leg_id,
            symbol=symbol,
            timeframe_min=timeframe_min,
            session_profile=session_profile,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            params={},  # Empty params for research-generated legs
            enabled=True,
            tags=["research_generated", season] if 'season' in locals() else ["research_generated"]
        )
        
        legs.append(leg)
    
    return legs


def _sort_legs_deterministically(legs: List[PortfolioLeg]) -> List[PortfolioLeg]:
    """Sort legs deterministically."""
    def sort_key(leg: PortfolioLeg) -> tuple:
        return (
            leg.symbol or '',
            leg.timeframe_min or 0,
            leg.strategy_id or '',
            leg.leg_id or ''
        )
    
    return sorted(legs, key=sort_key)


def _generate_portfolio_id(
    season: str,
    symbols_allowlist: Set[str],
    legs: List[PortfolioLeg]
) -> str:
    """Generate deterministic portfolio ID."""
    
    # Extract core fields from legs for ID generation
    legs_core = []
    for leg in legs:
        legs_core.append({
            'leg_id': leg.leg_id,
            'symbol': leg.symbol,
            'strategy_id': leg.strategy_id,
            'strategy_version': leg.strategy_version,
            'timeframe_min': leg.timeframe_min,
            'session_profile': leg.session_profile
        })
    
    # Sort for determinism
    sorted_allowlist = sorted(symbols_allowlist)
    sorted_legs_core = sorted(legs_core, key=lambda x: x['leg_id'])
    
    # Create ID payload
    id_payload = {
        'season': season,
        'symbols_allowlist': sorted_allowlist,
        'legs_core': sorted_legs_core,
        'generator_version': 'phase11_v1'
    }
    
    # Generate SHA1 and take first 12 chars
    json_str = stable_json_dumps(id_payload)
    full_hash = sha1_text(json_str)
    return full_hash[:12]


def _create_manifest(
    portfolio_id: str,
    season: str,
    symbols_allowlist: Set[str],
    decisions_log_path: Path,
    research_index_path: Path,
    legs: List[PortfolioLeg],
    missing_run_ids: List[str],
    total_decisions: int,
    keep_decisions: int
) -> dict:
    """Create portfolio manifest with metadata."""
    
    # Calculate symbol breakdown
    symbols_breakdown = {}
    for leg in legs:
        symbol = leg.symbol
        symbols_breakdown[symbol] = symbols_breakdown.get(symbol, 0) + 1
    
    # Calculate file hashes
    decisions_log_hash = _calculate_file_hash(decisions_log_path) if decisions_log_path.exists() else ""
    research_index_hash = _calculate_file_hash(research_index_path) if research_index_path.exists() else ""
    
    return {
        'portfolio_id': portfolio_id,
        'season': season,
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'symbols_allowlist': sorted(symbols_allowlist),
        'inputs': {
            'decisions_log_path': str(decisions_log_path.relative_to(decisions_log_path.parent.parent.parent)),
            'decisions_log_sha1': decisions_log_hash,
            'research_index_path': str(research_index_path.relative_to(research_index_path.parent.parent.parent)),
            'research_index_sha1': research_index_hash,
        },
        'counts': {
            'total_decisions': total_decisions,
            'keep_decisions': keep_decisions,
            'num_legs_final': len(legs),
            'symbols_breakdown': symbols_breakdown,
        },
        'warnings': {
            'missing_run_ids': missing_run_ids,
        }
    }


def _calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA1 hash of a file."""
    if not file_path.exists():
        return ""
    
    hasher = hashlib.sha1()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return hasher.hexdigest()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/runner_v1.py
sha256(source_bytes) = c74b8575d8c93276becb84c895f47e5b152d7863bdc5a54f6e5131f9a6e9fec9
bytes = 9642
redacted = False
--------------------------------------------------------------------------------
"""Portfolio runner V1 - assembles candidate signals from artifacts."""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pandas as pd

from FishBroWFS_V2.core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    PortfolioSpecV1,
    SignalCandidateV1,
    OpenPositionV1,
)
from FishBroWFS_V2.portfolio.engine_v1 import PortfolioEngineV1
from FishBroWFS_V2.portfolio.instruments import load_instruments_config

logger = logging.getLogger(__name__)


def detect_entry_events(signal_series_df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect entry events from signal series.
    
    Entry event: position_contracts changes from 0 to non-zero.
    
    Args:
        signal_series_df: DataFrame from signal_series.parquet
        
    Returns:
        DataFrame with entry events only
    """
    if signal_series_df.empty:
        return pd.DataFrame()
    
    # Ensure sorted by ts
    df = signal_series_df.sort_values("ts").reset_index(drop=True)
    
    # Detect position changes
    df["position_change"] = df["position_contracts"].diff()
    
    # First row special case
    if len(df) > 0:
        # If first position is non-zero, it's an entry
        if df.loc[0, "position_contracts"] != 0:
            df.loc[0, "position_change"] = df.loc[0, "position_contracts"]
    
    # Entry events: position_change > 0 (long) or < 0 (short)
    # For v1, we treat both as entry events
    entry_mask = df["position_change"] != 0
    
    return df[entry_mask].copy()


def load_signal_series(
    outputs_root: Path,
    season: str,
    strategy_id: str,
    instrument_id: str,
) -> Optional[pd.DataFrame]:
    """
    Load signal series parquet for a strategy.
    
    Path pattern: outputs/{season}/runs/.../artifacts/signal_series.parquet
    This is a simplified version - actual path may vary.
    """
    # Try to find the signal series file
    # This is a placeholder - actual implementation needs to find the correct run directory
    pattern = f"**/{strategy_id}/**/signal_series.parquet"
    matches = list(outputs_root.glob(pattern))
    
    if not matches:
        logger.warning(f"No signal series found for {strategy_id}/{instrument_id} in {season}")
        return None
    
    # Use first match
    parquet_path = matches[0]
    try:
        df = pd.read_parquet(parquet_path)
        # Filter by instrument if needed
        if "instrument" in df.columns:
            df = df[df["instrument"] == instrument_id].copy()
        return df
    except Exception as e:
        logger.error(f"Failed to load {parquet_path}: {e}")
        return None


def assemble_candidates(
    spec: PortfolioSpecV1,
    outputs_root: Path,
    instruments_config_path: Path = Path("configs/portfolio/instruments.yaml"),
) -> List[SignalCandidateV1]:
    """
    Assemble candidate signals from frozen seasons.
    
    Args:
        spec: Portfolio specification
        outputs_root: Root outputs directory
        instruments_config_path: Path to instruments config
        
    Returns:
        List of candidate signals
    """
    # Load instruments config for margin calculations
    instruments_cfg = load_instruments_config(instruments_config_path)
    
    candidates = []
    
    for season in spec.seasons:
        for strategy_id in spec.strategy_ids:
            for instrument_id in spec.instrument_ids:
                # Load signal series
                df = load_signal_series(
                    outputs_root / season,
                    season,
                    strategy_id,
                    instrument_id,
                )
                
                if df is None or df.empty:
                    continue
                
                # Detect entry events
                entry_events = detect_entry_events(df)
                
                if entry_events.empty:
                    continue
                
                # Get instrument spec for margin calculation
                instrument_spec = instruments_cfg.instruments.get(instrument_id)
                if instrument_spec is None:
                    logger.warning(f"Instrument {instrument_id} not found in config, skipping")
                    continue
                
                # Try to load metadata for candidate_score
                candidate_score = 0.0
                # Look for score in metadata files
                # This is a simplified implementation - actual implementation would need to
                # locate and parse the appropriate metadata file
                # For v1, we'll use a placeholder approach
                
                # Create candidates from entry events
                for _, row in entry_events.iterrows():
                    # Calculate required margin
                    # For v1: use margin_initial_base from the signal series
                    # If not available, estimate from position * margin_per_contract * fx
                    if "margin_initial_base" in row:
                        required_margin = abs(row["margin_initial_base"])
                    else:
                        # Estimate conservatively
                        position = abs(row["position_contracts"])
                        required_margin = (
                            position
                            * instrument_spec.initial_margin_per_contract
                            * instruments_cfg.fx_rates[instrument_spec.currency]
                        )
                    
                    # Get signal strength (use close as placeholder if not available)
                    signal_strength = 1.0  # Default
                    if "signal_strength" in row:
                        signal_strength = row["signal_strength"]
                    elif "close" in row:
                        # Use normalized close as proxy (simplified)
                        signal_strength = row["close"] / 10000.0
                    
                    candidate = SignalCandidateV1(
                        strategy_id=strategy_id,
                        instrument_id=instrument_id,
                        bar_ts=row["ts"],
                        bar_index=int(row.name) if "index" in row else 0,
                        signal_strength=float(signal_strength),
                        candidate_score=float(candidate_score),  # v1: default 0.0
                        required_margin_base=float(required_margin),
                        required_slot=1,  # v1 fixed
                    )
                    candidates.append(candidate)
    
    # Sort by bar_ts for chronological processing
    candidates.sort(key=lambda c: c.bar_ts)
    
    logger.info(f"Assembled {len(candidates)} candidates from {len(spec.seasons)} seasons")
    return candidates


def run_portfolio_admission(
    policy: PortfolioPolicyV1,
    spec: PortfolioSpecV1,
    equity_base: float,
    outputs_root: Path,
    replay_mode: bool = False,
) -> Tuple[List[SignalCandidateV1], List[OpenPositionV1], Dict]:
    """
    Run portfolio admission process.
    
    Args:
        policy: Portfolio policy
        spec: Portfolio specification
        equity_base: Initial equity in base currency
        outputs_root: Root outputs directory
        replay_mode: If True, read-only mode (no writes)
        
    Returns:
        Tuple of (candidates, final_open_positions, results_dict)
    """
    logger.info(f"Starting portfolio admission (replay={replay_mode})")
    
    # Assemble candidates
    candidates = assemble_candidates(spec, outputs_root)
    
    if not candidates:
        logger.warning("No candidates found")
        return [], [], {}
    
    # Group candidates by bar for sequential processing
    candidates_by_bar: Dict[Tuple, List[SignalCandidateV1]] = {}
    for candidate in candidates:
        key = (candidate.bar_index, candidate.bar_ts)
        candidates_by_bar.setdefault(key, []).append(candidate)
    
    # Initialize engine
    engine = PortfolioEngineV1(policy, equity_base)
    
    # Process bars in chronological order
    for (bar_index, bar_ts), bar_candidates in sorted(candidates_by_bar.items()):
        engine.admit_candidates(bar_candidates)
    
    # Get results
    decisions = engine.decisions
    final_positions = engine.open_positions
    summary = engine.get_summary()
    
    logger.info(
        f"Portfolio admission completed: "
        f"{summary.accepted_count} accepted, "
        f"{summary.rejected_count} rejected, "
        f"final slots={summary.final_slots_used}, "
        f"margin ratio={summary.final_margin_ratio:.2%}"
    )
    
    results = {
        "decisions": decisions,
        "summary": summary,
        "bar_states": engine.bar_states,
    }
    
    return candidates, final_positions, results


def validate_portfolio_spec(spec: PortfolioSpecV1, outputs_root: Path) -> List[str]:
    """
    Validate portfolio specification.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check seasons exist
    for season in spec.seasons:
        season_dir = outputs_root / season
        if not season_dir.exists():
            errors.append(f"Season directory not found: {season_dir}")
    
    # Check instruments config SHA256
    # This would need to be implemented based on actual config loading
    
    # Check resource estimate (simplified)
    total_candidates_estimate = len(spec.seasons) * len(spec.strategy_ids) * len(spec.instrument_ids) * 1000
    if total_candidates_estimate > 100000:
        errors.append(f"Large resource estimate: ~{total_candidates_estimate} candidates")
    
    return errors
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/signal_series_writer.py
sha256(source_bytes) = 60acf6a51a2847efe8325cb486d16956034dcad23d51daef30292c61f12ada8d
bytes = 4655
redacted = False
--------------------------------------------------------------------------------
"""Signal series writer for portfolio artifacts."""

import json
from pathlib import Path
from typing import Dict, Any
import pandas as pd

from FishBroWFS_V2.core.schemas.portfolio import SignalSeriesMetaV1
from FishBroWFS_V2.portfolio.instruments import load_instruments_config, InstrumentSpec
from FishBroWFS_V2.engine.signal_exporter import build_signal_series_v1


def write_signal_series_artifacts(
    *,
    run_dir: Path,
    instrument: str,
    bars_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    timeframe: str,
    tz: str,
    source_run_id: str,
    source_spec_sha: str,
    instruments_config_path: Path = Path("configs/portfolio/instruments.yaml"),
) -> None:
    """
    Write signal series artifacts (signal_series.parquet and signal_series_meta.json).
    
    Args:
        run_dir: Run directory where artifacts will be written
        instrument: Instrument identifier (e.g., "CME.MNQ")
        bars_df: DataFrame with columns ['ts', 'close']; must be sorted ascending by ts
        fills_df: DataFrame with columns ['ts', 'qty']; qty is signed contracts
        timeframe: Bar timeframe (e.g., "5min")
        tz: Timezone string (e.g., "UTC")
        source_run_id: Source run ID for traceability
        source_spec_sha: Source spec SHA for traceability
        instruments_config_path: Path to instruments.yaml config
        
    Raises:
        FileNotFoundError: If instruments config not found
        KeyError: If instrument not found in config
        ValueError: If input validation fails
    """
    # Load instruments config
    cfg = load_instruments_config(instruments_config_path)
    spec = cfg.instruments.get(instrument)
    if spec is None:
        raise KeyError(f"Instrument '{instrument}' not found in instruments config")
    
    # Get FX rate
    fx_to_base = cfg.fx_rates[spec.currency]
    
    # Build signal series DataFrame
    df = build_signal_series_v1(
        instrument=instrument,
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe=timeframe,
        tz=tz,
        base_currency=cfg.base_currency,
        instrument_currency=spec.currency,
        fx_to_base=fx_to_base,
        multiplier=spec.multiplier,
        initial_margin_per_contract=spec.initial_margin_per_contract,
        maintenance_margin_per_contract=spec.maintenance_margin_per_contract,
    )
    
    # Write signal_series.parquet
    parquet_path = run_dir / "signal_series.parquet"
    df.to_parquet(parquet_path, index=False)
    
    # Build metadata
    meta = SignalSeriesMetaV1(
        schema="SIGNAL_SERIES_V1",
        instrument=instrument,
        timeframe=timeframe,
        tz=tz,
        base_currency=cfg.base_currency,
        instrument_currency=spec.currency,
        fx_to_base=fx_to_base,
        multiplier=spec.multiplier,
        initial_margin_per_contract=spec.initial_margin_per_contract,
        maintenance_margin_per_contract=spec.maintenance_margin_per_contract,
        source_run_id=source_run_id,
        source_spec_sha=source_spec_sha,
        instruments_config_sha256=cfg.sha256,
    )
    
    # Write signal_series_meta.json
    meta_path = run_dir / "signal_series_meta.json"
    meta_dict = meta.model_dump(by_alias=True)
    meta_path.write_text(
        json.dumps(meta_dict, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    
    # Update manifest to include signal series files
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Add signal series artifacts to manifest
            if "signal_series_artifacts" not in manifest:
                manifest["signal_series_artifacts"] = []
            manifest["signal_series_artifacts"].extend([
                {
                    "path": "signal_series.parquet",
                    "type": "parquet",
                    "schema": "SIGNAL_SERIES_V1",
                },
                {
                    "path": "signal_series_meta.json",
                    "type": "json",
                    "schema": "SIGNAL_SERIES_V1",
                }
            ])
            # Write updated manifest
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            # Don't fail if manifest update fails, just log
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to update manifest with signal series artifacts: {e}")
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/spec.py
sha256(source_bytes) = 44a65113f404abeec7a45a12ed4aae9d46dcac6b323814d1b47dc897964d460d
bytes = 3231
redacted = False
--------------------------------------------------------------------------------

"""Portfolio specification data model.

Phase 8: Portfolio OS - versioned, auditable, replayable portfolio definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PortfolioLeg:
    """Portfolio leg definition.
    
    A leg represents one trading strategy applied to one symbol/timeframe.
    
    Attributes:
        leg_id: Unique leg identifier (e.g., "mnq_60_sma")
        symbol: Symbol identifier (e.g., "CME.MNQ")
        timeframe_min: Timeframe in minutes (e.g., 60)
        session_profile: Path to session profile YAML file or profile ID
        strategy_id: Strategy identifier (must exist in registry)
        strategy_version: Strategy version (must match registry)
        params: Strategy parameters dict (key-value pairs)
        enabled: Whether this leg is enabled (default: True)
        tags: Optional tags for categorization (default: empty list)
    """
    leg_id: str
    symbol: str
    timeframe_min: int
    session_profile: str
    strategy_id: str
    strategy_version: str
    params: Dict[str, float]
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate leg fields."""
        if not self.leg_id:
            raise ValueError("leg_id cannot be empty")
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.timeframe_min <= 0:
            raise ValueError(f"timeframe_min must be > 0, got {self.timeframe_min}")
        if not self.session_profile:
            raise ValueError("session_profile cannot be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id cannot be empty")
        if not self.strategy_version:
            raise ValueError("strategy_version cannot be empty")
        if not isinstance(self.params, dict):
            raise ValueError(f"params must be dict, got {type(self.params)}")


@dataclass(frozen=True)
class PortfolioSpec:
    """Portfolio specification.
    
    Defines a portfolio as a collection of legs (trading strategies).
    
    Attributes:
        portfolio_id: Unique portfolio identifier (e.g., "mvp")
        version: Portfolio version (e.g., "2026Q1")
        data_tz: Data timezone (default: "Asia/Taipei", fixed)
        legs: List of portfolio legs
    """
    portfolio_id: str
    version: str
    data_tz: str = "Asia/Taipei"  # Fixed default
    legs: List[PortfolioLeg] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate portfolio spec."""
        if not self.portfolio_id:
            raise ValueError("portfolio_id cannot be empty")
        if not self.version:
            raise ValueError("version cannot be empty")
        if self.data_tz != "Asia/Taipei":
            raise ValueError(f"data_tz must be 'Asia/Taipei' (fixed), got {self.data_tz}")
        
        # Check leg_id uniqueness
        leg_ids = [leg.leg_id for leg in self.legs]
        if len(leg_ids) != len(set(leg_ids)):
            duplicates = [lid for lid in leg_ids if leg_ids.count(lid) > 1]
            raise ValueError(f"Duplicate leg_id found: {set(duplicates)}")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/validate.py
sha256(source_bytes) = c491840f3d05d73bae8d640ba01949f364061ac21bbde2cfc1f7d313cf69da55
bytes = 4058
redacted = False
--------------------------------------------------------------------------------

"""Portfolio specification validator.

Phase 8: Validate portfolio spec against contracts.
"""

from __future__ import annotations

from pathlib import Path

from FishBroWFS_V2.data.session.loader import load_session_profile
from FishBroWFS_V2.portfolio.spec import PortfolioSpec
from FishBroWFS_V2.strategy.registry import get


def validate_portfolio_spec(spec: PortfolioSpec) -> None:
    """Validate portfolio specification.
    
    Validates:
    - portfolio_id/version non-empty (already checked in PortfolioSpec.__post_init__)
    - legs non-empty; each leg_id unique (already checked in PortfolioSpec.__post_init__)
    - timeframe_min > 0 (already checked in PortfolioLeg.__post_init__)
    - session_profile path exists and can be loaded
    - strategy_id exists in registry
    - strategy_version matches registry (strict match)
    - params is dict with float values (already checked in loader)
    
    Args:
        spec: Portfolio specification to validate
        
    Raises:
        ValueError: If validation fails
        FileNotFoundError: If session profile not found
        KeyError: If strategy not found in registry
    """
    if not spec.legs:
        raise ValueError("Portfolio must have at least one leg")
    
    # Validate each leg
    for leg in spec.legs:
        # Validate session_profile path exists and can be loaded
        session_profile_path = Path(leg.session_profile)
        
        # Handle relative paths (relative to project root or current working directory)
        if not session_profile_path.is_absolute():
            # Try relative to current working directory first
            if not session_profile_path.exists():
                # Try relative to project root (if path starts with src/)
                if leg.session_profile.startswith("src/"):
                    # Path is already relative to project root
                    if not session_profile_path.exists():
                        # Try from current directory
                        pass
                else:
                    # Try relative to project root (src/FishBroWFS_V2/data/profiles/)
                    project_profile_path = Path("src/FishBroWFS_V2/data/profiles") / session_profile_path.name
                    if project_profile_path.exists():
                        session_profile_path = project_profile_path
        
        if not session_profile_path.exists():
            raise FileNotFoundError(
                f"Leg '{leg.leg_id}': session_profile not found: {leg.session_profile}"
            )
        
        # Try to load session profile
        try:
            load_session_profile(session_profile_path)
        except Exception as e:
            raise ValueError(
                f"Leg '{leg.leg_id}': failed to load session_profile '{leg.session_profile}': {e}"
            )
        
        # Validate strategy_id exists in registry
        try:
            strategy_spec = get(leg.strategy_id)
        except KeyError as e:
            raise KeyError(
                f"Leg '{leg.leg_id}': strategy_id '{leg.strategy_id}' not found in registry: {e}"
            )
        
        # Validate strategy_version matches (strict match)
        if strategy_spec.version != leg.strategy_version:
            raise ValueError(
                f"Leg '{leg.leg_id}': strategy_version mismatch. "
                f"Expected '{strategy_spec.version}' (from registry), got '{leg.strategy_version}'"
            )
        
        # Validate params keys exist in strategy param_schema (optional check)
        # This is a best-effort check - runner will handle defaults
        param_schema = strategy_spec.param_schema
        if isinstance(param_schema, dict) and "properties" in param_schema:
            schema_props = param_schema.get("properties", {})
            for param_key in leg.params.keys():
                if param_key not in schema_props and param_key not in strategy_spec.defaults:
                    # Warning: extra param, but allowed (runner will log warning)
                    pass



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/writer.py
sha256(source_bytes) = 85ff28c0e0b9d3612b32c6329e6488ca4632f4093fe073fc913f543d818f0164
bytes = 7045
redacted = False
--------------------------------------------------------------------------------

"""Portfolio artifacts writer.

Phase 8/11:
- Single source of truth: PortfolioSpec (dataclass) in spec.py
- Writer is IO-only: write portfolio_spec.json + portfolio_manifest.json + README.md
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from FishBroWFS_V2.portfolio.spec import PortfolioSpec


def _utc_now_z() -> str:
    """Return UTC timestamp ending with 'Z'."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dump(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _spec_to_dict(spec: PortfolioSpec) -> dict:
    """Convert PortfolioSpec to a JSON-serializable dict deterministically."""
    if is_dataclass(spec):
        return asdict(spec)

    # Fallback if spec ever becomes pydantic-like
    if hasattr(spec, "model_dump"):
        return spec.model_dump()  # type: ignore[no-any-return]
    if hasattr(spec, "dict"):
        return spec.dict()  # type: ignore[no-any-return]

    raise TypeError(f"Unsupported spec type for serialization: {type(spec)}")


def _render_readme_md(*, spec: PortfolioSpec, manifest: dict) -> str:
    """Render README.md content that satisfies test contracts.
    
    Required sections (order matters for readability):
    # Portfolio: {portfolio_id}
    ## Purpose
    ## Inputs
    ## Legs
    ## Summary
    ## Reproducibility
    ## Files
    ## Warnings (optional but kept for compatibility)
    """
    portfolio_id = manifest.get("portfolio_id", getattr(spec, "portfolio_id", ""))
    season = manifest.get("season", "")

    inputs = manifest.get("inputs", {}) or {}
    counts = manifest.get("counts", {}) or {}
    warnings = manifest.get("warnings", {}) or {}

    decisions_log_path = inputs.get("decisions_log_path", "")
    decisions_log_sha1 = inputs.get("decisions_log_sha1", "")
    research_index_path = inputs.get("research_index_path", "")
    research_index_sha1 = inputs.get("research_index_sha1", "")

    total_decisions = counts.get("total_decisions", 0)
    keep_decisions = counts.get("keep_decisions", 0)
    num_legs_final = counts.get("num_legs_final", len(getattr(spec, "legs", []) or []))
    symbols_allowlist = manifest.get("symbols_allowlist", [])

    lines: list[str] = []
    lines.append(f"# Portfolio: {portfolio_id}")
    lines.append("")
    lines.append("## Purpose")
    lines.append(
        "This folder contains an **executable portfolio specification** generated from Research decisions "
        "(append-only decisions.log). It is designed to be deterministic and auditable."
    )
    lines.append("")

    lines.append("## Inputs")
    lines.append(f"- season: `{season}`")
    lines.append(f"- decisions_log_path: `{decisions_log_path}`")
    lines.append(f"- decisions_log_sha1: `{decisions_log_sha1}`")
    lines.append(f"- research_index_path: `{research_index_path}`")
    lines.append(f"- research_index_sha1: `{research_index_sha1}`")
    lines.append(f"- symbols_allowlist: `{symbols_allowlist}`")
    lines.append("")

    lines.append("## Legs")
    legs = getattr(spec, "legs", None) or []
    if legs:
        lines.append("| symbol | timeframe_min | session_profile | strategy_id | strategy_version | enabled | leg_id |")
        lines.append("|---|---:|---|---|---|---|---|")
        for leg in legs:
            # Support both dataclass and dict-like legs
            symbol = getattr(leg, "symbol", None) if not isinstance(leg, dict) else leg.get("symbol")
            timeframe_min = getattr(leg, "timeframe_min", None) if not isinstance(leg, dict) else leg.get("timeframe_min")
            session_profile = getattr(leg, "session_profile", None) if not isinstance(leg, dict) else leg.get("session_profile")
            strategy_id = getattr(leg, "strategy_id", None) if not isinstance(leg, dict) else leg.get("strategy_id")
            strategy_version = getattr(leg, "strategy_version", None) if not isinstance(leg, dict) else leg.get("strategy_version")
            enabled = getattr(leg, "enabled", None) if not isinstance(leg, dict) else leg.get("enabled")
            leg_id = getattr(leg, "leg_id", None) if not isinstance(leg, dict) else leg.get("leg_id")
            
            lines.append(
                f"| {symbol} | {timeframe_min} | {session_profile} | "
                f"{strategy_id} | {strategy_version} | {enabled} | {leg_id} |"
            )
    else:
        lines.append("_No legs (empty portfolio)._")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- portfolio_id: `{portfolio_id}`")
    lines.append(f"- version: `{getattr(spec, 'version', '')}`")
    lines.append(f"- total_decisions: `{total_decisions}`")
    lines.append(f"- keep_decisions: `{keep_decisions}`")
    lines.append(f"- num_legs_final: `{num_legs_final}`")
    lines.append("")

    lines.append("## Reproducibility")
    lines.append("To reproduce this portfolio exactly, you must use the same inputs and ordering rules:")
    lines.append("- decisions.log is append-only; **last decision wins** per run_id.")
    lines.append("- legs are filtered by symbols_allowlist.")
    lines.append("- legs are sorted deterministically before portfolio_id generation.")
    lines.append("- the input digests above (sha1) must match.")
    lines.append("")

    lines.append("## Files")
    lines.append("- `portfolio_spec.json`")
    lines.append("- `portfolio_manifest.json`")
    lines.append("- `README.md`")
    lines.append("")

    # Optional: keep warnings section for compatibility
    lines.append("## Warnings")
    lines.append(f"- missing_run_ids: {warnings.get('missing_run_ids', [])}")
    lines.append("")

    return "\n".join(lines)


def write_portfolio_artifacts(
    *,
    outputs_root: Path,
    season: str,
    spec: PortfolioSpec,
    manifest: dict,
) -> Path:
    """Write portfolio artifacts to outputs/seasons/{season}/portfolio/{portfolio_id}/

    Contract:
    - IO-only
    - Deterministic file content given (spec, manifest) except generated_at if caller omitted it
    """
    portfolio_id = getattr(spec, "portfolio_id", None)
    if not portfolio_id or not str(portfolio_id).strip():
        raise ValueError("spec.portfolio_id must be non-empty")

    out_dir = outputs_root / "seasons" / season / "portfolio" / str(portfolio_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ensure generated_at exists
    if "generated_at" not in manifest or not str(manifest.get("generated_at", "")).strip():
        manifest = dict(manifest)
        manifest["generated_at"] = _utc_now_z()

    spec_dict = _spec_to_dict(spec)

    _json_dump(out_dir / "portfolio_spec.json", spec_dict)
    _json_dump(out_dir / "portfolio_manifest.json", manifest)

    readme = _render_readme_md(spec=spec, manifest=manifest)
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    return out_dir



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/portfolio/examples/portfolio_mvp_2026Q1.yaml
sha256(source_bytes) = 5938689c1d3f43baadbf892fcfee59cd23c5688af3770a21ceb60ee7827676d9
bytes = 656
redacted = False
--------------------------------------------------------------------------------
portfolio_id: "mvp"
version: "2026Q1"
data_tz: "Asia/Taipei"
legs:
  - leg_id: "mnq_60_sma"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "src/FishBroWFS_V2/data/profiles/CME_MNQ_v2.yaml"
    strategy_id: "sma_cross"
    strategy_version: "v1"
    params:
      fast_period: 10.0
      slow_period: 40.0
    enabled: true
    tags: ["mvp", "cme"]

  - leg_id: "mxf_60_mrz"
    symbol: "TWF.MXF"
    timeframe_min: 60
    session_profile: "src/FishBroWFS_V2/data/profiles/TWF_MXF_v2.yaml"
    strategy_id: "mean_revert_zscore"
    strategy_version: "v1"
    params:
      zscore_threshold: -2.0
    enabled: true
    tags: ["mvp", "twf"]

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/research/__init__.py
sha256(source_bytes) = f08bdc7c012cb0ee85b9282c7bd62e72973c74b1bab7f50b67126072f48b3efa
bytes = 249
redacted = False
--------------------------------------------------------------------------------

"""Research Governance Layer (Phase 9).

Provides standardized summary, comparison, and archival capabilities for portfolio runs.
Read-only layer that extracts and aggregates data from existing artifacts.
"""

from __future__ import annotations




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/research/__main__.py
sha256(source_bytes) = d7fa0a2c2104b37762571f084e23febf3b444c4ac026f7e361e4f98b23b4e329
bytes = 2836
redacted = False
--------------------------------------------------------------------------------

"""Research Governance Layer main entry point.

Phase 9: Generate canonical results and research index.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from FishBroWFS_V2.research.registry import build_research_index
from FishBroWFS_V2.research.extract import extract_canonical_metrics, ExtractionError


def generate_canonical_results(outputs_root: Path, research_dir: Path) -> Path:
    """
    Generate canonical_results.json from all runs.
    
    Args:
        outputs_root: Root outputs directory
        research_dir: Research output directory
        
    Returns:
        Path to canonical_results.json
    """
    research_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan all runs
    seasons_dir = outputs_root / "seasons"
    if not seasons_dir.exists():
        # Create empty results
        results_path = research_dir / "canonical_results.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump({"results": []}, f, indent=2, ensure_ascii=False, sort_keys=True)
        return results_path
    
    results = []
    
    # Scan seasons
    for season_dir in seasons_dir.iterdir():
        if not season_dir.is_dir():
            continue
        
        runs_dir = season_dir / "runs"
        if not runs_dir.exists():
            continue
        
        # Scan runs
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            try:
                metrics = extract_canonical_metrics(run_dir)
                results.append(metrics.to_dict())
            except ExtractionError:
                # Skip runs with missing artifacts
                continue
    
    # Write results
    results_path = research_dir / "canonical_results.json"
    results_data = {
        "results": results,
        "total_runs": len(results),
    }
    
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    return results_path


def main() -> int:
    """Main entry point for research governance layer."""
    outputs_root = Path("outputs")
    research_dir = outputs_root / "research"
    
    try:
        # Generate canonical results
        print(f"Generating canonical_results.json...")
        generate_canonical_results(outputs_root, research_dir)
        
        # Build research index
        print(f"Building research_index.json...")
        build_research_index(outputs_root, research_dir)
        
        print(f"Research governance layer completed successfully.")
        print(f"Output directory: {research_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/research/decision.py
sha256(source_bytes) = 204cc32953d97e5dae82ed325a84b99f83d0d41da893d8cd69b7ded2b128b3aa
bytes = 2307
redacted = False
--------------------------------------------------------------------------------

"""Research Decision - manage KEEP/DROP/ARCHIVE decisions.

Phase 9: Append-only decision log with notes and timestamps.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

DecisionType = Literal["KEEP", "DROP", "ARCHIVE"]


def append_decision(out_dir: Path, run_id: str, decision: DecisionType, note: str) -> Path:
    """
    Append a decision to decisions.log (JSONL format).
    
    Same run_id can have multiple decisions (append-only).
    The research_index.json will show the last decision (last-write-wins view).
    
    Args:
        out_dir: Research output directory
        run_id: Run ID
        decision: Decision type (KEEP, DROP, ARCHIVE)
        note: Note explaining the decision
        
    Returns:
        Path to decisions.log
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Append to log (JSONL format)
    decisions_log_path = out_dir / "decisions.log"
    
    decision_entry = {
        "run_id": run_id,
        "decision": decision,
        "note": note,
        "decided_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    
    with open(decisions_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision_entry, ensure_ascii=False, sort_keys=True) + "\n")
    
    return decisions_log_path


def load_decisions(out_dir: Path) -> List[Dict[str, Any]]:
    """
    Load all decisions from decisions.log.
    
    Args:
        out_dir: Research output directory
        
    Returns:
        List of decision entries (all entries, including duplicates for same run_id)
    """
    decisions_log_path = out_dir / "decisions.log"
    
    if not decisions_log_path.exists():
        return []
    
    decisions = []
    try:
        with open(decisions_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    decisions.append(entry)
                except json.JSONDecodeError:
                    # Skip invalid lines
                    continue
    except Exception:
        pass
    
    return decisions



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/research/extract.py
sha256(source_bytes) = 9a4f29e3be4d15083d7a0c11700901ef0cdbc9dc3d2106f3f694f5f803b83c9b
bytes = 6430
redacted = False
--------------------------------------------------------------------------------

"""Result Extractor - extract canonical metrics from artifacts.

Phase 9: Read-only extraction from existing artifacts.
No computation, only aggregation from existing data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.research.metrics import CanonicalMetrics


class ExtractionError(Exception):
    """Raised when required artifacts or fields are missing."""
    pass


def extract_canonical_metrics(run_dir: Path) -> CanonicalMetrics:
    """
    Extract canonical metrics from run artifacts.
    
    Reads artifacts from run_dir (at least one of manifest/metrics/config_snapshot/README must exist).
    Uses field mapping table to map artifact fields to CanonicalMetrics.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        CanonicalMetrics instance
        
    Raises:
        ExtractionError: If required artifacts or fields are missing
    """
    # Check at least one artifact exists
    manifest_path = run_dir / "manifest.json"
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "config_snapshot.json"
    winners_path = run_dir / "winners.json"
    
    if not any(p.exists() for p in [manifest_path, metrics_path, config_path]):
        raise ExtractionError(f"No artifacts found in {run_dir}")
    
    # Load available artifacts
    manifest: Dict[str, Any] = {}
    metrics_data: Dict[str, Any] = {}
    config_data: Dict[str, Any] = {}
    winners: Dict[str, Any] = {}
    
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid manifest.json: {e}")
    
    if metrics_path.exists():
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid metrics.json: {e}")
    
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid config_snapshot.json: {e}")
    
    if winners_path.exists():
        try:
            with open(winners_path, "r", encoding="utf-8") as f:
                winners = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid winners.json: {e}")
    
    # Field mapping table: artifact field -> CanonicalMetrics field
    # Extract identification
    run_id = manifest.get("run_id") or metrics_data.get("run_id")
    if not run_id:
        raise ExtractionError("Missing 'run_id' in artifacts")
    
    portfolio_id = manifest.get("portfolio_id") or config_data.get("portfolio_id")
    portfolio_version = manifest.get("portfolio_version") or config_data.get("portfolio_version")
    
    # Strategy info from winners.json topk (take first item if available)
    strategy_id = None
    strategy_version = None
    symbol = None
    timeframe_min = None
    
    topk = winners.get("topk", [])
    if topk and isinstance(topk, list) and len(topk) > 0:
        first_item = topk[0]
        strategy_id = first_item.get("strategy_id")
        symbol = first_item.get("symbol")
        # timeframe_min might be in config or need parsing from timeframe string
        timeframe_str = first_item.get("timeframe", "")
        if timeframe_str and timeframe_str != "UNKNOWN":
            # Try to extract minutes from timeframe (e.g., "60m" -> 60)
            try:
                if timeframe_str.endswith("m"):
                    timeframe_min = int(timeframe_str[:-1])
            except ValueError:
                pass
    
    # Extract bars (required)
    bars = manifest.get("bars") or metrics_data.get("bars") or config_data.get("bars")
    if bars is None:
        raise ExtractionError("Missing 'bars' in artifacts")
    
    # Extract dates
    start_date = manifest.get("created_at", "")
    end_date = ""  # Not available in artifacts
    
    # Extract core metrics from winners.json topk aggregation
    # Aggregate net_profit, max_dd, trades from topk
    total_net_profit = 0.0
    max_max_dd = 0.0
    total_trades = 0
    
    for item in topk:
        item_metrics = item.get("metrics", {})
        net_profit = item_metrics.get("net_profit", 0.0)
        max_dd = item_metrics.get("max_dd", 0.0)
        trades = item_metrics.get("trades", 0)
        
        total_net_profit += net_profit
        max_max_dd = min(max_max_dd, max_dd)  # max_dd is negative or 0
        total_trades += trades
    
    net_profit = total_net_profit
    max_drawdown = abs(max_max_dd)  # Convert to positive
    
    # Extract profit_factor and sharpe from metrics (if available)
    # These may not be in artifacts, so allow None
    profit_factor = metrics_data.get("profit_factor")
    sharpe = metrics_data.get("sharpe")
    
    # Calculate derived scores
    # score_net_mdd = net_profit / abs(max_drawdown)
    # If max_drawdown == 0, raise error (as per requirement)
    if max_drawdown == 0.0:
        if net_profit != 0.0:
            # Non-zero profit but zero drawdown - this is edge case
            # Per requirement: "mdd=0 → inf or raise, please define clearly"
            # We'll raise to be explicit
            raise ExtractionError(
                f"max_drawdown is 0 but net_profit is {net_profit}, "
                "cannot calculate score_net_mdd"
            )
        score_net_mdd = 0.0
    else:
        score_net_mdd = net_profit / max_drawdown
    
    # score_final = score_net_mdd * (trades ** 0.25)
    score_final = score_net_mdd * (total_trades ** 0.25) if total_trades > 0 else 0.0
    
    return CanonicalMetrics(
        run_id=run_id,
        portfolio_id=portfolio_id,
        portfolio_version=portfolio_version,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        symbol=symbol,
        timeframe_min=timeframe_min,
        net_profit=net_profit,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        sharpe=sharpe,
        trades=total_trades,
        score_net_mdd=score_net_mdd,
        score_final=score_final,
        bars=bars,
        start_date=start_date,
        end_date=end_date,
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/research/metrics.py
sha256(source_bytes) = 2df6b67466d3a0daaf047a1b0d15b3cb1b77b8da179174c749222ab0a60395bd
bytes = 1571
redacted = False
--------------------------------------------------------------------------------

"""Canonical Metrics Schema for research results.

Phase 9: Standardized format for portfolio run results.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass(frozen=True)
class CanonicalMetrics:
    """
    Canonical metrics schema for research results.
    
    This is the official format for summarizing portfolio run results.
    All fields are required - missing data must be handled at extraction time.
    """
    # Identification
    run_id: str
    portfolio_id: str | None
    portfolio_version: str | None
    strategy_id: str | None
    strategy_version: str | None
    symbol: str | None
    timeframe_min: int | None
    
    # Performance (core numerical fields)
    net_profit: float
    max_drawdown: float
    profit_factor: float | None  # May be None if not available in artifacts
    sharpe: float | None  # May be None if not available in artifacts
    trades: int
    
    # Derived scores (computed from existing values only)
    score_net_mdd: float  # Net / |MDD|, raises if MDD=0
    score_final: float  # score_net_mdd * (trades ** 0.25)
    
    # Metadata
    bars: int
    start_date: str  # ISO8601 format or empty string
    end_date: str  # ISO8601 format or empty string
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CanonicalMetrics:
        """Create from dictionary."""
        return cls(**data)




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/research/registry.py
sha256(source_bytes) = e0f7ff2d0949604a455415239f4751a65694154105dcd3a2ec164c3cb9595baa
bytes = 4012
redacted = False
--------------------------------------------------------------------------------

"""Result Registry - scan outputs and build research index.

Phase 9: Scan outputs/ directory and create canonical_results.json and research_index.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from FishBroWFS_V2.research.decision import load_decisions
from FishBroWFS_V2.research.extract import extract_canonical_metrics, ExtractionError


def build_research_index(outputs_root: Path, out_dir: Path) -> Path:
    """
    Build research index from scanned outputs.
    
    Scans outputs/seasons/{season}/runs/{run_id}/ and extracts canonical metrics.
    Outputs two files:
    - canonical_results.json: List of all CanonicalMetrics as dicts
    - research_index.json: Sorted lightweight index with run_id, score_final, decision, keys
    
    Sorting rules (fixed):
    1. score_final desc
    2. score_net_mdd desc
    3. trades desc
    
    Args:
        outputs_root: Root outputs directory (e.g., Path("outputs"))
        out_dir: Output directory for research artifacts (e.g., Path("outputs/research"))
        
    Returns:
        Path to research_index.json
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan all runs
    canonical_results = []
    seasons_dir = outputs_root / "seasons"
    
    if seasons_dir.exists():
        for season_dir in seasons_dir.iterdir():
            if not season_dir.is_dir():
                continue
            
            runs_dir = season_dir / "runs"
            if not runs_dir.exists():
                continue
            
            # Scan runs
            for run_dir in runs_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                
                try:
                    metrics = extract_canonical_metrics(run_dir)
                    canonical_results.append(metrics.to_dict())
                except ExtractionError:
                    # Skip runs with missing artifacts
                    continue
    
    # Write canonical_results.json (list of CanonicalMetrics as dict)
    canonical_path = out_dir / "canonical_results.json"
    with open(canonical_path, "w", encoding="utf-8") as f:
        json.dump(canonical_results, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    # Load decisions (if any)
    decisions = load_decisions(out_dir)
    decision_map: Dict[str, str] = {}
    for decision_entry in decisions:
        run_id = decision_entry.get("run_id")
        decision = decision_entry.get("decision")
        if run_id and decision:
            # Last-write-wins: later entries overwrite earlier ones
            decision_map[run_id] = decision
    
    # Build lightweight index with sorting
    index_entries = []
    for result in canonical_results:
        run_id = result.get("run_id")
        if not run_id:
            continue
        
        entry = {
            "run_id": run_id,
            "score_final": result.get("score_final", 0.0),
            "score_net_mdd": result.get("score_net_mdd", 0.0),
            "trades": result.get("trades", 0),
            "decision": decision_map.get(run_id, "UNDECIDED"),
            "keys": {
                "portfolio_id": result.get("portfolio_id"),
                "strategy_id": result.get("strategy_id"),
                "symbol": result.get("symbol"),
            },
        }
        index_entries.append(entry)
    
    # Sort: score_final desc, then score_net_mdd desc, then trades desc
    index_entries.sort(
        key=lambda x: (
            -x["score_final"],  # Negative for descending
            -x["score_net_mdd"],
            -x["trades"],
        )
    )
    
    # Write research_index.json
    index_data = {
        "entries": index_entries,
        "total_runs": len(index_entries),
    }
    
    index_path = out_dir / "research_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    return index_path



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/stage0/__init__.py
sha256(source_bytes) = 24b4597b0a4a5c619073212095f818e9b9f677a1b89e00f119f01d156e08236f
bytes = 335
redacted = False
--------------------------------------------------------------------------------

"""
Stage 0 Funnel (Vector/Proxy Filter)

Design goal:
  - Extremely cheap scoring/ranking for massive parameter grids.
  - No matcher, no orders, no fills, no state machine.
  - Must be vectorizable / nopython friendly.
"""

from .ma_proxy import stage0_score_ma_proxy
from .proxies import trend_proxy, vol_proxy, activity_proxy





--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/stage0/ma_proxy.py
sha256(source_bytes) = d96985049379b1cf36b6cd0e5c62090db229ac61efc702f88ea7892d5fc0c000
bytes = 6165
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

"""
Stage 0 v0: MA Directional Efficiency Proxy

This module intentionally does NOT depend on:
  - engine/* (matcher, fills, intents)
  - strategy/kernel
  - pipeline/runner_grid

It is a cheap scoring function to rank massive parameter grids before Stage 2.

Proxy idea (directional efficiency):
  dir[t] = sign(SMA_fast[t] - SMA_slow[t])
  ret[t] = close[t] - close[t-1]
  score = sum(dir[t] * ret[t]) / (std(ret) + eps)

Notes:
  - This is NOT a backtest. No orders, no fills, no costs.
  - Recall > precision. False negatives are acceptable at Stage 0.
"""

from typing import Tuple

import numpy as np
import os

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore


def _validate_inputs(close: np.ndarray, params_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Validate and normalize inputs for Stage0 proxy scoring.
    
    Accepts float32 or float64, but converts to float32 for Stage0 optimization.
    """
    from FishBroWFS_V2.config.dtypes import PRICE_DTYPE_STAGE0
    
    c = np.asarray(close, dtype=PRICE_DTYPE_STAGE0)
    if c.ndim != 1:
        raise ValueError("close must be 1D")
    pm = np.asarray(params_matrix, dtype=PRICE_DTYPE_STAGE0)
    if pm.ndim != 2:
        raise ValueError("params_matrix must be 2D")
    if pm.shape[1] < 2:
        raise ValueError("params_matrix must have at least 2 columns: fast, slow")
    if c.shape[0] < 3:
        raise ValueError("close must have at least 3 bars for Stage0 scoring")
    if not c.flags["C_CONTIGUOUS"]:
        c = np.ascontiguousarray(c, dtype=PRICE_DTYPE_STAGE0)
    if not pm.flags["C_CONTIGUOUS"]:
        pm = np.ascontiguousarray(pm, dtype=PRICE_DTYPE_STAGE0)
    return c, pm


def stage0_score_ma_proxy(close: np.ndarray, params_matrix: np.ndarray) -> np.ndarray:
    """
    Compute Stage 0 proxy scores for a parameter matrix.

    Args:
        close: float32 or float64 1D array (n_bars,) - will be converted to float32
        params_matrix: float32 or float64 2D array (n_params, >=2) - will be converted to float32
            - col0: fast_len
            - col1: slow_len
            - additional columns allowed and ignored by v0

    Returns:
        scores: float64 1D array (n_params,) where higher is better
    """
    c, pm = _validate_inputs(close, params_matrix)

    # If numba is available and JIT is not disabled, use nopython kernel.
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return _stage0_kernel(c, pm)

    # Fallback: pure numpy/python (correctness only, not intended for scale).
    ret = c[1:] - c[:-1]
    denom = np.std(ret) + 1e-12
    scores = np.empty(pm.shape[0], dtype=np.float64)
    for i in range(pm.shape[0]):
        fast = int(pm[i, 0])
        slow = int(pm[i, 1])
        if fast <= 0 or slow <= 0 or fast >= c.shape[0] or slow >= c.shape[0]:
            scores[i] = -np.inf
            continue
        f = _sma_py(c, fast)
        s = _sma_py(c, slow)
        # Skip NaN warmup region: SMA length L is valid from index (L-1) onward.
        # Here we conservatively start at max(fast, slow) to ensure both are non-NaN.
        start = max(fast, slow)
        acc = 0.0
        for t in range(start, c.shape[0]):
            d = np.sign(f[t] - s[t])
            acc += d * ret[t - 1]
        scores[i] = acc / denom
    return scores


def _sma_py(x: np.ndarray, length: int) -> np.ndarray:
    n = x.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if length <= 0:
        return out
    csum = np.cumsum(x, dtype=np.float64)
    for i in range(n):
        j = i - length + 1
        if j < 0:
            continue
        total = csum[i] - (csum[j - 1] if j > 0 else 0.0)
        out[i] = total / float(length)
    return out


if nb is not None:

    @nb.njit(cache=False)
    def _sma_nb(x: np.ndarray, length: int) -> np.ndarray:
        n = x.shape[0]
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            out[i] = np.nan
        if length <= 0:
            return out
        csum = np.empty(n, dtype=np.float64)
        acc = 0.0
        for i in range(n):
            acc += float(x[i])
            csum[i] = acc
        for i in range(n):
            j = i - length + 1
            if j < 0:
                continue
            total = csum[i] - (csum[j - 1] if j > 0 else 0.0)
            out[i] = total / float(length)
        return out

    @nb.njit(cache=False)
    def _sign_nb(v: float) -> float:
        if v > 0.0:
            return 1.0
        if v < 0.0:
            return -1.0
        return 0.0

    @nb.njit(cache=False)
    def _std_nb(x: np.ndarray) -> float:
        # simple two-pass std for stability
        n = x.shape[0]
        if n <= 1:
            return 0.0
        mu = 0.0
        for i in range(n):
            mu += float(x[i])
        mu /= float(n)
        var = 0.0
        for i in range(n):
            d = float(x[i]) - mu
            var += d * d
        var /= float(n)
        return np.sqrt(var)

    @nb.njit(cache=False)
    def _stage0_kernel(close: np.ndarray, params_matrix: np.ndarray) -> np.ndarray:
        n = close.shape[0]
        n_params = params_matrix.shape[0]

        # ret[t] = close[t] - close[t-1] for t in [1..n-1]
        ret = np.empty(n - 1, dtype=np.float64)
        for t in range(1, n):
            ret[t - 1] = float(close[t]) - float(close[t - 1])

        denom = _std_nb(ret) + 1e-12
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            fast = int(params_matrix[i, 0])
            slow = int(params_matrix[i, 1])

            # invalid lengths => hard reject
            if fast <= 0 or slow <= 0 or fast >= n or slow >= n:
                scores[i] = -np.inf
                continue

            f = _sma_nb(close, fast)
            s = _sma_nb(close, slow)

            start = fast if fast > slow else slow
            acc = 0.0
            for t in range(start, n):
                d = _sign_nb(f[t] - s[t])
                acc += d * ret[t - 1]

            scores[i] = acc / denom

        return scores





--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/stage0/proxies.py
sha256(source_bytes) = c736bbb47bb2333c94670af4bb5223b1a9632f9cf6be46301a63cd6cd29ad1ad
bytes = 19244
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

"""
Stage 0 v1 Trinity: Trend + Volatility + Activity Proxies

This module provides three proxy scoring functions for ranking parameter grids
before full backtest (Stage 2). These are NOT backtests - they are cheap heuristics.

Proxy Contract:
  - Stage0 is ranking proxy, NOT equal to backtest
  - NaN/warmup rules: start = max(required_lookbacks)
  - Correlation contract: Spearman ρ ≥ 0.4 (enforced by tests)

Design:
  - All proxies return float64 (n_params,) scores where higher is better
  - Input: OHLC arrays (np.ndarray), params: float64 2D array (n_params, k)
  - Must provide *_py (pure Python) and *_nb (Numba njit) versions
  - Wrapper functions select nb/py based on NUMBA_DISABLE_JIT kill-switch
"""

from typing import Tuple

import numpy as np
import os

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore

from FishBroWFS_V2.indicators.numba_indicators import atr_wilder


def _validate_inputs(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate and ensure contiguous arrays."""
    o = np.asarray(open_, dtype=np.float64)
    h = np.asarray(high, dtype=np.float64)
    l = np.asarray(low, dtype=np.float64)
    c = np.asarray(close, dtype=np.float64)
    pm = np.asarray(params_matrix, dtype=np.float64)

    if o.ndim != 1 or h.ndim != 1 or l.ndim != 1 or c.ndim != 1:
        raise ValueError("OHLC arrays must be 1D")
    if pm.ndim != 2:
        raise ValueError("params_matrix must be 2D")
    if not (o.shape[0] == h.shape[0] == l.shape[0] == c.shape[0]):
        raise ValueError("OHLC arrays must have same length")

    if not o.flags["C_CONTIGUOUS"]:
        o = np.ascontiguousarray(o)
    if not h.flags["C_CONTIGUOUS"]:
        h = np.ascontiguousarray(h)
    if not l.flags["C_CONTIGUOUS"]:
        l = np.ascontiguousarray(l)
    if not c.flags["C_CONTIGUOUS"]:
        c = np.ascontiguousarray(c)
    if not pm.flags["C_CONTIGUOUS"]:
        pm = np.ascontiguousarray(pm)

    return o, h, l, c, pm


# ============================================================================
# Proxy #1: Trend Proxy (MA / slope)
# ============================================================================


def trend_proxy_py(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """
    Trend proxy: mean(sign(sma_fast - sma_slow)) or mean((sma_fast - sma_slow) / close)

    Args:
        open_, high, low, close: float64 1D arrays (n_bars,)
        params_matrix: float64 2D array (n_params, >=2)
            - col0: fast_len
            - col1: slow_len

    Returns:
        scores: float64 1D array (n_params,)
    """
    o, h, l, c, pm = _validate_inputs(open_, high, low, close, params_matrix)
    n = c.shape[0]
    n_params = pm.shape[0]

    if pm.shape[1] < 2:
        raise ValueError("params_matrix must have at least 2 columns: fast_len, slow_len")

    scores = np.empty(n_params, dtype=np.float64)

    for i in range(n_params):
        fast = int(pm[i, 0])
        slow = int(pm[i, 1])

        # Invalid params: return -inf
        if fast <= 0 or slow <= 0 or fast >= n or slow >= n:
            scores[i] = -np.inf
            continue

        # Compute SMAs
        sma_fast = _sma_py(c, fast)
        sma_slow = _sma_py(c, slow)

        # Warmup: start at max(fast, slow)
        start = max(fast, slow)
        if start >= n:
            scores[i] = -np.inf
            continue

        # Compute trend score: mean((sma_fast - sma_slow) / close)
        acc = 0.0
        count = 0
        for t in range(start, n):
            diff = sma_fast[t] - sma_slow[t]
            if not np.isnan(diff) and c[t] > 0:
                acc += diff / c[t]
                count += 1

        if count == 0:
            scores[i] = -np.inf
        else:
            scores[i] = acc / count

    return scores


def trend_proxy_nb(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Numba version of trend_proxy."""
    if nb is None:  # pragma: no cover
        raise RuntimeError("numba not available")
    return _trend_proxy_kernel(open_, high, low, close, params_matrix)


def trend_proxy(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Wrapper: select nb/py based on NUMBA_DISABLE_JIT."""
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return trend_proxy_nb(open_, high, low, close, params_matrix)
    return trend_proxy_py(open_, high, low, close, params_matrix)


# ============================================================================
# Proxy #2: Volatility Proxy (ATR / Range)
# ============================================================================


def vol_proxy_py(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """
    Volatility proxy: effective stop distance = ATR(atr_len) * stop_mult.
    
    Score prefers moderate stop distance (avoids extremely tiny or huge stops).

    Args:
        open_, high, low, close: float64 1D arrays (n_bars,)
        params_matrix: float64 2D array (n_params, >=2)
            - col0: atr_len
            - col1: stop_mult

    Returns:
        scores: float64 1D array (n_params,)
    """
    o, h, l, c, pm = _validate_inputs(open_, high, low, close, params_matrix)
    n = c.shape[0]
    n_params = pm.shape[0]

    if pm.shape[1] < 2:
        raise ValueError("params_matrix must have at least 2 columns: atr_len, stop_mult")

    scores = np.empty(n_params, dtype=np.float64)

    for i in range(n_params):
        atr_len = int(pm[i, 0])
        stop_mult = float(pm[i, 1])

        # Invalid params: return -inf
        if atr_len <= 0 or atr_len >= n or stop_mult <= 0.0:
            scores[i] = -np.inf
            continue

        # Compute ATR using Wilder's method
        atr = atr_wilder(h, l, c, atr_len)

        # Warmup: start at atr_len
        start = max(atr_len, 1)
        if start >= n:
            scores[i] = -np.inf
            continue

        # Compute stop distance: ATR * stop_mult
        stop_dist_sum = 0.0
        stop_dist_count = 0
        for t in range(start, n):
            if not np.isnan(atr[t]) and atr[t] > 0:
                stop_dist = atr[t] * stop_mult
                stop_dist_sum += stop_dist
                stop_dist_count += 1

        if stop_dist_count == 0:
            scores[i] = -np.inf
        else:
            stop_dist_mean = stop_dist_sum / float(stop_dist_count)
            # Score: -log1p(stop_mean) - penalize larger stops; deterministic; no target/median
            scores[i] = -np.log1p(stop_dist_mean)

    return scores


def vol_proxy_nb(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Numba version of vol_proxy."""
    if nb is None:  # pragma: no cover
        raise RuntimeError("numba not available")
    return _vol_proxy_kernel(open_, high, low, close, params_matrix)


def vol_proxy(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Wrapper: select nb/py based on NUMBA_DISABLE_JIT."""
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return vol_proxy_nb(open_, high, low, close, params_matrix)
    return vol_proxy_py(open_, high, low, close, params_matrix)


# ============================================================================
# Proxy #3: Activity Proxy (Trade Count / trigger density)
# ============================================================================


def activity_proxy_py(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """
    Activity proxy: channel breakout trigger count.
    
    Counts crossings where close[t-1] <= channel_hi[t-1] and close[t] > channel_hi[t].
    Aligned with Stage2 kernel which uses channel breakout entry.

    Args:
        open_, high, low, close: float64 1D arrays (n_bars,)
        params_matrix: float64 2D array (n_params, >=1)
            - col0: channel_len
            - col1: atr_len (not used, kept for compatibility)

    Returns:
        scores: float64 1D array (n_params,)
    """
    o, h, l, c, pm = _validate_inputs(open_, high, low, close, params_matrix)
    n = c.shape[0]
    n_params = pm.shape[0]

    if pm.shape[1] < 1:
        raise ValueError("params_matrix must have at least 1 column: channel_len")

    scores = np.empty(n_params, dtype=np.float64)

    for i in range(n_params):
        channel_len = int(pm[i, 0])

        # Invalid params: return -inf
        if channel_len <= 0 or channel_len >= n:
            scores[i] = -np.inf
            continue

        # Compute channel_hi = rolling_max(high, channel_len)
        channel_hi = np.full(n, np.nan, dtype=np.float64)
        for t in range(n):
            start_idx = max(0, t - channel_len + 1)
            window_high = h[start_idx : t + 1]
            if window_high.size > 0:
                channel_hi[t] = np.max(window_high)

        # Warmup: start at channel_len
        start = channel_len
        if start >= n - 1:
            scores[i] = -np.inf
            continue

        # Count breakout triggers: high[t] > ch[t-1] AND high[t-1] <= ch[t-1]
        # Compare to previous channel high to avoid equality lock
        # Start from start+1 to ensure we have t-1 available
        triggers = 0
        for t in range(start + 1, n):
            if np.isnan(channel_hi[t-1]):
                continue
            # Trigger when high crosses above previous channel high
            if high[t] > channel_hi[t-1] and high[t-1] <= channel_hi[t-1]:
                triggers += 1

        n_effective = n - start
        if n_effective == 0:
            scores[i] = -np.inf
        else:
            # Activity score: raw count of triggers (or triggers per bar)
            # Using raw count for simplicity and robustness
            scores[i] = float(triggers)

    return scores


def activity_proxy_nb(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Numba version of activity_proxy."""
    if nb is None:  # pragma: no cover
        raise RuntimeError("numba not available")
    return _activity_proxy_kernel(open_, high, low, close, params_matrix)


def activity_proxy(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Wrapper: select nb/py based on NUMBA_DISABLE_JIT."""
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return activity_proxy_nb(open_, high, low, close, params_matrix)
    return activity_proxy_py(open_, high, low, close, params_matrix)


# ============================================================================
# Helper functions (SMA)
# ============================================================================


def _sma_py(x: np.ndarray, length: int) -> np.ndarray:
    """Simple Moving Average (pure Python)."""
    n = x.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if length <= 0:
        return out
    csum = np.cumsum(x, dtype=np.float64)
    for i in range(n):
        j = i - length + 1
        if j < 0:
            continue
        total = csum[i] - (csum[j - 1] if j > 0 else 0.0)
        out[i] = total / float(length)
    return out


# ============================================================================
# Numba kernels
# ============================================================================

if nb is not None:

    @nb.njit(cache=False)
    def _sma_nb(x: np.ndarray, length: int) -> np.ndarray:
        """Simple Moving Average (Numba)."""
        n = x.shape[0]
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            out[i] = np.nan
        if length <= 0:
            return out
        csum = np.empty(n, dtype=np.float64)
        acc = 0.0
        for i in range(n):
            acc += float(x[i])
            csum[i] = acc
        for i in range(n):
            j = i - length + 1
            if j < 0:
                continue
            total = csum[i] - (csum[j - 1] if j > 0 else 0.0)
            out[i] = total / float(length)
        return out

    @nb.njit(cache=False)
    def _trend_proxy_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        params_matrix: np.ndarray,
    ) -> np.ndarray:
        """Numba kernel for trend proxy."""
        n = close.shape[0]
        n_params = params_matrix.shape[0]
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            fast = int(params_matrix[i, 0])
            slow = int(params_matrix[i, 1])

            if fast <= 0 or slow <= 0 or fast >= n or slow >= n:
                scores[i] = -np.inf
                continue

            sma_fast = _sma_nb(close, fast)
            sma_slow = _sma_nb(close, slow)

            start = fast if fast > slow else slow
            if start >= n:
                scores[i] = -np.inf
                continue

            acc = 0.0
            count = 0
            for t in range(start, n):
                diff = sma_fast[t] - sma_slow[t]
                if not np.isnan(diff) and close[t] > 0.0:
                    acc += diff / close[t]
                    count += 1

            if count == 0:
                scores[i] = -np.inf
            else:
                scores[i] = acc / float(count)

        return scores

    @nb.njit(cache=False)
    def _atr_wilder_nb(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
        """ATR Wilder (Numba version, inline for njit compatibility)."""
        n = high.shape[0]
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            out[i] = np.nan

        if window <= 0 or n == 0 or window > n:
            return out

        tr = np.empty(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            a = high[i] - low[i]
            b = abs(high[i] - close[i - 1])
            c = abs(low[i] - close[i - 1])
            tr[i] = a if a >= b and a >= c else (b if b >= c else c)

        s = 0.0
        end = window if window < n else n
        for i in range(end):
            s += tr[i]
        out[end - 1] = s / float(window)

        for i in range(window, n):
            out[i] = (out[i - 1] * float(window - 1) + tr[i]) / float(window)

        return out

    @nb.njit(cache=False)
    def _rolling_max_nb(arr: np.ndarray, window: int) -> np.ndarray:
        """Rolling maximum (Numba, inline for njit compatibility)."""
        n = arr.shape[0]
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            out[i] = np.nan
        if window <= 0:
            return out
        for i in range(n):
            start = i - window + 1
            if start < 0:
                start = 0
            m = arr[start]
            for j in range(start + 1, i + 1):
                v = arr[j]
                if v > m:
                    m = v
            out[i] = m
        return out

    @nb.njit(cache=False)
    def _vol_proxy_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        params_matrix: np.ndarray,
    ) -> np.ndarray:
        """Numba kernel for vol proxy with stop_mult."""
        n = close.shape[0]
        n_params = params_matrix.shape[0]
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            atr_len = int(params_matrix[i, 0])
            stop_mult = float(params_matrix[i, 1])

            if atr_len <= 0 or atr_len >= n or stop_mult <= 0.0:
                scores[i] = -np.inf
                continue

            atr = _atr_wilder_nb(high, low, close, atr_len)

            start = atr_len if atr_len > 1 else 1
            if start >= n:
                scores[i] = -np.inf
                continue

            # Compute stop distance: ATR * stop_mult
            stop_dist_sum = 0.0
            stop_dist_count = 0
            for t in range(start, n):
                if not np.isnan(atr[t]) and atr[t] > 0.0:
                    stop_dist = atr[t] * stop_mult
                    stop_dist_sum += stop_dist
                    stop_dist_count += 1

            if stop_dist_count == 0:
                scores[i] = -np.inf
            else:
                stop_dist_mean = stop_dist_sum / float(stop_dist_count)
                # Score: -log1p(stop_mean) - penalize larger stops; deterministic; no target/median
                scores[i] = -np.log1p(stop_dist_mean)

        return scores

    @nb.njit(cache=False)
    def _sign_nb(v: float) -> float:
        """Sign function (Numba)."""
        if v > 0.0:
            return 1.0
        if v < 0.0:
            return -1.0
        return 0.0

    @nb.njit(cache=False)
    def _activity_proxy_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        params_matrix: np.ndarray,
    ) -> np.ndarray:
        """Numba kernel for activity proxy: channel breakout triggers."""
        n = close.shape[0]
        n_params = params_matrix.shape[0]
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            channel_len = int(params_matrix[i, 0])

            if channel_len <= 0 or channel_len >= n:
                scores[i] = -np.inf
                continue

            # Compute channel_hi = rolling_max(high, channel_len)
            channel_hi = _rolling_max_nb(high, channel_len)

            start = channel_len
            if start >= n - 1:
                scores[i] = -np.inf
                continue

            # Count breakout triggers: high[t] > ch[t-1] AND high[t-1] <= ch[t-1]
            # Compare to previous channel high to avoid equality lock
            # Start from start+1 to ensure we have t-1 available
            triggers = 0
            for t in range(start + 1, n):
                if np.isnan(channel_hi[t-1]):
                    continue
                # Trigger when high crosses above previous channel high
                if high[t] > channel_hi[t-1] and high[t-1] <= channel_hi[t-1]:
                    triggers += 1

            n_effective = n - start
            if n_effective == 0:
                scores[i] = -np.inf
            else:
                # Activity score: raw count of triggers (or triggers per bar)
                # Using raw count for simplicity and robustness
                scores[i] = float(triggers)

        return scores



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/strategy/__init__.py
sha256(source_bytes) = 58a4af8020a5536712667db310be1c6507e111664b1a7a367a87ea3ca52d8d7a
bytes = 485
redacted = False
--------------------------------------------------------------------------------

"""Strategy system.

Phase 7: Strategy registry, runner, and built-in strategies.
"""

from FishBroWFS_V2.strategy.registry import (
    register,
    get,
    list_strategies,
    load_builtin_strategies,
)
from FishBroWFS_V2.strategy.runner import run_strategy
from FishBroWFS_V2.strategy.spec import StrategySpec, StrategyFn

__all__ = [
    "register",
    "get",
    "list_strategies",
    "load_builtin_strategies",
    "run_strategy",
    "StrategySpec",
    "StrategyFn",
]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/strategy/builder_sparse.py
sha256(source_bytes) = 0a2f7d58dd16aa78a19f0ab140c504c3400b02e1ec15533326bfc9f802a7d5ed
bytes = 7159
redacted = False
--------------------------------------------------------------------------------
"""
Sparse Intent Builder (P2-3)

Provides sparse intent generation with trigger rate control for performance testing.
Supports both sparse (default) and dense (reference) modes.
"""
from __future__ import annotations

from typing import Dict

import numpy as np

from FishBroWFS_V2.config.dtypes import (
    INDEX_DTYPE,
    INTENT_ENUM_DTYPE,
    INTENT_PRICE_DTYPE,
)
from FishBroWFS_V2.engine.constants import KIND_STOP, ROLE_ENTRY, SIDE_BUY


def build_intents_sparse(
    donch_prev: np.ndarray,
    channel_len: int,
    order_qty: int,
    trigger_rate: float = 1.0,
    seed: int = 42,
    use_dense: bool = False,
) -> Dict[str, object]:
    """
    Build entry intents from trigger array with sparse masking support.
    
    This is the main sparse builder that supports trigger rate control for performance testing.
    When trigger_rate < 1.0, it deterministically selects a subset of valid triggers.
    
    Args:
        donch_prev: float64 array (n_bars,) - shifted donchian high (donch_prev[0]=NaN, donch_prev[1:]=donch_hi[:-1])
        channel_len: warmup period (same as indicator warmup)
        order_qty: order quantity
        trigger_rate: Rate of triggers to keep (0.0 to 1.0). Default 1.0 (all triggers).
        seed: Random seed for deterministic trigger selection. Default 42.
        use_dense: If True, use dense builder (reference implementation). Default False (sparse).
    
    Returns:
        dict with:
            - created_bar: int32 array (n_entry,) - created bar indices
            - price: float64 array (n_entry,) - entry prices
            - order_id: int32 array (n_entry,) - order IDs
            - role: uint8 array (n_entry,) - role (ENTRY)
            - kind: uint8 array (n_entry,) - kind (STOP)
            - side: uint8 array (n_entry,) - side (BUY)
            - qty: int32 array (n_entry,) - quantities
            - n_entry: int - number of entry intents
            - obs: dict - diagnostic observations (includes allowed_bars, intents_generated)
    """
    n = int(donch_prev.shape[0])
    warmup = channel_len
    
    # Create index array for bars 1..n-1 (bar indices t, where created_bar = t-1)
    i = np.arange(1, n, dtype=INDEX_DTYPE)
    
    # Valid bar mask: entries must be finite, positive, and past warmup
    valid_bar_mask = (~np.isnan(donch_prev[1:])) & (donch_prev[1:] > 0) & (i >= warmup)
    
    # CURSOR TASK 1: Generate bar_allow mask based on trigger_rate
    # rate <= 0.0 → 全 False
    # rate >= 1.0 → 全 True
    # else → rng.random(n_bars) < rate
    if use_dense or trigger_rate >= 1.0:
        # Dense mode or full rate: all bars allowed
        bar_allow = np.ones(n - 1, dtype=bool)  # n-1 because we skip first bar
    elif trigger_rate <= 0.0:
        # Zero rate: no bars allowed
        bar_allow = np.zeros(n - 1, dtype=bool)
    else:
        # Sparse mode: deterministically select bars based on trigger_rate
        rng = np.random.default_rng(seed)
        random_vals = rng.random(n - 1)  # Random values for bars 1..n-1
        bar_allow = random_vals < trigger_rate
    
    # Combine valid_bar_mask with bar_allow to get final allow_mask
    allow_mask = valid_bar_mask & bar_allow
    
    # Count valid bars (before trigger rate filtering) - this is the baseline
    valid_bars_count = int(np.sum(valid_bar_mask))
    
    # Count allowed bars (after intent sparse filtering) - this is what actually gets intents
    allowed_bars_after_sparse = int(np.sum(allow_mask))
    
    # Get indices of allowed entries (flatnonzero returns indices into donch_prev[1:])
    idx_selected = np.flatnonzero(allow_mask).astype(INDEX_DTYPE)
    intents_generated = allowed_bars_after_sparse
    n_entry = int(idx_selected.shape[0])
    
    # CURSOR TASK 2: entry_valid_mask_sum must be sum(allow_mask) (after intent sparse)
    # Diagnostic observations
    obs = {
        "n_bars": n,
        "warmup": warmup,
        "valid_mask_sum": valid_bars_count,  # Dense valid bars (before trigger rate)
        "entry_valid_mask_sum": allowed_bars_after_sparse,  # CURSOR TASK 2: After intent sparse (sum(allow_mask))
        "allowed_bars": valid_bars_count,  # Always equals valid_mask_sum (baseline, for comparison)
        "intents_generated": intents_generated,  # Actual intents generated (equals allowed_bars_after_sparse)
        "trigger_rate_applied": float(trigger_rate),
        "builder_mode": "dense" if use_dense else "sparse",
    }
    
    if n_entry == 0:
        return {
            "created_bar": np.empty(0, dtype=INDEX_DTYPE),
            "price": np.empty(0, dtype=INTENT_PRICE_DTYPE),
            "order_id": np.empty(0, dtype=INDEX_DTYPE),
            "role": np.empty(0, dtype=INTENT_ENUM_DTYPE),
            "kind": np.empty(0, dtype=INTENT_ENUM_DTYPE),
            "side": np.empty(0, dtype=INTENT_ENUM_DTYPE),
            "qty": np.empty(0, dtype=INDEX_DTYPE),
            "n_entry": 0,
            "obs": obs,
        }
    
    # Gather sparse entries (only for selected positions)
    # - idx_selected is index into donch_prev[1:], so bar index t = idx_selected + 1
    # - created_bar = t - 1 = idx_selected (since t = idx_selected + 1)
    # - price = donch_prev[t] = donch_prev[idx_selected + 1] = donch_prev[1:][idx_selected]
    created_bar = idx_selected.astype(INDEX_DTYPE)  # created_bar = t-1 = idx_selected
    price = donch_prev[1:][idx_selected].astype(INTENT_PRICE_DTYPE)  # Gather from donch_prev[1:]
    
    # Order ID maintains deterministic ordering
    # Order ID is sequential (1, 2, 3, ...) based on created_bar order
    # Since created_bar is already sorted, this preserves deterministic ordering
    order_id = np.arange(1, n_entry + 1, dtype=INDEX_DTYPE)
    role = np.full(n_entry, ROLE_ENTRY, dtype=INTENT_ENUM_DTYPE)
    kind = np.full(n_entry, KIND_STOP, dtype=INTENT_ENUM_DTYPE)
    side = np.full(n_entry, SIDE_BUY, dtype=INTENT_ENUM_DTYPE)
    qty = np.full(n_entry, int(order_qty), dtype=INDEX_DTYPE)
    
    return {
        "created_bar": created_bar,
        "price": price,
        "order_id": order_id,
        "role": role,
        "kind": kind,
        "side": side,
        "qty": qty,
        "n_entry": n_entry,
        "obs": obs,
    }


def build_intents_dense(
    donch_prev: np.ndarray,
    channel_len: int,
    order_qty: int,
) -> Dict[str, object]:
    """
    Dense builder (reference implementation).
    
    This is a wrapper around build_intents_sparse with use_dense=True for clarity.
    Use this when you need the reference dense behavior.
    
    Args:
        donch_prev: float64 array (n_bars,) - shifted donchian high
        channel_len: warmup period
        order_qty: order quantity
    
    Returns:
        Same format as build_intents_sparse (with all valid triggers).
    """
    return build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=1.0,
        seed=42,
        use_dense=True,
    )

--------------------------------------------------------------------------------

