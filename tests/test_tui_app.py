"""Small deterministic smoke tests for the full-screen terminal client."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))

from textual.widgets import TextArea  # noqa: E402

from tui.app import CortexTui  # noqa: E402


class _TuiFixtureClient:
    base_url = "http://127.0.0.1:18420"

    def __init__(self, *, fail_send: bool = False):
        self.requests = []
        self.fail_send = fail_send

    def request(self, method, path, *, body=None, query=None):
        self.requests.append((method, path, body, query))
        if path == "/api/status":
            return {"executor_available": True}
        if path == "/api/pipeline/status":
            return {"components": [{"id": "transport", "state": "ready"}]}
        if path == "/api/conversations":
            return [{"title": "Fixture chat", "url": "https://chatgpt.com/c/fixture"}]
        if path == "/api/models/chatgpt":
            return {"models": [{"label": "GPT fixture"}]}
        if path == "/api/chat/send":
            if self.fail_send:
                raise OSError("fixture send failure")
            return {"state": "QUEUED", "canonical_url": "https://chatgpt.com/c/new"}
        raise AssertionError(f"unexpected fixture request: {method} {path}")


class TuiSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_small_terminal_keeps_composer_and_safe_status(self):
        app = CortexTui(offline=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            composer = app.query_one("#composer", TextArea)
            self.assertGreater(composer.region.height, 0)
            self.assertLessEqual(composer.region.bottom, 24)
            composer.focus()
            await pilot.press("h", "i")
            self.assertEqual(composer.text, "hi")
            self.assertIn("Exécuteur", app.query_one("#executor-status").render().plain)

    async def test_escape_does_not_submit_or_clear_draft(self):
        app = CortexTui(offline=True)
        async with app.run_test(size=(120, 35)) as pilot:
            composer = app.query_one("#composer", TextArea)
            composer.focus()
            await pilot.press("d", "r", "a", "f", "t")
            await pilot.press("escape")
            self.assertEqual(composer.text, "draft")
            self.assertIn(app.state.delivery, {"Prêt", "Exécuteur vérifié sélectionné"})

    async def test_new_conversation_clears_transcript_without_network(self):
        app = CortexTui(offline=True)
        app.state.messages = [{"role": "assistant", "text": "ancienne réponse"}]
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            app.action_new_conversation()
            self.assertEqual(app.state.messages, [])
            self.assertIn("Aucun message", app.query_one("#transcript-text").render().plain)

    async def test_untrusted_transcript_text_is_not_interpreted_as_markup(self):
        app = CortexTui(offline=True)
        app.state.messages = [{"role": "assistant", "text": "[bold]literal[/bold]"}]
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            app._render()
            rendered = app.query_one("#transcript-text").render().plain
            self.assertIn("[bold]literal[/bold]", rendered)

    async def test_live_client_fixture_loads_status_and_confirms_send(self):
        client = _TuiFixtureClient()
        app = CortexTui(client, offline=False, start_backend=lambda: None)
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause(delay=0.2)
            self.assertEqual(app.state.connection, "ready")
            self.assertEqual(app.state.planner_label, "GPT fixture")
            self.assertEqual(len(app.state.conversations), 1)
            self.assertEqual(len(app.query_one("#conversation-list").children), 1)
            composer = app.query_one("#composer", TextArea)
            composer.focus()
            await pilot.press("o", "k")
            app._submit_text()
            await pilot.pause(delay=0.2)
            self.assertTrue(any(path == "/api/chat/send" for _, path, _, _ in client.requests))
            self.assertIn("Envoi confirmé", app.state.delivery)
            self.assertEqual(composer.text, "")

    async def test_failed_send_keeps_draft_and_reports_uncertainty(self):
        client = _TuiFixtureClient(fail_send=True)
        app = CortexTui(client, offline=False, start_backend=lambda: None)
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause(delay=0.1)
            composer = app.query_one("#composer", TextArea)
            composer.focus()
            await pilot.press("x")
            app._submit_text()
            await pilot.pause(delay=0.2)
            self.assertEqual(composer.text, "x")
            self.assertIn("Envoi non confirmé", app.state.delivery)


if __name__ == "__main__":
    unittest.main()
