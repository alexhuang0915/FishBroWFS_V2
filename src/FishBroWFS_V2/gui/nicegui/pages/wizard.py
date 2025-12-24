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