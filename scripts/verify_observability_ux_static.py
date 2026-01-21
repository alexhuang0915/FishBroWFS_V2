
import sys
from pathlib import Path

def check_file_contains(path, required_strings):
    print(f"Checking {path}...")
    if not path.exists():
        print(f"FAIL: {path} not found")
        return False
    
    content = path.read_text("utf-8")
    missing = [s for s in required_strings if s not in content]
    if missing:
        print(f"FAIL: Missing strings: {missing}")
        return False
        
    print("PASS")
    return True

def main():
    repo_root = Path("src/gui/desktop")
    
    # 1. OpsTab: Timeline & Error Digest & Artifact Copy
    ops_tab = repo_root / "tabs/ops_tab.py"
    if not check_file_contains(ops_tab, [
        "def _build_timeline(self, status: str) -> str:",
        "self.error_digest = QTextEdit()",
        "copy_art = QAction(\"Copy Artifact Dir\", self)"
    ]):
        sys.exit(1)

    # 2. OpTabRefactored: Deep Link to Ops
    op_tab = repo_root / "tabs/op_tab_refactored.py"
    if not check_file_contains(op_tab, [
        "self.action_router.handle_action(f\"internal://job/{job_id}\")",
        "lr_btn.clicked.connect(self._on_open_ops)"
    ]):
        sys.exit(1)

    # 3. MainWindow: Routing Logic
    main_window = repo_root / "control_station.py"
    if not check_file_contains(main_window, [
        "if target.startswith(\"internal://job/\"):",
        "self._open_tool_tab(\"ops\")"
    ]):
        sys.exit(1)

    print("ALL OBSERVABILITY UX FEATURES VERIFIED STATICALLY")

if __name__ == "__main__":
    main()
