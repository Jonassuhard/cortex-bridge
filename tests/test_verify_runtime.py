import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_runtime", ROOT / "scripts" / "verify-runtime.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class VerifyRuntimeTest(unittest.TestCase):
    def test_repository_runtime_artifacts_pass(self):
        result = MODULE.verify(ROOT)
        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(len(result["checks"]), 4)

    def test_fallback_rejects_mission_surface(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "frontend/out").mkdir(parents=True)
            (root / "frontend/fallback").mkdir(parents=True)
            (root / "docs/verification").mkdir(parents=True)
            (root / "frontend/out/index.html").write_text("ui", encoding="utf-8")
            (root / "docs/verification/runtime-schema.json").write_text("{}", encoding="utf-8")
            (root / "frontend/fallback/index.html").write_text("Interface principale indisponible /api/missions", encoding="utf-8")
            result = MODULE.verify(root)
            self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
