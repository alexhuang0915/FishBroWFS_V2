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