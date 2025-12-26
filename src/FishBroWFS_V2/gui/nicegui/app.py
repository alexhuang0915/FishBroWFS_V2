
"""NiceGUI 主應用程式 - 唯一 UI 入口點"""

import json
from nicegui import ui
from .router import register_pages
from ..theme import inject_global_styles
from FishBroWFS_V2.core.service_identity import get_service_identity


@ui.page('/health')
def health_page():
    """健康檢查端點 - 用於 launcher readiness check"""
    # 用純文字就好，launcher 只需要 200 OK
    ui.label('ok')


@ui.page('/__identity')
def identity_page():
    """服務身份端點 - 用於拓撲可觀測性"""
    ident = get_service_identity(service_name="nicegui", db_path=None)
    # 使用 ui.code 顯示 JSON，確保可複製
    ui.code(json.dumps(ident, indent=2, sort_keys=True), language='json')


def main() -> None:
    """啟動 NiceGUI 應用程式"""
    # 注入全域樣式（必須在 register_pages 之前）
    inject_global_styles()
    
    # 註冊頁面路由
    register_pages()
    
    # 啟動伺服器
    ui.run(
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,  # 避免 gio: Operation not supported
    )


# 以下函數簽名符合 P0-0 要求，實際實作在 layout.py 中
def render_header(season: str) -> None:
    """渲染頁面頂部 header（包含 season 顯示）"""
    from .layout import render_header as _render_header
    _render_header(season)


def render_nav(active_path: str) -> None:
    """渲染側邊導航欄（用於需要側邊導航的頁面）"""
    from .layout import render_nav as _render_nav
    _render_nav(active_path)


def render_shell(active_path: str, season: str = "2026Q1"):
    """渲染完整 shell（header + 主內容區）"""
    from .layout import render_shell as _render_shell
    return _render_shell(active_path, season)


if __name__ == "__main__":
    main()


