
"""NiceGUI 路由設定"""

from nicegui import ui


def register_pages() -> None:
    """註冊所有頁面路由"""
    from .pages import (
        register_home,
        register_new_job,
        register_job,
        register_results,
        register_charts,
        register_deploy,
        register_history,
        register_candidates,
        register_wizard,
        register_portfolio,
        register_run_detail,
    )
    
    # 註冊所有頁面
    register_home()
    register_new_job()
    register_job()
    register_results()
    register_charts()
    register_deploy()
    register_history()
    register_candidates()
    register_wizard()
    register_portfolio()
    register_run_detail()


