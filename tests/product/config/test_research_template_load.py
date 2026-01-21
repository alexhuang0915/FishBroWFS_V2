
import pytest
import yaml
from pathlib import Path

METADATA_PATH = Path("configs/strategies/wfs/research_template_v1.yaml")

class TestResearchTemplateLoad:
    def test_template_exists(self):
        """Verify the template file exists."""
        assert METADATA_PATH.exists(), f"Template not found at {METADATA_PATH}"

    def test_template_valid_yaml(self):
        """Verify template is valid YAML."""
        content = METADATA_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        assert isinstance(data, dict), "Template must be a dictionary"
        
    def test_template_required_fields(self):
        """Verify standard fields are present."""
        content = METADATA_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        
        required = ["version", "strategy_id", "determinism", "parameters", "features"]
        for field in required:
            assert field in data, f"Missing required field: {field}"
            
    def test_determinism_seed(self):
        """Verify default seed is set."""
        content = METADATA_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        
        assert "default_seed" in data["determinism"]
        assert data["determinism"]["default_seed"] == 42
