"""Security boundaries for attachments and screenshots (local fixtures only)."""

from __future__ import annotations

import base64
import asyncio
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

import attachments  # noqa: E402
from transport.chatgpt_web.adapter import MAX_FILE_BYTES, MAX_IMAGE_BYTES  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"png-data"
PDF = b"%PDF-1.7\nbody"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _office_bytes(member: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(member, "<document/>")
    return output.getvalue()


class AttachmentBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.original_dir = attachments.ATTACHMENTS_DIR
        attachments.ATTACHMENTS_DIR = Path(self.tempdir.name) / "attachments"
        self.addCleanup(setattr, attachments, "ATTACHMENTS_DIR", self.original_dir)
        if hasattr(attachments, "_TOKENS"):
            attachments._TOKENS.clear()

    def test_explicit_supported_mime_table(self):
        cases = {
            "image.png": (PNG, "image/png"),
            "image.jpg": (b"\xff\xd8\xffpayload", "image/jpeg"),
            "image.gif": (b"GIF89apayload", "image/gif"),
            "image.webp": (b"RIFF\x04\x00\x00\x00WEBP", "image/webp"),
            "paper.pdf": (PDF, "application/pdf"),
            "notes.txt": (b"plain utf-8", "text/plain"),
            "data.json": (b'{"ok": true}', "application/json"),
            "table.csv": (b"a,b\n1,2\n", "text/csv"),
            "readme.md": (b"# Heading\n", "text/markdown"),
            "doc.docx": (_office_bytes("word/document.xml"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "book.xlsx": (_office_bytes("xl/workbook.xml"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "deck.pptx": (_office_bytes("ppt/presentation.xml"), "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        }
        for name, (payload, expected) in cases.items():
            with self.subTest(name=name):
                descriptor = attachments.store_upload(name, _b64(payload))
                self.assertEqual(descriptor["mime"], expected)

    def test_office_extension_requires_matching_internal_zip_member(self):
        with self.assertRaises(ValueError):
            attachments.store_upload(
                "forged.docx", _b64(_office_bytes("xl/workbook.xml"))
            )

    def test_extension_content_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            attachments.store_upload("renamed.png", _b64(PDF))

    def test_filename_and_symlink_are_rejected_before_read(self):
        descriptor = attachments.store_upload("..\\..\\safe\\note.txt", _b64(b"ok"))
        self.assertEqual(descriptor["name"], "note.txt")
        real = Path(self.tempdir.name) / "real.txt"
        real.write_text("secret", encoding="utf-8")
        link = Path(self.tempdir.name) / "link.txt"
        link.symlink_to(real)
        with self.assertRaises(ValueError):
            attachments.describe_path(str(link))

    def test_sparse_size_boundaries_do_not_allocate_payloads(self):
        exact = Path(self.tempdir.name) / "exact.pdf"
        with exact.open("wb") as handle:
            handle.write(PDF)
            handle.truncate(MAX_FILE_BYTES)
        self.assertEqual(
            attachments.describe_path(str(exact))["size_bytes"], MAX_FILE_BYTES
        )
        over = Path(self.tempdir.name) / "over.pdf"
        with over.open("wb") as handle:
            handle.write(PDF)
            handle.truncate(MAX_FILE_BYTES + 1)
        with self.assertRaises(ValueError):
            attachments.describe_path(str(over))

        image_over = Path(self.tempdir.name) / "over.png"
        with image_over.open("wb") as handle:
            handle.write(PNG)
            handle.truncate(MAX_IMAGE_BYTES + 1)
        with self.assertRaises(ValueError):
            attachments.describe_path(str(image_over))

    def test_descriptor_contains_opaque_token_owner_mime_kind_and_size(self):
        descriptor = attachments.store_upload("paper.pdf", _b64(PDF))
        self.assertEqual(descriptor["owner"], "cortex-bridge")
        self.assertEqual(descriptor["mime"], "application/pdf")
        self.assertEqual(descriptor["kind"], "file")
        self.assertEqual(descriptor["size_bytes"], len(PDF))
        self.assertNotIn("/", descriptor["token"])
        self.assertNotIn(str(attachments.ATTACHMENTS_DIR), descriptor["token"])
        self.assertIsNotNone(attachments.resolve_token(descriptor["token"]))
        attachments._TOKENS[descriptor["token"]]["expires_at"] = time.time() - 1
        self.assertIsNone(attachments.resolve_token(descriptor["token"]))

    def test_cleanup_preserves_references_and_ignores_non_cortex_files(self):
        keep = attachments.store_upload("keep.pdf", _b64(PDF))
        drop = attachments.store_upload("drop.pdf", _b64(PDF))
        foreign = attachments.ATTACHMENTS_DIR / "family-photo.png"
        foreign.write_bytes(PNG)
        deleted = attachments.cleanup_abandoned({keep["path"]})
        self.assertEqual(deleted, [drop["path"]])
        self.assertTrue(Path(keep["path"]).exists())
        self.assertTrue(foreign.exists())

    def test_screenshot_requires_expected_regular_png_and_cleans_invalid_file(self):
        wrong = attachments.ATTACHMENTS_DIR / "cortex-screenshot-wrong.png"
        wrong.parent.mkdir(parents=True, exist_ok=True)
        wrong.write_bytes(PNG)
        expected = attachments.ATTACHMENTS_DIR / "cortex-screenshot-expected.png"
        with self.assertRaises(ValueError):
            attachments.describe_screenshot(str(wrong), expected_path=str(expected))
        self.assertFalse(wrong.exists())

        invalid = attachments.ATTACHMENTS_DIR / "cortex-screenshot-invalid.png"
        invalid.write_bytes(b"not-png")
        with self.assertRaises(ValueError):
            attachments.describe_screenshot(str(invalid), expected_path=str(invalid))
        self.assertFalse(invalid.exists())

        valid = attachments.ATTACHMENTS_DIR / "cortex-screenshot-valid.png"
        valid.write_bytes(PNG)
        descriptor = attachments.describe_screenshot(
            str(valid), expected_path=str(valid)
        )
        self.assertEqual(descriptor["mime"], "image/png")


class ChatAttachmentIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import chat

        self.chat = chat
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.original_dir = attachments.ATTACHMENTS_DIR
        attachments.ATTACHMENTS_DIR = Path(self.tempdir.name) / "attachments"
        self.addCleanup(setattr, attachments, "ATTACHMENTS_DIR", self.original_dir)
        attachments._TOKENS.clear()

    async def test_chat_run_persists_complete_attachment_descriptor(self):
        run = self.chat.ChatRunRuntime(
            id="run-1",
            conversation_url="https://chatgpt.com/c/conv-1",
            text="",
            new_conversation=False,
            attachment_path="/tmp/staged.pdf",
            attachment_name="staged.pdf",
            attachment_token="opaque",
            attachment_owner="cortex-bridge",
            attachment_mime="application/pdf",
            attachment_kind="file",
            attachment_size_bytes=123,
        )
        persisted = run.persisted()
        self.assertEqual(persisted["attachment_token"], "opaque")
        self.assertEqual(persisted["attachment_owner"], "cortex-bridge")
        self.assertEqual(persisted["attachment_mime"], "application/pdf")
        self.assertEqual(persisted["attachment_kind"], "file")
        self.assertEqual(persisted["attachment_size_bytes"], 123)

    async def test_raw_endpoint_returns_404_for_unknown_and_file_for_known_token(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as missing:
            await self.chat.attachment_raw("unknown-token")
        self.assertEqual(missing.exception.status_code, 404)

        descriptor = attachments.store_upload("paper.pdf", _b64(PDF))
        response = await self.chat.attachment_raw(descriptor["token"])
        self.assertEqual(Path(response.path).resolve(), Path(descriptor["path"]).resolve())
        self.assertEqual(response.headers["access-control-allow-origin"], "https://chatgpt.com")

    async def test_screenshot_selects_requested_target_and_uses_driver_result(self):
        calls = []

        class Driver:
            async def take_screenshot(self, target):
                calls.append(("screenshot", target))
                Path(target).write_bytes(PNG)
                return {"path": target, "driver": "fixture"}

        class Transport:
            driver = Driver()

            async def select_conversation(self, url):
                calls.append(("select", url))

        async def start_run(**kwargs):
            calls.append(("start", kwargs))
            return kwargs

        body = self.chat.ChatScreenshotIn(
            conversation_url="https://chatgpt.com/c/conv-1",
            text="capture",
        )
        with (
            patch.object(self.chat.missions_api, "_global_stop", False),
            patch.object(self.chat.missions_api, "optin_accepted", return_value=True),
            patch.object(self.chat, "_make_transport", return_value=Transport()),
            patch.object(self.chat, "_start_attachment_run", side_effect=start_run),
        ):
            result = await self.chat.send_screenshot(body)
        self.assertEqual(calls[0], ("select", body.conversation_url))
        self.assertEqual(calls[1][0], "screenshot")
        self.assertEqual(result["mime"], "image/png")
        self.assertTrue(result["token"])

    async def test_screenshot_rejects_wrong_driver_path_and_cleans_it(self):
        wrong = attachments.ATTACHMENTS_DIR / "cortex-screenshot-wrong.png"

        class Driver:
            async def take_screenshot(self, _target):
                wrong.parent.mkdir(parents=True, exist_ok=True)
                wrong.write_bytes(PNG)
                return {"path": str(wrong), "driver": "fixture"}

        class Transport:
            driver = Driver()

            async def select_conversation(self, _url):
                return None

        body = self.chat.ChatScreenshotIn(
            conversation_url="https://chatgpt.com/c/conv-1"
        )
        with (
            patch.object(self.chat.missions_api, "_global_stop", False),
            patch.object(self.chat.missions_api, "optin_accepted", return_value=True),
            patch.object(self.chat, "_make_transport", return_value=Transport()),
        ):
            with self.assertRaises(Exception) as raised:
                await self.chat.send_screenshot(body)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertFalse(wrong.exists())

    async def test_screenshot_transport_failure_cleans_partial_expected_file(self):
        class Driver:
            async def take_screenshot(self, target):
                Path(target).write_bytes(b"partial")
                raise RuntimeError("driver failed")

        class Transport:
            driver = Driver()

            async def select_conversation(self, _url):
                return None

        body = self.chat.ChatScreenshotIn(
            conversation_url="https://chatgpt.com/c/conv-1"
        )
        with (
            patch.object(self.chat.missions_api, "_global_stop", False),
            patch.object(self.chat.missions_api, "optin_accepted", return_value=True),
            patch.object(self.chat, "_make_transport", return_value=Transport()),
        ):
            with self.assertRaises(Exception):
                await self.chat.send_screenshot(body)
        leftovers = list(attachments.ATTACHMENTS_DIR.glob("cortex-screenshot-*"))
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
