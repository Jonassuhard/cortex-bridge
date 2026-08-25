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

    def test_resolving_an_expired_token_deletes_its_unreferenced_managed_file(self):
        descriptor = attachments.store_upload("expired.txt", _b64(b"expired\n"))
        managed_file = Path(descriptor["path"])
        attachments._TOKENS[descriptor["token"]]["expires_at"] = time.time() - 1

        resolved = attachments.resolve_token(descriptor["token"])

        self.assertIsNone(resolved)
        self.assertFalse(managed_file.exists())
        self.assertNotIn(descriptor["token"], attachments._TOKENS)

    def test_new_staging_sweeps_an_expired_unreferenced_managed_file(self):
        expired = attachments.store_upload("expired.txt", _b64(b"expired\n"))
        expired_file = Path(expired["path"])
        attachments._TOKENS[expired["token"]]["expires_at"] = time.time() - 1

        current = attachments.store_upload("current.txt", _b64(b"current\n"))

        self.assertFalse(expired_file.exists())
        self.assertNotIn(expired["token"], attachments._TOKENS)
        self.assertTrue(Path(current["path"]).exists())
        self.assertIsNotNone(attachments.resolve_token(current["token"]))

    def test_expiring_one_token_keeps_a_file_referenced_by_a_live_token(self):
        expired = attachments.store_upload("shared.txt", _b64(b"shared\n"))
        live = attachments.stage_path(expired["path"])
        attachments._TOKENS[expired["token"]]["expires_at"] = time.time() - 1

        resolved = attachments.resolve_token(expired["token"])

        self.assertIsNone(resolved)
        self.assertTrue(Path(expired["path"]).exists())
        self.assertNotIn(expired["token"], attachments._TOKENS)
        self.assertIsNotNone(attachments.resolve_token(live["token"]))

    def test_stage_path_copies_a_valid_external_file_into_managed_storage(self):
        source = Path(self.tempdir.name) / "selected-by-user.txt"
        source.write_bytes(b"synthetic attachment\n")

        descriptor = attachments.stage_path(str(source))
        staged = Path(descriptor["path"])

        self.assertEqual(staged.parent.resolve(), attachments.ATTACHMENTS_DIR.resolve())
        self.assertNotEqual(staged.resolve(), source.resolve())
        self.assertEqual(staged.read_bytes(), source.read_bytes())
        self.assertEqual(source.read_bytes(), b"synthetic attachment\n")

    def test_stage_path_reuses_an_already_managed_upload(self):
        uploaded = attachments.store_upload("already-managed.txt", _b64(b"managed\n"))

        staged = attachments.stage_path(uploaded["path"])

        self.assertEqual(Path(staged["path"]).resolve(), Path(uploaded["path"]).resolve())

    def test_stage_path_preserves_a_managed_file_when_its_old_token_expired(self):
        uploaded = attachments.store_upload("expired-managed.txt", _b64(b"managed\n"))
        managed_file = Path(uploaded["path"])
        attachments._TOKENS[uploaded["token"]]["expires_at"] = time.time() - 1

        staged = attachments.stage_path(uploaded["path"])

        self.assertTrue(managed_file.exists())
        self.assertNotIn(uploaded["token"], attachments._TOKENS)
        self.assertIsNotNone(attachments.resolve_token(staged["token"]))

    def test_cleanup_preserves_references_and_ignores_non_cortex_files(self):
        keep = attachments.store_upload("keep.pdf", _b64(PDF))
        drop = attachments.store_upload("drop.pdf", _b64(PDF))
        foreign = attachments.ATTACHMENTS_DIR / "family-photo.png"
        foreign.write_bytes(PNG)
        deleted = attachments.cleanup_abandoned({keep["path"]})
        self.assertEqual(deleted, [drop["path"]])
        self.assertTrue(Path(keep["path"]).exists())
        self.assertTrue(foreign.exists())

    def test_release_owned_keeps_a_shared_file_until_its_last_token(self):
        uploaded = attachments.store_upload("terminal.txt", _b64(b"terminal\n"))
        duplicate = attachments.stage_path(uploaded["path"])

        released = attachments.release_owned(
            uploaded["path"],
            token=uploaded["token"],
        )

        self.assertTrue(released)
        self.assertTrue(Path(uploaded["path"]).exists())
        self.assertIsNone(attachments.resolve_token(uploaded["token"]))
        self.assertIsNotNone(attachments.resolve_token(duplicate["token"]))

        released_last = attachments.release_owned(
            duplicate["path"],
            token=duplicate["token"],
        )

        self.assertTrue(released_last)
        self.assertFalse(Path(uploaded["path"]).exists())
        self.assertIsNone(attachments.resolve_token(duplicate["token"]))

    def test_release_owned_never_deletes_an_external_or_foreign_file(self):
        external = Path(self.tempdir.name) / "external.txt"
        external.write_text("keep", encoding="utf-8")
        foreign = attachments.ATTACHMENTS_DIR / "family-photo.png"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_bytes(PNG)

        self.assertFalse(attachments.release_owned(str(external)))
        self.assertFalse(attachments.release_owned(str(foreign)))
        self.assertTrue(external.exists())
        self.assertTrue(foreign.exists())

    def test_release_owned_keeps_the_last_token_when_unlink_fails(self):
        uploaded = attachments.store_upload("busy.txt", _b64(b"busy\n"))

        with patch.object(Path, "unlink", side_effect=OSError("busy")):
            released = attachments.release_owned(
                uploaded["path"],
                token=uploaded["token"],
            )

        self.assertFalse(released)
        self.assertIsNotNone(attachments.resolve_token(uploaded["token"]))
        self.assertTrue(Path(uploaded["path"]).exists())

    def test_release_owned_refuses_a_symlinked_attachment_root(self):
        real_root = Path(self.tempdir.name) / "real-attachments"
        real_root.mkdir()
        attachments.ATTACHMENTS_DIR.symlink_to(real_root, target_is_directory=True)
        target = real_root / "cortex-attachment-outside.txt"
        target.write_text("keep", encoding="utf-8")

        released = attachments.release_owned(str(target))

        self.assertFalse(released)
        self.assertTrue(target.exists())

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

    async def test_terminal_failed_run_releases_its_managed_attachment(self):
        descriptor = attachments.store_upload("failed.txt", _b64(b"failed\n"))
        retained = attachments.stage_path(descriptor["path"])

        class Lease:
            async def release(self):
                return None

        class Transport:
            lock = None

            async def select_conversation(self, _url):
                return None

            async def send_with_attachment(self, *_args, **_kwargs):
                raise self_chat.TransportError("ATTACHMENT_FAILED", "synthetic failure")

            async def close(self):
                return None

        self_chat = self.chat
        run = self.chat.ChatRunRuntime(
            id="failed-attachment-run",
            conversation_url="https://chatgpt.com/c/conv-1",
            text="synthetic",
            new_conversation=False,
            attachment_path=descriptor["path"],
            attachment_name=descriptor["name"],
            attachment_token=descriptor["token"],
            attachment_owner=descriptor["owner"],
            attachment_mime=descriptor["mime"],
            attachment_kind=descriptor["kind"],
            attachment_size_bytes=descriptor["size_bytes"],
            conversation_key="https://chatgpt.com/c/conv-1",
            session_id="attachment-cleanup",
            lease=Lease(),
        )

        with (
            patch.object(self.chat, "_make_transport", return_value=Transport()),
            patch.object(self.chat, "_persist_runs"),
        ):
            await self.chat._run_chat(run)

        self.assertEqual(run.state, "FAILED")
        self.assertTrue(Path(descriptor["path"]).exists())
        self.assertIsNone(attachments.resolve_token(descriptor["token"]))
        self.assertIsNotNone(attachments.resolve_token(retained["token"]))

    async def test_attachment_cleanup_failure_never_blocks_lease_release(self):
        class Lease:
            released = False

            async def release(self):
                self.released = True

        class Transport:
            lock = None

            async def select_conversation(self, _url):
                return None

            async def send_with_attachment(self, *_args, **_kwargs):
                raise self_chat.TransportError("ATTACHMENT_FAILED", "synthetic failure")

            async def close(self):
                return None

        self_chat = self.chat
        lease = Lease()
        run = self.chat.ChatRunRuntime(
            id="cleanup-error-run",
            conversation_url="https://chatgpt.com/c/conv-1",
            text="synthetic",
            new_conversation=False,
            attachment_path="/managed/cortex-attachment-proof.txt",
            conversation_key="https://chatgpt.com/c/conv-1",
            session_id="attachment-cleanup-error",
            lease=lease,
        )

        with (
            patch.object(self.chat, "_make_transport", return_value=Transport()),
            patch.object(self.chat.attachments, "release_owned", side_effect=OSError("busy")),
            patch.object(self.chat, "_persist_runs") as persist,
        ):
            await self.chat._run_chat(run)

        self.assertTrue(lease.released)
        self.assertTrue(persist.called)

    async def test_rejected_path_run_preserves_the_callers_staged_file(self):
        descriptor = attachments.store_upload("capacity.txt", _b64(b"capacity\n"))
        body = self.chat.ChatSendAttachmentIn(
            conversation_url="https://chatgpt.com/c/conv-1",
            text="synthetic",
            path=descriptor["path"],
            name=descriptor["name"],
        )

        with (
            patch.object(self.chat.missions_api, "_global_stop", False),
            patch.object(self.chat.missions_api, "optin_accepted", return_value=True),
            patch.object(
                self.chat,
                "_start_attachment_run",
                side_effect=self.chat.HTTPException(status_code=409, detail="capacity"),
            ),
        ):
            with self.assertRaises(self.chat.HTTPException):
                await self.chat.send_with_attachment(body)

        self.assertTrue(Path(descriptor["path"]).exists())
        self.assertIsNotNone(attachments.resolve_token(descriptor["token"]))

    async def test_atomic_upload_rejection_leaves_no_staged_file(self):
        body = self.chat.ChatSendAttachmentIn(
            conversation_url="https://chatgpt.com/c/conv-1",
            text="synthetic",
            name="atomic.txt",
            data_b64=_b64(b"atomic\n"),
        )

        with (
            patch.object(self.chat.missions_api, "_global_stop", False),
            patch.object(self.chat.missions_api, "optin_accepted", return_value=True),
            patch.object(
                self.chat,
                "_start_attachment_run",
                side_effect=self.chat.HTTPException(status_code=409, detail="capacity"),
            ),
        ):
            with self.assertRaises(self.chat.HTTPException):
                await self.chat.send_with_attachment(body)

        self.assertEqual(list(attachments.ATTACHMENTS_DIR.glob("*")), [])

    async def test_transport_capabilities_never_exceed_backend_intake_limits(self):
        class Driver:
            def capabilities(self):
                return {
                    "send_text": True,
                    "upload_file": True,
                    "upload_image": True,
                    "take_screenshot": True,
                    "limits": {
                        "file_bytes": 25 * 1024 * 1024,
                        "image_bytes": 25 * 1024 * 1024,
                    },
                }

        class Transport:
            driver = Driver()

        with patch.object(self.chat, "_make_transport", return_value=Transport()):
            result = await self.chat.transport_capabilities()

        self.assertEqual(result["limits"]["file_bytes"], 25 * 1024 * 1024)
        self.assertEqual(result["limits"]["image_bytes"], MAX_IMAGE_BYTES)

    async def test_attachment_run_registration_failure_releases_its_writer_slot(self):
        class Lease:
            session_id = "registration-failure"
            released = False

            async def release(self):
                self.released = True

        lease = Lease()
        existing_runs = set(self.chat._runs)
        with (
            patch.object(self.chat.missions_api, "get_store"),
            patch.object(self.chat.write_slots, "acquire_writer", return_value=lease),
            patch.object(self.chat, "_emit", side_effect=RuntimeError("persist failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "persist failed"):
                await self.chat._start_attachment_run(
                    url="https://chatgpt.com/c/conv-1",
                    text="synthetic",
                    path="/managed/cortex-attachment-proof.txt",
                    image=False,
                    name="proof.txt",
                    new_conversation=False,
                    token="opaque",
                )

        self.assertTrue(lease.released)
        self.assertEqual(set(self.chat._runs), existing_runs)

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

            async def close(self):
                calls.append(("close",))

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
            patch.object(self.chat, "_make_transport", return_value=Transport()) as make_transport,
            patch.object(self.chat, "_start_attachment_run", side_effect=start_run),
        ):
            result = await self.chat.send_screenshot(body)
        make_transport.assert_called_once_with(self.chat.SCREENSHOT_SESSION_ID)
        self.assertEqual(calls[0], ("select", body.conversation_url))
        self.assertEqual(calls[1][0], "screenshot")
        self.assertEqual(calls[-2], ("close",))
        self.assertEqual(calls[-1][0], "start")
        self.assertEqual(result["mime"], "image/png")
        self.assertTrue(result["token"])

    async def test_concurrent_screenshots_cannot_capture_the_other_conversation(self):
        class SharedDriver:
            current_url = ""

            async def take_screenshot(self, target):
                captured_url = self.current_url
                Path(target).write_bytes(PNG + captured_url.encode("utf-8"))
                return {"path": target, "captured_url": captured_url}

        driver = SharedDriver()

        class Transport:
            def __init__(self):
                self.driver = driver

            async def select_conversation(self, url):
                driver.current_url = url
                if url.endswith("/capture-a"):
                    # Without one read-surface operation lock, B selects the
                    # shared Chrome tab while A is between selection and pixels.
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)

            async def close(self):
                return None

        async def start_run(**kwargs):
            data = Path(kwargs["path"]).read_bytes()
            return {"captured_url": data[len(PNG):].decode("utf-8")}

        first_url = "https://chatgpt.com/c/capture-a"
        second_url = "https://chatgpt.com/c/capture-b"
        with (
            patch.object(self.chat.missions_api, "_global_stop", False),
            patch.object(self.chat.missions_api, "optin_accepted", return_value=True),
            patch.object(self.chat, "_make_transport", side_effect=lambda _session: Transport()),
            patch.object(self.chat, "_start_attachment_run", side_effect=start_run),
        ):
            first, second = await asyncio.gather(
                self.chat.send_screenshot(self.chat.ChatScreenshotIn(
                    conversation_url=first_url,
                    text="capture A",
                )),
                self.chat.send_screenshot(self.chat.ChatScreenshotIn(
                    conversation_url=second_url,
                    text="capture B",
                )),
            )

        self.assertEqual(first["captured_url"], first_url)
        self.assertEqual(second["captured_url"], second_url)

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

    async def test_screenshot_cancellation_during_close_releases_the_capture(self):
        class Driver:
            async def take_screenshot(self, target):
                Path(target).write_bytes(PNG)
                return {"path": target, "driver": "fixture"}

        class Transport:
            driver = Driver()

            async def select_conversation(self, _url):
                return None

            async def close(self):
                raise asyncio.CancelledError()

        body = self.chat.ChatScreenshotIn(
            conversation_url="https://chatgpt.com/c/conv-1"
        )
        with (
            patch.object(self.chat.missions_api, "_global_stop", False),
            patch.object(self.chat.missions_api, "optin_accepted", return_value=True),
            patch.object(self.chat, "_make_transport", return_value=Transport()),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.chat.send_screenshot(body)

        self.assertEqual(list(attachments.ATTACHMENTS_DIR.glob("*")), [])
        self.assertEqual(attachments._TOKENS, {})


if __name__ == "__main__":
    unittest.main()
