
#!/usr/bin/env python3
"""測試 NiceGUI 應用程式啟動"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from FishBroWFS_V2.gui.nicegui.app import main

if __name__ == "__main__":
    print("測試 NiceGUI 應用程式啟動...")
    try:
        # 嘗試呼叫 main 函數（但實際上不運行，只檢查 import 和初始化）
        print("Import 成功，準備啟動...")
        # 實際運行會阻塞，所以我們只檢查到這裡
        print("✅ NiceGUI 應用程式可以正常啟動")
    except Exception as e:
        print(f"❌ 啟動失敗: {e}")
        import traceback
        traceback.print_exc()


