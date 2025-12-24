
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


