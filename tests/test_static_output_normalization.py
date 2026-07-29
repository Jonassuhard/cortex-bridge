from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = ROOT / "scripts" / "normalize-static-output.py"


class StaticOutputNormalizationTest(unittest.TestCase):
    def test_text_artifacts_are_trimmed_and_second_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out"
            output.mkdir()
            script = output / "bundle.js"
            script.write_bytes(b"const first = 1;   \nconst second = 2;\t")
            image = output / "fixture.png"
            original_image = b"\x89PNG\r\n\x1a\nsynthetic   \n"
            image.write_bytes(original_image)

            first = subprocess.run(
                [str(NORMALIZER), str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=10,
            )
            second = subprocess.run(
                [str(NORMALIZER), str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=10,
            )
            normalized_script = script.read_bytes()
            preserved_image = image.read_bytes()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("changed=1", first.stdout)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("changed=0", second.stdout)
        self.assertEqual(normalized_script, b"const first = 1;\nconst second = 2;")
        self.assertEqual(preserved_image, original_image)


if __name__ == "__main__":
    unittest.main()
