
"""圖表頁面 - Charts"""

from nicegui import ui

from ..api import list_chart_artifacts, load_chart_artifact
from ..state import app_state


def register() -> None:
    """註冊圖表頁面"""
    
    @ui.page("/charts/{job_id}")
    def charts_page(job_id: str) -> None:
        """圖表頁面"""
        ui.page_title(f"FishBroWFS V2 - Charts {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # DEV MODE banner - 更醒目的誠實化標示
            with ui.card().classes("w-full mb-6 bg-red-50 border-red-300"):
                with ui.row().classes("w-full items-center"):
                    ui.icon("error", size="lg").classes("text-red-600 mr-2")
                    ui.label("DEV MODE: Chart visualization NOT WIRED").classes("text-red-800 font-bold text-lg")
                ui.label("All chart artifacts are currently NOT IMPLEMENTED. UI cannot compute drawdown/correlation/heatmap.").classes("text-sm text-red-700 mb-2")
                ui.label("Constitutional principle: UI only renders artifacts produced by Research/Portfolio layer.").classes("text-xs text-red-600")
                ui.label("Expected artifact location: outputs/runs/{job_id}/viz/*.json").classes("font-mono text-xs text-gray-600")
            
            # 圖表選擇器
            chart_selector_container = ui.row().classes("w-full mb-6")
            
            # 圖表顯示容器
            chart_container = ui.column().classes("w-full")
            
            def refresh_charts(jid: str) -> None:
                """刷新圖表顯示"""
                chart_selector_container.clear()
                chart_container.clear()
                
                try:
                    # 獲取可用的圖表 artifact
                    artifacts = list_chart_artifacts(jid)
                    
                    with chart_selector_container:
                        ui.label("Select chart:").classes("mr-4 font-bold")
                        
                        # 預設圖表選項 - 但誠實標示為 "Not wired"
                        chart_options = {
                            "equity": "Equity Curve (NOT WIRED)",
                            "drawdown": "Drawdown Curve (NOT WIRED)",
                            "corr": "Correlation Matrix (NOT WIRED)",
                            "heatmap": "Heatmap (NOT WIRED)",
                        }
                        
                        # 如果有 artifact，使用 artifact 列表
                        if artifacts and len(artifacts) > 0:
                            chart_options = {a["id"]: f"{a.get('name', a['id'])} (Artifact)" for a in artifacts}
                        else:
                            # 沒有 artifact，顯示 "Not wired" 選項
                            chart_options = {"not_wired": "No artifacts available (NOT WIRED)"}
                        
                        chart_select = ui.select(
                            options=chart_options,
                            value=list(chart_options.keys())[0] if chart_options else None
                        ).props("disabled" if not artifacts else None).classes("flex-1")
                        
                        # 滑點等級選擇器 - 如果沒有 artifact 則 disabled
                        slippage_select = ui.select(
                            label="Slippage Level",
                            options={"S0": "S0", "S1": "S1", "S2": "S2", "S3": "S3"},
                            value="S0"
                        ).props("disabled" if not artifacts else None).classes("ml-4")
                        
                        # 更新圖表按鈕 - 如果沒有 artifact 則 disabled
                        def update_chart_display() -> None:
                            if chart_select.value == "not_wired":
                                with chart_container:
                                    chart_container.clear()
                                    display_not_wired_message()
                            else:
                                load_and_display_chart(jid, chart_select.value, slippage_select.value)
                        
                        ui.button("Load", on_click=update_chart_display, icon="visibility",
                                 props="disabled" if not artifacts else None).classes("ml-4")
                    
                    # 初始載入
                    if artifacts and len(artifacts) > 0:
                        load_and_display_chart(jid, list(chart_options.keys())[0], "S0")
                    else:
                        with chart_container:
                            display_not_wired_message()
                
                except Exception as e:
                    with chart_container:
                        ui.label(f"Load failed: {e}").classes("text-red-600")
                        display_not_wired_message()
            
            def display_not_wired_message() -> None:
                """顯示 'Not wired' 訊息"""
                with ui.card().classes("w-full p-6 bg-gray-50 border-gray-300"):
                    ui.icon("warning", size="xl").classes("text-gray-500 mx-auto mb-4")
                    ui.label("Chart visualization NOT WIRED").classes("text-xl font-bold text-gray-700 text-center mb-2")
                    ui.label("The chart artifact system is not yet implemented.").classes("text-gray-600 text-center mb-4")
                    
                    ui.label("Expected workflow:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-gray-600"):
                        ui.label("1. Research/Portfolio layer produces visualization artifacts")
                        ui.label("2. Artifacts saved to outputs/runs/{job_id}/viz/")
                        ui.label("3. UI loads and renders artifacts (no computation)")
                        ui.label("4. UI shows equity/drawdown/corr/heatmap from artifacts")
                    
                    ui.label("Current status:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-red-600"):
                        ui.label("• Artifact production NOT IMPLEMENTED")
                        ui.label("• UI cannot compute drawdown/correlation")
                        ui.label("• All chart displays are placeholders")
            
            def load_and_display_chart(jid: str, chart_type: str, slippage_level: str) -> None:
                """載入並顯示圖表"""
                chart_container.clear()
                
                with chart_container:
                    ui.label(f"{chart_type} - {slippage_level}").classes("text-xl font-bold mb-4")
                    
                    try:
                        # 嘗試載入 artifact
                        artifact_data = load_chart_artifact(jid, f"{chart_type}_{slippage_level}")
                        
                        if artifact_data and artifact_data.get("type") != "not_implemented":
                            # 顯示 artifact 資訊
                            with ui.card().classes("w-full p-4 mb-4 bg-green-50 border-green-200"):
                                ui.label("✅ Artifact Loaded").classes("font-bold mb-2 text-green-800")
                                ui.label(f"Type: {artifact_data.get('type', 'unknown')}").classes("text-sm")
                                ui.label(f"Data points: {len(artifact_data.get('data', []))}").classes("text-sm")
                                ui.label(f"Generated at: {artifact_data.get('generated_at', 'unknown')}").classes("text-sm")
                            
                            # 根據圖表類型顯示不同的預覽
                            if chart_type == "equity":
                                display_equity_chart_preview(artifact_data)
                            elif chart_type == "drawdown":
                                display_drawdown_chart_preview(artifact_data)
                            elif chart_type == "corr":
                                display_correlation_preview(artifact_data)
                            elif chart_type == "heatmap":
                                display_heatmap_preview(artifact_data)
                            else:
                                display_generic_chart_preview(artifact_data)
                        
                        else:
                            # 顯示 NOT WIRED 訊息
                            display_not_wired_chart(chart_type, slippage_level)
                    
                    except Exception as e:
                        ui.label(f"Chart load error: {e}").classes("text-red-600")
                        display_not_wired_chart(chart_type, slippage_level)
            
            def display_not_wired_chart(chart_type: str, slippage_level: str) -> None:
                """顯示 NOT WIRED 圖表訊息"""
                with ui.card().classes("w-full p-6 bg-red-50 border-red-300"):
                    ui.icon("error", size="xl").classes("text-red-600 mx-auto mb-4")
                    ui.label(f"NOT WIRED: {chart_type} - {slippage_level}").classes("text-xl font-bold text-red-800 text-center mb-2")
                    ui.label("This chart visualization is not yet implemented.").classes("text-red-700 text-center mb-4")
                    
                    # 憲法級原則提醒
                    with ui.card().classes("w-full p-4 bg-white border-gray-300"):
                        ui.label("Constitutional principles:").classes("font-bold mb-2")
                        with ui.column().classes("ml-2 text-sm text-gray-700"):
                            ui.label("• All visualization data must be produced by Research/Portfolio as artifacts")
                            ui.label("• UI only renders, never computes drawdown/correlation/etc.")
                            ui.label("• Artifacts are the single source of truth")
                            ui.label("• UI cannot compute anything - must wait for artifact production")
                    
                    # 預期的工作流程
                    ui.label("Expected workflow:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-gray-600"):
                        ui.label(f"1. Research layer produces {chart_type}_{slippage_level}.json")
                        ui.label("2. Artifact saved to outputs/runs/{job_id}/viz/")
                        ui.label("3. UI loads artifact via Control API")
                        ui.label("4. UI renders using artifact data (no computation)")
                    
                    # 當前狀態
                    ui.label("Current status:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-red-600"):
                        ui.label("• Artifact production NOT IMPLEMENTED")
                        ui.label("• Control API endpoint returns 'not_implemented'")
                        ui.label("• UI shows this honest 'NOT WIRED' message")
                        ui.label("• No fake charts or placeholder data")
            
            def display_equity_chart_preview(data: dict) -> None:
                """顯示 Equity Curve 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Equity Curve Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: UI only renders artifact, no computation").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域 - 真實 artifact 資料
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📈 Real Equity Curve from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取統計資訊
                    if "stats" in data:
                        stats = data["stats"]
                        with ui.grid(columns=4).classes("w-full mt-4 gap-2"):
                            ui.label("Final equity:").classes("font-bold")
                            ui.label(f"{stats.get('final_equity', 'N/A')}").classes("text-right")
                            ui.label("Max drawdown:").classes("font-bold")
                            ui.label(f"{stats.get('max_drawdown', 'N/A')}%").classes("text-right text-red-600")
                            ui.label("Sharpe ratio:").classes("font-bold")
                            ui.label(f"{stats.get('sharpe_ratio', 'N/A')}").classes("text-right")
                            ui.label("Trades:").classes("font-bold")
                            ui.label(f"{stats.get('trades', 'N/A')}").classes("text-right")
            
            def display_drawdown_chart_preview(data: dict) -> None:
                """顯示 Drawdown Curve 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Drawdown Curve Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: Drawdown must be computed by Research, not UI").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📉 Real Drawdown Curve from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取統計資訊
                    if "stats" in data:
                        stats = data["stats"]
                        with ui.grid(columns=3).classes("w-full mt-4 gap-2"):
                            ui.label("Max drawdown:").classes("font-bold")
                            ui.label(f"{stats.get('max_drawdown', 'N/A')}%").classes("text-right text-red-600")
                            ui.label("Drawdown period:").classes("font-bold")
                            ui.label(f"{stats.get('drawdown_period', 'N/A')} days").classes("text-right")
                            ui.label("Recovery time:").classes("font-bold")
                            ui.label(f"{stats.get('recovery_time', 'N/A')} days").classes("text-right")
            
            def display_correlation_preview(data: dict) -> None:
                """顯示 Correlation Matrix 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Correlation Matrix Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: Correlation must be computed by Portfolio, not UI").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("🔗 Real Correlation Matrix from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取摘要
                    if "summary" in data:
                        summary = data["summary"]
                        ui.label("Correlation summary:").classes("font-bold mt-4")
                        for pair, value in summary.items():
                            with ui.row().classes("w-full text-sm"):
                                ui.label(f"{pair}:").classes("font-bold flex-1")
                                ui.label(f"{value}").classes("text-right")
            
            def display_heatmap_preview(data: dict) -> None:
                """顯示 Heatmap 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Heatmap Preview").classes("font-bold mb-2")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("🔥 Real Heatmap from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取資訊
                    if "description" in data:
                        ui.label(f"Description: {data['description']}").classes("text-sm mt-4")
            
            def display_generic_chart_preview(data: dict) -> None:
                """顯示通用圖表預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Chart Preview").classes("font-bold mb-2")
                    
                    with ui.row().classes("w-full h-48 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📊 Chart rendering area").classes("text-gray-500")
                    
                    # 顯示 artifact 基本資訊
                    ui.label(f"Type: {data.get('type', 'unknown')}").classes("text-sm mt-2")
                    ui.label(f"Data points: {len(data.get('data', []))}").classes("text-sm")
            
            def display_dev_mode_chart(chart_type: str, slippage_level: str) -> None:
                """顯示 DEV MODE 圖表"""
                with ui.card().classes("w-full p-4"):
                    ui.label(f"DEV MODE: {chart_type} - {slippage_level}").classes("font-bold mb-2 text-yellow-700")
                    ui.label("This is a placeholder. Real artifacts will be loaded when available.").classes("text-sm text-gray-600 mb-4")
                    
                    with ui.row().classes("w-full h-48 items-center justify-center bg-yellow-50 rounded border border-yellow-200"):
                        ui.label(f"🎨 {chart_type} chart placeholder ({slippage_level})").classes("text-yellow-600")
                    
                    # 說明文字
                    ui.label("Expected artifact location:").classes("font-bold mt-4 text-sm")
                    ui.label(f"outputs/runs/{{job_id}}/viz/{chart_type}_{slippage_level}.json").classes("font-mono text-xs text-gray-600")
                    
                    # 憲法級原則提醒
                    ui.label("Constitutional principles:").classes("font-bold mt-4 text-sm")
                    ui.label("• All visualization data must be produced by Research/Portfolio as artifacts").classes("text-xs text-gray-600")
                    ui.label("• UI only renders, never computes drawdown/correlation/etc.").classes("text-xs text-gray-600")
                    ui.label("• Artifacts are the single source of truth").classes("text-xs text-gray-600")
            
            # 初始載入
            refresh_charts(job_id)


