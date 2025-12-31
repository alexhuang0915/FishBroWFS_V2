from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
UI_TEST = ROOT / "tests" / "ui" / "test_ui_style_contract.py"

def test_ui_contract_is_env_gated() -> None:
    text = UI_TEST.read_text(encoding="utf-8", errors="replace")
    assert "FISHBRO_UI_CONTRACT" in text, "UI contract tests must be gated by FISHBRO_UI_CONTRACT"
    assert re.search(r"pytest\.skip\(", text), "UI contract tests must call pytest.skip when env var not set"