
"""NiceGUI 主應用程式 - 唯一 UI 入口點"""

from nicegui import ui
from .router import register_pages


@ui.page('/health')
def health_page():
    """健康檢查端點 - 用於 launcher readiness check"""
    # 用純文字就好，launcher 只需要 200 OK
    ui.label('ok')


def main() -> None:
    """啟動 NiceGUI 應用程式"""
    register_pages()  # 只負責註冊 @ui.page，不能建任何 ui 元件
    ui.run(
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,  # 避免 gio: Operation not supported
    )


if __name__ == "__main__":
    main()


