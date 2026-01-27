import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from click.testing import CliRunner
from control.shared_cli import shared_cli

class TestBuildDataPurge(unittest.TestCase):
    def test_purge_workflow(self):
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cache_root = tmpdir_path / "cache"
            shared_root = cache_root / "shared"
            dataset_dir = shared_root / "2026Q1" / "CME.MNQ"
            
            # Setup dummy files
            bars_dir = dataset_dir / "bars"
            feat_dir = dataset_dir / "features"
            bars_dir.mkdir(parents=True)
            feat_dir.mkdir(parents=True)
            
            (bars_dir / "normalized_bars.npz").write_text("data")
            (bars_dir / "resampled_60m.npz").write_text("data")
            (feat_dir / "features_60m.npz").write_text("data")
            (dataset_dir / "shared_manifest.json").write_text("{}")

            runner = CliRunner()
            
            with patch("control.shared_cli.get_shared_cache_root", return_value=shared_root):
                # 1. Purge features only for 60m
                result = runner.invoke(shared_cli, [
                    "purge", 
                    "--season", "2026Q1", 
                    "--dataset-id", "CME.MNQ", 
                    "--tfs", "60", 
                    "--features"
                ])
                self.assertEqual(result.exit_code, 0)
                self.assertFalse((feat_dir / "features_60m.npz").exists())
                self.assertTrue((bars_dir / "resampled_60m.npz").exists())
                self.assertTrue((dataset_dir / "purge_manifest.json").exists())
                
                # Check manifest
                with (dataset_dir / "purge_manifest.json").open("r") as f:
                    manifest = json.load(f)
                    self.assertIn(str(feat_dir / "features_60m.npz"), manifest["deleted_paths"])

                # 2. Purge bars and features (all)
                result = runner.invoke(shared_cli, [
                    "purge", 
                    "--season", "2026Q1", 
                    "--dataset-id", "CME.MNQ", 
                    "--all"
                ])
                self.assertEqual(result.exit_code, 0)
                self.assertTrue(dataset_dir.exists())
                # Check that bars/features dirs are gone
                self.assertFalse((dataset_dir / "bars").exists())
                self.assertFalse((dataset_dir / "features").exists())
                self.assertTrue((dataset_dir / "purge_manifest.json").exists())

if __name__ == "__main__":
    unittest.main()
