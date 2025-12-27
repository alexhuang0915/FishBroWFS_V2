import os
import sys
import json
from pathlib import Path

# ================= 配置區 (Config) =================

# 1. 輸出檔名
OUTPUT_FILE = "SNAPSHOT_CLEAN.jsonl"

# 2. 總容量限制 (Bytes) - 設定 9.5MB (留一點緩衝給 Header)
MAX_TOTAL_SIZE = 9.5 * 1024 * 1024 

# 3. 單檔容量限制 (Bytes) - 單個檔案超過 100KB 就截斷 (避免誤收巨大數據)
MAX_FILE_SIZE = 100 * 1024

# 4. [黑名單] 絕對不掃描的資料夾 (名稱完全符合即跳過)
# 這裡把 LOCAL, FishBroData, outputs 都封殺了
EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode",
    ".venv", "venv", "env", "__pycache__",
    "outputs", "output", "dist", "build", "target",
    "FishBroData", "data", "Data", "db",
    "LOCAL", "local", "Local",  # <--- 這裡擋住你的 LOCAL
    "SNAPSHOT", "temp", "tmp", "logs"
}

# 5. [白名單] 只允許這些副檔名 (防堵 .csv, .parquet 或無副檔名亂入)
ALLOW_EXTENSIONS = {
    ".py", ".pyi",
    ".md", ".markdown",
    ".json", ".jsonl", ".toml", ".yaml", ".yml", ".ini",
    ".txt",  # 如果你有重要 txt 說明檔，請保留；若 txt 都是數據，請拿掉這行
    ".sh", ".bat",
    ".css", ".html", ".js", # 如果有 UI 相關
    ".sql"
}

# 6. [白名單] 允許的特定無副檔名檔案
ALLOW_FILENAMES = {
    "Makefile", "Dockerfile", "README", "LICENSE", ".gitignore", ".dockerignore", "requirements.txt"
}

# ================= 主程式 =================

def is_text_file(file_path):
    """簡單檢查是否為文字檔 (嘗試讀取前 1KB)"""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            if b'\0' in chunk:  # 有 NULL byte 通常是二進位
                return False
            # 嘗試解碼
            chunk.decode('utf-8')
        return True
    except Exception:
        return False

def generate_snapshot(root_dir):
    root_path = Path(root_dir).resolve()
    output_path = root_path / OUTPUT_FILE
    
    current_size = 0
    file_count = 0
    skipped_count = 0
    
    print(f"🚀 開始掃描 (Root: {root_path})")
    print(f"🚫 排除目錄: {EXCLUDE_DIRS}")
    print(f"✅ 允許格式: {ALLOW_EXTENSIONS} + {ALLOW_FILENAMES}")

    with open(output_path, 'w', encoding='utf-8') as out_f:
        # 寫入一個 Meta Header
        meta = {
            "type": "META",
            "project": root_path.name,
            "root": str(root_path),
            "generated_by": "snapshot_clean.py"
        }
        out_f.write(json.dumps(meta, ensure_ascii=False) + "\n")

        # 使用 os.walk 遍歷 (不依賴 Git)
        for dirpath, dirnames, filenames in os.walk(root_path):
            # 1. 過濾目錄 (原地修改 dirnames 以阻止 os.walk 進入)
            # 使用 set intersection 快速過濾
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith('.')]
            
            # 將路徑轉為 Path 物件
            current_dir = Path(dirpath)
            
            # 確保不會掃到輸出檔自己所在目錄 (如果它在根目錄其實沒差，因為 filenames 會過濾)
            if "SNAPSHOT" in current_dir.parts:
                continue

            for filename in filenames:
                file_path = current_dir / filename
                
                # 跳過輸出檔自己
                if filename == OUTPUT_FILE:
                    continue

                # 2. 檢查檔名規則
                ext = file_path.suffix.lower()
                is_allowed = (ext in ALLOW_EXTENSIONS) or (filename in ALLOW_FILENAMES)
                
                if not is_allowed:
                    # 再次檢查，如果是 .txt 但不在 data 資料夾下，或許可以放行？
                    # 為了安全，這裡嚴格執行：不在白名單就殺。
                    continue

                # 3. 檢查大小預判
                try:
                    stat = file_path.stat()
                    if stat.st_size > MAX_FILE_SIZE:
                        print(f"⚠️ 跳過過大檔案 ({stat.st_size/1024:.1f}KB): {file_path.relative_to(root_path)}")
                        skipped_count += 1
                        continue
                except Exception:
                    continue

                # 4. 讀取內容
                try:
                    if not is_text_file(file_path):
                        continue

                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # 建立 JSON 物件
                    record = {
                        "path": str(file_path.relative_to(root_path)).replace("\\", "/"),
                        "content": content
                    }
                    
                    json_line = json.dumps(record, ensure_ascii=False)
                    line_bytes = len(json_line.encode('utf-8'))

                    # 5. 檢查總容量
                    if current_size + line_bytes > MAX_TOTAL_SIZE:
                        print(f"🛑 容量已達上限 ({current_size/1024/1024:.2f}MB)，停止掃描。")
                        break
                    
                    out_f.write(json_line + "\n")
                    current_size += line_bytes
                    file_count += 1

                except Exception as e:
                    print(f"❌ 讀取錯誤 {filename}: {e}")
            
            if current_size > MAX_TOTAL_SIZE:
                break

    print("=" * 40)
    print(f"✨ 快照完成！")
    print(f"📂 輸出檔案: {OUTPUT_FILE}")
    print(f"📄 檔案數量: {file_count}")
    print(f"📦 總大小: {current_size / 1024 / 1024:.2f} MB")
    print("=" * 40)

if __name__ == "__main__":
    generate_snapshot(".")