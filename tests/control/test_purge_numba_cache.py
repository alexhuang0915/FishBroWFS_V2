import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from click.testing import CliRunner

from control.shared_cli import shared_cli


class TestPurgeNumbaCache(unittest.TestCase):
    def test_purge_numba_writes_audit_and_deletes_children(self):
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cache_root = tmpdir_path / "cache"
            numba_root = cache_root / "numba"
            numba_root.mkdir(parents=True)

            # Dummy compiled artifacts
            sub = numba_root / "indicators_deadbeef"
            sub.mkdir()
            (sub / "fn.nbi").write_text("x")
            (sub / "fn.nbc").write_text("y")

            runner = CliRunner()
            with patch("control.shared_cli.get_numba_cache_root", return_value=numba_root):
                result = runner.invoke(shared_cli, ["purge-numba"])
                self.assertEqual(result.exit_code, 0, msg=result.output)

            # Subdir deleted, audit present in root
            self.assertFalse(sub.exists())
            audit_path = numba_root / "purge_manifest.json"
            self.assertTrue(audit_path.exists())

            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["scope"], "numba")
            self.assertIn(str(sub), audit["deleted_paths"])


if __name__ == "__main__":
    unittest.main()

