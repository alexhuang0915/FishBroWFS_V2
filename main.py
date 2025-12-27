import sys
import os
from nicegui import ui

# 強制設定路徑
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_PATH)

print(f"🚀 Init FishBro War Room...")
print(f"📂 SRC Path: {SRC_PATH}")

try:
    from gui.nicegui.pages.war_room import war_room_page
except ImportError as e:
    import traceback
    print("\n❌ IMPORT ERROR! 無法載入 War Room 模組。")
    print(f"錯誤原因: {e}")
    print("詳細堆疊:")
    traceback.print_exc()
    sys.exit(1)

@ui.page('/')
def index():
    war_room_page()

if __name__ in {"__main__", "__mp_main__"}:
    # 檢查是否能讀到 service
    try:
        import gui.services.war_room_service
        print("✅ Service module found.")
    except ImportError:
        print("⚠️ Warning: Service module check failed.")

    ui.run(title="FishBro V3", port=8080, dark=True, reload=True, show=False)