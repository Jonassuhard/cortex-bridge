"""Behavioral tests for the public-tree privacy gate."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "check-public-privacy.sh"


class PublicPrivacyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "docs").mkdir()
        self.allowlist = self.root / "allowlist.txt"
        self.allowlist.write_text("", encoding="utf-8")
        self.markers = self.root / "markers.txt"
        self.markers.write_text("Private Person Fixture\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_scan(
        self,
        *,
        marker_file: Path | None = None,
        allowlist_file: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, **(extra_env or {})}
        return subprocess.run(
            [
                "bash",
                str(SCANNER),
                "--root",
                str(self.root),
                "--markers",
                str(marker_file or self.markers),
                "--url-allowlist",
                str(allowlist_file or self.allowlist),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_empty_marker_file_fails_closed(self) -> None:
        empty_markers = self.root / "empty-markers.txt"
        empty_markers.write_text("\n# no owner markers\n", encoding="utf-8")
        (self.root / "README.md").write_text("Public fixture\n", encoding="utf-8")

        result = self.run_scan(marker_file=empty_markers)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("marker_config", result.stdout)

    def test_marker_detection_never_prints_the_marker(self) -> None:
        secret = "Private Person Fixture"
        (self.root / "README.md").write_text(
            f"A fixture accidentally contains {secret}.\n", encoding="utf-8"
        )

        result = self.run_scan()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private_marker", result.stdout)
        self.assertIn("README.md", result.stdout)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)

    def test_url_allowlist_is_exact_including_query_and_fragment(self) -> None:
        canonical = "https://docs.example.invalid/product"
        self.allowlist.write_text(f"{canonical}\n", encoding="utf-8")
        page = self.root / "README.md"
        page.write_text(f"Official: {canonical}\n", encoding="utf-8")
        clean = self.run_scan()
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

        page.write_text(f"Leaked: {canonical}?profile=private#token\n", encoding="utf-8")
        rejected = self.run_scan()

        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("unapproved_url", rejected.stdout)
        self.assertNotIn("profile=private", rejected.stdout)

    def test_dependency_lock_urls_do_not_require_public_navigation_allowlisting(self) -> None:
        (self.root / "package-lock.json").write_text(
            '{"resolved":"https://registry.example.invalid/pkg/-/pkg-1.0.0.tgz"}\n',
            encoding="utf-8",
        )

        result = self.run_scan()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_encoded_private_path_is_rejected(self) -> None:
        (self.root / "docs" / "guide.md").write_text(
            "file%3A%2F%2F%2FUsers%2Fprivate-user%2FDesktop%2Fproof.png\n",
            encoding="utf-8",
        )

        result = self.run_scan()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private_path", result.stdout)
        self.assertNotIn("private-user", result.stdout)

    def test_git_tracked_file_is_scanned_even_when_ignored(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("tracked-proof.txt\n", encoding="utf-8")
        proof = self.root / "tracked-proof.txt"
        proof.write_text("Private Person Fixture\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.root), "add", ".gitignore"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.root), "add", "-f", "tracked-proof.txt"],
            check=True,
        )

        result = self.run_scan()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private_marker", result.stdout)
        self.assertIn("tracked-proof.txt", result.stdout)

    def test_unknown_public_binary_is_rejected(self) -> None:
        media = self.root / "docs" / "media"
        media.mkdir()
        (media / "payload.bin").write_bytes(b"\x00\x01\x02unknown")

        result = self.run_scan()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown_public_binary", result.stdout)

    def test_public_image_requires_metadata_and_ocr_tools(self) -> None:
        screenshots = self.root / "docs" / "screenshots"
        screenshots.mkdir()
        (screenshots / "fixture.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"synthetic"
        )

        result = self.run_scan(
            extra_env={
                "EXIFTOOL_BIN": str(self.root / "missing-exiftool"),
                "TESSERACT_BIN": str(self.root / "missing-tesseract"),
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_image_tool", result.stdout)

    def test_public_image_requires_both_ocr_languages(self) -> None:
        screenshots = self.root / "docs" / "screenshots"
        screenshots.mkdir()
        (screenshots / "fixture.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"synthetic"
        )
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_exiftool = bin_dir / "exiftool"
        fake_exiftool.write_text("#!/bin/sh\nprintf '[]\\n'\n", encoding="utf-8")
        fake_exiftool.chmod(0o755)
        fake_tesseract = bin_dir / "tesseract"
        fake_tesseract.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--list-langs\" ]; then printf 'eng\\n'; exit 0; fi\n"
            "printf 'clean\\n'\n",
            encoding="utf-8",
        )
        fake_tesseract.chmod(0o755)

        result = self.run_scan(
            extra_env={
                "EXIFTOOL_BIN": str(fake_exiftool),
                "TESSERACT_BIN": str(fake_tesseract),
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_image_tool", result.stdout)

    def test_metadata_and_ocr_findings_are_redacted(self) -> None:
        screenshots = self.root / "docs" / "screenshots"
        screenshots.mkdir()
        image = screenshots / "fixture.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"synthetic")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_exiftool = bin_dir / "exiftool"
        fake_exiftool.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' '[{\"Comment\":\"Private Person Fixture\"}]'\n",
            encoding="utf-8",
        )
        fake_exiftool.chmod(0o755)
        fake_tesseract = bin_dir / "tesseract"
        fake_tesseract.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--list-langs\" ]; then printf 'eng\\nfra\\n'; exit 0; fi\n"
            "printf '%s\\n' 'Private Person Fixture'\n",
            encoding="utf-8",
        )
        fake_tesseract.chmod(0o755)

        result = self.run_scan(
            extra_env={
                "EXIFTOOL_BIN": str(fake_exiftool),
                "TESSERACT_BIN": str(fake_tesseract),
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("image_metadata", result.stdout)
        self.assertIn("image_ocr", result.stdout)
        self.assertNotIn("Private Person Fixture", result.stdout)


if __name__ == "__main__":
    unittest.main()
