
from __future__ import annotations
from nicegui import ui

# 根據 P0-0 要求：Dashboard / Wizard / History / Candidates / Portfolio / Deploy / Settings / Status
NAV = [
    ("Dashboard", "/"),
    ("Wizard", "/wizard"),
    ("History", "/history"),
    ("Candidates", "/candidates"),
    ("Portfolio", "/portfolio"),
    ("Deploy", "/deploy"),
    ("Settings", "/settings"),
    ("Status", "/status"),
]

def render_header(season: str) -> None:
    """渲染頁面頂部 header（包含 season 顯示）"""
    with ui.header().classes("fish-header items-center justify-between px-6 py-4"):
        with ui.row().classes("items-center gap-4"):
            ui.icon("rocket_launch", size="lg").classes("text-cyber-500")
            ui.label("FishBroWFS V2").classes("text-2xl font-bold text-cyber-glow")
            ui.label(f"Season: {season}").classes("text-sm bg-nexus-800 px-3 py-1 rounded-full")
        
        with ui.row().classes("gap-2"):
            for name, path in NAV:
                ui.link(name, path).classes(
                    "px-4 py-2 rounded-lg no-underline transition-colors "
                    "hover:bg-nexus-800 text-slate-300"
                )

def render_nav(active_path: str) -> None:
    """渲染側邊導航欄（用於需要側邊導航的頁面）"""
    with ui.column().classes("w-64 bg-nexus-900 h-full p-4 border-r border-nexus-800"):
        ui.label("Navigation").classes("text-lg font-bold mb-4 text-cyber-400")
        
        for name, path in NAV:
            is_active = active_path == path
            classes = "px-4 py-3 rounded-lg mb-2 no-underline transition-colors "
            if is_active:
                classes += "nav-active bg-nexus-800 text-cyber-300 font-semibold"
            else:
                classes += "hover:bg-nexus-800 text-slate-400"
            
            ui.link(name, path).classes(classes)

def render_shell(active_path: str, season: str = "2026Q1") -> None:
    """渲染完整 shell（header + 主內容區）"""
    # 套用 cyberpunk body classes
    ui.query("body").classes("bg-nexus-950 text-slate-300 font-sans h-screen flex flex-col overflow-hidden")
    
    # 渲染 header
    render_header(season)
    
    # 主內容區容器
    with ui.row().classes("flex-1 overflow-hidden"):
        # 側邊導航（可選，根據頁面需求）
        # render_nav(active_path)
        
        # 主內容
        with ui.column().classes("flex-1 p-6 overflow-auto"):
            yield  # 讓呼叫者可以插入內容


def render_topbar(*args, **kwargs):
    """向後相容性 shim：舊頁面可能呼叫 render_topbar，將其映射到 render_header"""
    # 如果第一個參數是字串，視為 title 參數（舊版 render_topbar 可能接受 title）
    if args and isinstance(args[0], str):
        # 舊版 render_topbar(title) -> 呼叫 render_header(season)
        # 這裡我們忽略 title，使用預設 season
        season = "2026Q1"
        if len(args) > 1 and isinstance(args[1], str):
            season = args[1]
        return render_header(season)
    # 如果沒有參數，使用預設 season
    return render_header(kwargs.get("season", "2026Q1"))


