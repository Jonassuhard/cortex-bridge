"""Explicit approval boundary for ChatGPT-requested context items."""

from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import chat as chat_api  # noqa: E402


class ContextApprovalEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()
        (self.workspace / "notes.txt").write_text("bounded context", encoding="utf-8")
        self.saved_attachment = chat_api.send_with_attachment
        self.saved_chat = chat_api.send_chat
        self.saved_screenshot = chat_api.send_screenshot
        self.saved_settings_path = chat_api.RUNTIME_PATHS.settings
        self.seen: dict[str, object] = {}
        chat_api._observed_context_registry.clear()
        chat_api._context_approval_registry.clear()
        settings_path = self.workspace / "settings.json"
        settings_path.write_text(
            __import__("json").dumps({"default_workspace": str(self.workspace)}),
            encoding="utf-8",
        )
        chat_api.RUNTIME_PATHS = chat_api.RUNTIME_PATHS.__class__(
            **{**chat_api.RUNTIME_PATHS.__dict__, "settings": settings_path}
        )

    async def asyncTearDown(self) -> None:
        chat_api.send_with_attachment = self.saved_attachment
        chat_api.send_chat = self.saved_chat
        chat_api.send_screenshot = self.saved_screenshot
        chat_api.RUNTIME_PATHS = chat_api.RUNTIME_PATHS.__class__(
            **{**chat_api.RUNTIME_PATHS.__dict__, "settings": self.saved_settings_path}
        )
        chat_api._observed_context_registry.clear()
        chat_api._context_approval_registry.clear()
        self.tmp.cleanup()

    def observe(self, url: str, request_id: str, item: dict) -> None:
        chat_api._register_observed_context_requests(
            url,
            [{
                "id": "assistant-context",
                "role": "assistant",
                "text": "",
                "code_blocks": [{
                    "lang": "cortex-context-request",
                    "text": __import__("json").dumps({
                        "protocol": "cortex-context-request.v1",
                        "requestId": request_id,
                        "summary": "Contexte requis",
                        "items": [item],
                    }),
                }],
            }],
        )

    async def test_file_requires_explicit_call_and_stays_inside_workspace(self) -> None:
        async def fake_attachment(body):
            self.seen["attachment"] = body
            return {"id": "run-file"}

        chat_api.send_with_attachment = fake_attachment
        self.observe("https://chatgpt.com/c/demo", "ctx-file-1", {
            "id": "file-1", "kind": "file", "reason": "Lire les notes", "path": "notes.txt",
        })
        result = await chat_api.approve_context(chat_api.ContextApprovalIn(
            conversation_url="https://chatgpt.com/c/demo",
            workspace=str(self.workspace),
            request_id="ctx-file-1",
            item_id="file-1",
            item=chat_api.ContextApprovalItemIn(
                id="file-1", kind="file", reason="Lire les notes", path="notes.txt"
            ),
        ))
        self.assertEqual(result, {
            "id": "run-file",
            "context_request_id": "ctx-file-1",
            "context_item_id": "file-1",
            "idempotent": False,
        })
        body = self.seen["attachment"]
        self.assertEqual(Path(body.path), (self.workspace / "notes.txt").resolve())
        self.assertIn("Lire les notes", body.text)

    async def test_file_traversal_and_missing_workspace_are_refused(self) -> None:
        for workspace, path in [
            (str(self.workspace), "../outside.txt"),
            (str(self.workspace), str(self.workspace / "notes.txt")),
            (str(Path(self.tmp.name) / "missing"), "notes.txt"),
        ]:
            with self.subTest(workspace=workspace, path=path):
                with self.assertRaises(HTTPException) as raised:
                    await chat_api.approve_context(chat_api.ContextApprovalIn(
                        conversation_url="https://chatgpt.com/c/demo",
                        workspace=workspace,
                        request_id="ctx-file-1",
                        item_id="file-1",
                        item=chat_api.ContextApprovalItemIn(
                            id="file-1", kind="file", reason="Lire", path=path
                        ),
                    ))
                self.assertEqual(raised.exception.status_code, 422)

    async def test_link_is_sent_only_after_approval_and_only_over_http(self) -> None:
        async def fake_chat(body):
            self.seen["chat"] = body
            return {"id": "run-link"}

        chat_api.send_chat = fake_chat
        self.observe("https://chatgpt.com/c/demo", "ctx-link-1", {
            "id": "link-1", "kind": "link", "reason": "Lire la doc", "url": "https://example.com/docs",
        })
        result = await chat_api.approve_context(chat_api.ContextApprovalIn(
            conversation_url="https://chatgpt.com/c/demo",
            workspace=str(self.workspace),
            request_id="ctx-link-1",
            item_id="link-1",
            item=chat_api.ContextApprovalItemIn(
                id="link-1", kind="link", reason="Lire la doc", url="https://example.com/docs"
            ),
        ))
        self.assertEqual(result, {
            "id": "run-link",
            "context_request_id": "ctx-link-1",
            "context_item_id": "link-1",
            "idempotent": False,
        })
        self.assertIn("https://example.com/docs", self.seen["chat"].text)

        with self.assertRaises(HTTPException) as raised:
            await chat_api.approve_context(chat_api.ContextApprovalIn(
                conversation_url="https://chatgpt.com/c/demo",
                workspace=str(self.workspace),
                request_id="ctx-link-2",
                item_id="link-2",
                item=chat_api.ContextApprovalItemIn(
                    id="link-2", kind="link", reason="Lire", url="file:///tmp/secret"
                ),
            ))
        self.assertEqual(raised.exception.status_code, 422)

    async def test_screenshot_target_is_bounded(self) -> None:
        async def fake_screenshot(body):
            self.seen["screenshot"] = body
            return {"id": "run-shot"}

        chat_api.send_screenshot = fake_screenshot
        self.observe("https://chatgpt.com/c/demo", "ctx-shot-1", {
            "id": "shot-1", "kind": "screenshot", "reason": "Comparer", "target": "current_chatgpt",
        })
        result = await chat_api.approve_context(chat_api.ContextApprovalIn(
            conversation_url="https://chatgpt.com/c/demo",
            workspace=str(self.workspace),
            request_id="ctx-shot-1",
            item_id="shot-1",
            item=chat_api.ContextApprovalItemIn(
                id="shot-1", kind="screenshot", reason="Comparer", target="current_chatgpt"
            ),
        ))
        self.assertEqual(result, {
            "id": "run-shot",
            "context_request_id": "ctx-shot-1",
            "context_item_id": "shot-1",
            "idempotent": False,
        })

        with self.assertRaises(HTTPException) as raised:
            await chat_api.approve_context(chat_api.ContextApprovalIn(
                conversation_url="https://chatgpt.com/c/demo",
                workspace=str(self.workspace),
                request_id="ctx-shot-2",
                item_id="shot-2",
                item=chat_api.ContextApprovalItemIn(
                    id="shot-2", kind="screenshot", reason="Capturer", target="arbitrary_window"
                ),
            ))
        self.assertEqual(raised.exception.status_code, 422)

    async def test_duplicate_identity_returns_original_run_without_second_transport_call(self) -> None:
        calls = 0

        async def fake_attachment(body):
            nonlocal calls
            calls += 1
            return {"id": "run-once"}

        chat_api.send_with_attachment = fake_attachment
        self.observe("https://chatgpt.com/c/demo", "ctx-duplicate-1", {
            "id": "file-1", "kind": "file", "reason": "Lire les notes", "path": "notes.txt",
        })
        request = chat_api.ContextApprovalIn(
            conversation_url="https://chatgpt.com/c/demo",
            workspace=str(self.workspace),
            request_id="ctx-duplicate-1",
            item_id="file-1",
            item=chat_api.ContextApprovalItemIn(
                id="file-1", kind="file", reason="Lire les notes", path="notes.txt"
            ),
        )
        first = await chat_api.approve_context(request)
        second = await chat_api.approve_context(request)
        self.assertEqual(calls, 1)
        self.assertEqual(first["id"], "run-once")
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["context_request_id"], "ctx-duplicate-1")

    async def test_identity_must_match_item_and_use_bounded_token_format(self) -> None:
        for request_id, item_id, item_value in [
            ("ctx mismatch", "file-1", "file-1"),
            ("ctx-valid", "wrong-item", "file-1"),
            ("ctx-valid", "file-1", "different-item"),
        ]:
            with self.subTest(request_id=request_id, item_id=item_id, item_value=item_value):
                with self.assertRaises(HTTPException) as raised:
                    await chat_api.approve_context(chat_api.ContextApprovalIn(
                        conversation_url="https://chatgpt.com/c/demo",
                        workspace=str(self.workspace),
                        request_id=request_id,
                        item_id=item_id,
                        item=chat_api.ContextApprovalItemIn(
                            id=item_value,
                            kind="file",
                            reason="Lire",
                            path="notes.txt",
                        ),
                    ))
                self.assertEqual(raised.exception.status_code, 422)

    async def test_unobserved_request_and_wrong_workspace_are_refused(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await chat_api.approve_context(chat_api.ContextApprovalIn(
                conversation_url="https://chatgpt.com/c/demo",
                workspace=str(self.workspace),
                request_id="forged-request",
                item_id="file-1",
                item=chat_api.ContextApprovalItemIn(
                    id="file-1", kind="file", reason="Lire", path="notes.txt",
                ),
            ))
        self.assertEqual(raised.exception.status_code, 409)

    async def test_observation_ignores_user_messages_and_normalizes_trailing_slash(self) -> None:
        chat_api._register_observed_context_requests(
            "https://chatgpt.com/c/demo/",
            [{
                "id": "user-context",
                "role": "user",
                "text": "```cortex-context-request\n{}\n```",
            }, {
                "id": "assistant-context",
                "role": "assistant",
                "text": "```cortex-context-request\n"
                        "{\"protocol\":\"cortex-context-request.v1\","
                        "\"requestId\":\"ctx-slash-1\",\"summary\":\"Lire\","
                        "\"items\":[{\"id\":\"file-1\",\"kind\":\"file\","
                        "\"reason\":\"Lire\",\"path\":\"notes.txt\"}]}\n```",
            }],
        )
        self.assertIn(
            ("https://chatgpt.com/c/demo", "ctx-slash-1", "file-1"),
            chat_api._observed_context_registry,
        )
        self.assertNotIn(
            ("https://chatgpt.com/c/demo", "", ""),
            chat_api._observed_context_registry,
        )

        self.observe("https://chatgpt.com/c/demo", "ctx-workspace-1", {
            "id": "file-1", "kind": "file", "reason": "Lire", "path": "notes.txt",
        })
        other_workspace = Path(self.tmp.name) / "other"
        other_workspace.mkdir()
        (other_workspace / "notes.txt").write_text("not authorized", encoding="utf-8")
        with self.assertRaises(HTTPException) as raised:
            await chat_api.approve_context(chat_api.ContextApprovalIn(
                conversation_url="https://chatgpt.com/c/demo",
                workspace=str(other_workspace),
                request_id="ctx-workspace-1",
                item_id="file-1",
                item=chat_api.ContextApprovalItemIn(
                    id="file-1", kind="file", reason="Lire", path="notes.txt",
                ),
            ))
        self.assertEqual(raised.exception.status_code, 409)

    def test_context_item_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            chat_api.ContextApprovalItemIn(
                id="file-1",
                kind="file",
                reason="Lire",
                path="notes.txt",
                unexpected="ignored-before-hardening",
            )
