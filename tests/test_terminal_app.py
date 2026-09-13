"""Terminal controller regressions; the client double isolates only loopback I/O."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "console"))

from terminal_app import TerminalApp  # noqa: E402
from terminal_client import ApiError  # noqa: E402
from terminal_view import banner, safe_text  # noqa: E402


class RecordingClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def request(self, method, path, body=None, query=None):
        self.calls.append((method, path, body, query))
        response = self.responses.get((method, path))
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(method, path, body, query)
        return response if response is not None else {}


class TerminalViewTestCase(unittest.TestCase):
    def test_safe_text_removes_terminal_controls_from_remote_values(self):
        self.assertEqual(safe_text("ok\x1b[2J\x00\nnext"), "ok[2J\nnext")

    def test_safe_text_removes_c1_and_bidirectional_controls(self):
        self.assertEqual(safe_text("safe\x9b31m\u202e.txt\u2066"), "safe31m.txt")

    def test_banner_fits_requested_narrow_width(self):
        lines = banner(24).splitlines()
        self.assertTrue(lines)
        self.assertTrue(all(len(line) <= 24 for line in lines))

    def test_banner_uses_large_ascii_wordmark_at_normal_width_and_simple_narrow_fallback(self):
        normal = banner(72).splitlines()
        self.assertGreaterEqual(len(normal), 5)
        self.assertTrue(any("█" in line for line in normal))
        self.assertTrue(all(len(line) <= 72 for line in normal))
        self.assertEqual(banner(24), "CORTEX")


class TerminalAppTestCase(unittest.TestCase):
    def make_app(self, client, answers=()):
        output = []
        iterator = iter(answers)
        app = TerminalApp(client, input_fn=lambda _prompt: next(iterator), output=output.append)
        return app, output

    def test_welcome_keeps_prompt_usable_when_backend_is_unavailable(self):
        client = RecordingClient({("GET", "/api/status"): ApiError(None, "offline")})
        app, output = self.make_app(client, ["/quitter"])

        self.assertEqual(app.run(), 0)
        self.assertIn("indisponible", "\n".join(output).lower())

    def test_welcome_uses_actual_narrow_terminal_width_for_simple_banner(self):
        client = RecordingClient({("GET", "/api/status"): {}, ("GET", "/api/pipeline/status"): {}})
        app, output = self.make_app(client)

        with patch("terminal_app.shutil.get_terminal_size", return_value=__import__("os").terminal_size((24, 40))):
            app._welcome()

        self.assertEqual(output[0], "CORTEX")

    def test_chat_uses_one_submission_and_keeps_provisional_selection_while_queued(self):
        client = RecordingClient({
            ("POST", "/api/chat/send"): {
                "id": "run-1", "state": "QUEUED", "canonical_url": None,
            },
        })
        app, output = self.make_app(client)
        app.conversation_url = "https://chatgpt.com"
        app.new_conversation = True

        self.assertTrue(app.execute("bonjour"))
        self.assertEqual(app.conversation_url, "https://chatgpt.com")
        self.assertEqual(app.selected_run_id, "run-1")
        self.assertEqual(len(client.calls), 1)
        self.assertIn("en file", "\n".join(output).lower())

    def test_chat_uses_canonical_url_only_when_backend_supplies_one(self):
        canonical = "https://chatgpt.com/c/real-id"
        client = RecordingClient({
            ("POST", "/api/chat/send"): {
                "id": "run-2", "state": "WAITING_FOR_CHATGPT", "canonical_url": canonical,
            },
        })
        app, _ = self.make_app(client)
        app.conversation_url = "https://chatgpt.com"
        app.new_conversation = True

        self.assertTrue(app.execute("bonjour"))
        self.assertEqual(app.conversation_url, canonical)
        self.assertFalse(app.new_conversation)

    def test_history_reads_only_the_selected_canonical_conversation_snapshot(self):
        url = "https://chatgpt.com/c/alpha"
        client = RecordingClient({
            ("GET", "/api/conversations/snapshot"): {
                "messages": [
                    {"role": "user", "text": "Question visible"},
                    {"role": "assistant", "text": "Réponse\x1b[2J visible"},
                ],
            },
        })
        app, output = self.make_app(client)
        app.conversations = [{"url": url}]
        app.execute("/ouvrir 1")

        self.assertTrue(app.execute("/historique"))

        self.assertEqual(client.calls[-1], ("GET", "/api/conversations/snapshot", None, {"url": url}))
        rendered = "\n".join(output)
        self.assertIn("user: Question visible", rendered)
        self.assertIn("assistant: Réponse[2J visible", rendered)
        self.assertNotIn("\x1b", rendered)

    def test_history_refuses_to_snapshot_a_provisional_conversation(self):
        client = RecordingClient()
        app, output = self.make_app(client)

        self.assertTrue(app.execute("/historique"))

        self.assertEqual(client.calls, [])
        self.assertIn("canonique", "\n".join(output).lower())

    def test_open_rejects_non_positive_and_out_of_range_indices(self):
        client = RecordingClient()
        app, output = self.make_app(client)
        app.conversations = [{"url": "https://chatgpt.com/c/alpha"}]

        for invalid in ("0", "-1", "2", "non-entier"):
            self.assertTrue(app.execute(f"/ouvrir {invalid}"))

        self.assertTrue(app.new_conversation)
        self.assertEqual(app.conversation_url, "https://chatgpt.com")
        self.assertIn("indice de conversation invalide", "\n".join(output).lower())

    def test_uncertain_chat_submission_keeps_draft_selection_and_never_retries(self):
        client = RecordingClient({
            ("POST", "/api/chat/send"): ApiError(None, "timeout", uncertain=True),
        })
        app, output = self.make_app(client)
        app.conversation_url = "https://chatgpt.com"
        app.new_conversation = True

        self.assertTrue(app.execute("texte exact  \t"))
        self.assertEqual(app.conversation_url, "https://chatgpt.com")
        self.assertTrue(app.new_conversation)
        self.assertEqual(
            [(draft.selection_key, draft.text) for draft in app.unconfirmed_drafts.values()],
            [("provisional:0", "texte exact  \t")],
        )
        self.assertEqual(len(client.calls), 1)
        self.assertIn("aucune relance automatique", "\n".join(output).lower())

    def test_queued_draft_stays_accessible_across_conversation_switches_until_delivery(self):
        client = RecordingClient({
            ("POST", "/api/chat/send"): {"id": "run-1", "state": "QUEUED", "canonical_url": None},
        })
        app, output = self.make_app(client)
        app.conversations = [{"url": "https://chatgpt.com/c/alpha"}]
        app.execute("/ouvrir 1")

        self.assertTrue(app.execute("brouillon alpha"))
        app.conversations = [
            {"url": "https://chatgpt.com/c/beta"},
            {"url": "https://chatgpt.com/c/alpha"},
        ]
        app.execute("/ouvrir 1")
        app.execute("/ouvrir 2")
        app.execute("/brouillon")

        self.assertEqual(
            [(draft.selection_key, draft.text) for draft in app.unconfirmed_drafts.values()],
            [("conversation:https://chatgpt.com/c/alpha", "brouillon alpha")],
        )
        self.assertIn("brouillon alpha", "\n".join(output))
        self.assertEqual(len([call for call in client.calls if call[0] == "POST"]), 1)

    def test_queued_draft_survives_later_failed_run_and_clears_only_after_delivered_at(self):
        run = {"id": "run-1", "state": "QUEUED", "canonical_url": None}
        client = RecordingClient({
            ("POST", "/api/chat/send"): run,
            ("GET", "/api/chat/runs/run-1"): lambda *_args: {
                "id": "run-1", "state": "FAILED", "delivered_at": None,
            },
        })
        app, _ = self.make_app(client)

        app.execute("garder jusqu’à preuve")
        app.execute("/rafraichir")
        self.assertEqual(
            [(draft.selection_key, draft.text) for draft in app.unconfirmed_drafts.values()],
            [("provisional:0", "garder jusqu’à preuve")],
        )
        client.responses[("GET", "/api/chat/runs/run-1")] = lambda *_args: {
            "id": "run-1", "state": "WAITING_FOR_CHATGPT", "delivered_at": "2026-09-10T00:00:00Z",
        }
        app.execute("/rafraichir")
        self.assertEqual(app.unconfirmed_drafts, {})

    def test_refresh_keeps_draft_on_undelivered_failure_and_reports_response_and_error(self):
        client = RecordingClient({
            ("POST", "/api/chat/send"): {"id": "run-1", "state": "QUEUED", "canonical_url": None},
            ("GET", "/api/chat/runs/run-1"): {
                "id": "run-1", "state": "FAILED", "response_text": "partial answer",
                "error": "backend detail", "delivered_at": None,
            },
        })
        app, output = self.make_app(client)

        app.execute("garder après échec")
        app.execute("/rafraichir")

        self.assertEqual([draft.text for draft in app.unconfirmed_drafts.values()], ["garder après échec"])
        rendered = "\n".join(output)
        self.assertIn("partial answer", rendered)
        self.assertIn("backend detail", rendered)
        self.assertNotIn("Livraison confirmée", rendered)

    def test_delivered_run_confirms_delivery_once_even_when_refreshed_again(self):
        delivered = {
            "id": "run-1", "state": "COMPLETED",
            "delivered_at": "2026-09-10T01:00:00Z",
        }
        client = RecordingClient({
            ("POST", "/api/chat/send"): {"id": "run-1", "state": "QUEUED", "canonical_url": None},
            ("GET", "/api/chat/runs/run-1"): delivered,
        })
        app, output = self.make_app(client)

        app.execute("confirmer une fois")
        app.execute("/rafraichir")
        app.execute("/rafraichir")

        self.assertEqual("\n".join(output).count("Livraison confirmée"), 1)

    def test_follow_reports_response_once_and_acknowledges_only_the_delivered_submission(self):
        updates = iter([
            {"id": "run-1", "state": "WAITING_FOR_CHATGPT", "response_text": "answer", "delivered_at": None},
            {
                "id": "run-1", "state": "COMPLETED", "response_text": "answer",
                "delivered_at": "2026-09-10T01:00:00Z",
            },
        ])
        client = RecordingClient({
            ("POST", "/api/chat/send"): {"id": "run-1", "state": "QUEUED", "canonical_url": None},
            ("GET", "/api/chat/runs/run-1"): lambda *_args: next(updates),
        })
        app, output = self.make_app(client)
        app.execute("seul ce brouillon")
        app._sleep = lambda _seconds: None

        self.assertTrue(app.execute("/suivre"))

        self.assertEqual(app.unconfirmed_drafts, {})
        self.assertEqual("\n".join(output).count("answer"), 1)

    def test_conversation_selection_clears_old_run_and_mission_before_stop(self):
        client = RecordingClient()
        app, _ = self.make_app(client)
        app.selected_run_id = "run-old"
        app.selected_mission_id = "mission-old"
        app.conversations = [{"url": "https://chatgpt.com/c/b"}]

        app.execute("/ouvrir 1")
        app.execute("/suivre")
        app.execute("/rafraichir")
        app.execute("/stop")
        app.selected_run_id = "run-new"
        app.selected_mission_id = "mission-new"
        app.execute("/nouvelle")
        app.execute("/suivre")
        app.execute("/rafraichir")
        app.execute("/stop")

        self.assertIsNone(app.selected_run_id)
        self.assertIsNone(app.selected_mission_id)
        self.assertEqual(client.calls, [])

    def test_chat_and_mission_transitions_keep_exactly_one_active_target(self):
        client = RecordingClient({
            ("POST", "/api/chat/send"): {"id": "run-1", "state": "QUEUED", "canonical_url": None},
            ("GET", "/api/settings"): {"default_workspace": "/tmp/work"},
            ("POST", "/api/missions"): {"id": "mission-1", "state": "INITIALIZING_MISSION"},
            ("POST", "/api/missions/mission-1/cancel"): {"state": "CANCELLED"},
        })
        app, _ = self.make_app(client, ["oui"])
        app.selected_mission_id = "mission-old"

        app.execute("chat cible")
        self.assertEqual(app.selected_run_id, "run-1")
        self.assertIsNone(app.selected_mission_id)
        app.execute("/mission cible mission")
        self.assertEqual(app.selected_mission_id, "mission-1")
        self.assertIsNone(app.selected_run_id)
        app.execute("/stop")

        self.assertEqual(client.calls[-1][:2], ("POST", "/api/missions/mission-1/cancel"))

    def test_two_accepted_submissions_keep_separate_drafts_until_their_own_acknowledgements(self):
        runs = iter([
            {"id": "run-1", "state": "QUEUED", "canonical_url": None},
            {"id": "run-2", "state": "QUEUED", "canonical_url": None},
        ])
        client = RecordingClient({
            ("POST", "/api/chat/send"): lambda *_args: next(runs),
            ("GET", "/api/chat/runs/run-1"): {
                "id": "run-1", "state": "COMPLETED", "delivered_at": "2026-09-10T00:00:00Z",
            },
            ("GET", "/api/chat/runs/run-2"): {
                "id": "run-2", "state": "COMPLETED", "delivered_at": "2026-09-10T00:01:00Z",
            },
        })
        app, output = self.make_app(client)
        app.conversations = [{"url": "https://chatgpt.com/c/alpha"}]
        app.execute("/ouvrir 1")

        app.execute("premier message")
        app.execute("second message")
        self.assertEqual(
            [draft.text for draft in app.unconfirmed_drafts.values()],
            ["premier message", "second message"],
        )
        app.selected_run_id = "run-1"
        app.execute("/rafraichir")
        self.assertEqual([draft.text for draft in app.unconfirmed_drafts.values()], ["second message"])
        app.execute("/brouillon")
        self.assertIn("second message", "\n".join(output))
        app.selected_run_id = "run-2"
        app.execute("/rafraichir")
        self.assertEqual(app.unconfirmed_drafts, {})

    def test_ambiguous_submission_and_later_accepted_submission_survive_independently(self):
        replies = iter([
            ApiError(None, "timeout", uncertain=True),
            {"id": "run-2", "state": "QUEUED", "canonical_url": None},
        ])
        client = RecordingClient({
            ("POST", "/api/chat/send"): lambda *_args: next(replies),
            ("GET", "/api/chat/runs/run-2"): {
                "id": "run-2", "state": "COMPLETED", "delivered_at": "2026-09-10T00:00:00Z",
            },
        })
        app, _ = self.make_app(client)
        app.conversations = [{"url": "https://chatgpt.com/c/alpha"}]
        app.execute("/ouvrir 1")

        app.execute("incertain")
        app.execute("accepté")
        app.selected_run_id = "run-2"
        app.execute("/rafraichir")

        self.assertEqual([draft.text for draft in app.unconfirmed_drafts.values()], ["incertain"])

    def test_canonical_url_rekeys_every_unconfirmed_provisional_submission(self):
        replies = iter([
            ApiError(None, "timeout", uncertain=True),
            {
                "id": "run-2", "state": "QUEUED",
                "canonical_url": "https://chatgpt.com/c/canonical",
            },
        ])
        client = RecordingClient({("POST", "/api/chat/send"): lambda *_args: next(replies)})
        app, output = self.make_app(client)

        app.execute("avant canonique")
        app.execute("avec canonique")
        app.execute("/brouillon")

        self.assertEqual(
            [(draft.selection_key, draft.text) for draft in app.unconfirmed_drafts.values()],
            [
                ("conversation:https://chatgpt.com/c/canonical", "avant canonique"),
                ("conversation:https://chatgpt.com/c/canonical", "avec canonique"),
            ],
        )
        self.assertIn("avant canonique", "\n".join(output))
        self.assertIn("avec canonique", "\n".join(output))

    def test_mission_submission_forces_deterministic_network_off_and_per_action_approval(self):
        client = RecordingClient({
            ("GET", "/api/settings"): {"default_workspace": "/tmp/work"},
            ("POST", "/api/missions"): {"id": "mission-1", "state": "INITIALIZING_MISSION"},
        })
        app, _ = self.make_app(client, ["oui"])
        app.conversation_url = "https://chatgpt.com/c/a"

        self.assertTrue(app.execute("/mission écrire un fichier"))
        sent = client.calls[-1]
        self.assertEqual(sent[0:2], ("POST", "/api/missions"))
        self.assertEqual(sent[2]["executor_kind"], "deterministic")
        self.assertFalse(sent[2]["allow_network"])
        self.assertEqual(sent[2]["approval_policy"], "workspace-write-with-approvals")

    def test_approval_refuses_when_latest_policy_and_decision_action_ids_do_not_match(self):
        client = RecordingClient({
            ("GET", "/api/missions/m-1"): {
                "mission": {"id": "m-1", "state": "WAITING_FOR_APPROVAL"},
                "awaiting_approval": True,
                "timeline": {
                    "policy_decisions": [{"action_id": "policy-action", "requires_approval": 1}],
                    "orchestrator_decisions": [{"action_id": "decision-action", "decision_json": "{}"}],
                },
            },
        })
        app, output = self.make_app(client)
        app.selected_mission_id = "m-1"

        self.assertTrue(app.execute("/autoriser"))
        self.assertEqual([call[:2] for call in client.calls], [("GET", "/api/missions/m-1")])
        self.assertIn("refusée", "\n".join(output).lower())

    def test_approval_rechecks_same_action_before_sending_one_once_scope(self):
        payload = {
            "mission": {"id": "m-1", "state": "WAITING_FOR_APPROVAL"},
            "awaiting_approval": True,
            "pending_approval_action_id": "a-1",
            "timeline": {
                "policy_decisions": [{"action_id": "a-1", "requires_approval": 1}],
                "orchestrator_decisions": [{
                    "action_id": "a-1",
                        "decision_json": '{"actionId":"a-1","action":{"tool":"write_file","arguments":{"path":"x"}}}',
                }],
            },
        }
        client = RecordingClient({
            ("GET", "/api/missions/m-1"): payload,
            ("POST", "/api/missions/m-1/approve"): {"approved": True, "scope": "once"},
        })
        app, output = self.make_app(client, ["oui"])
        app.selected_mission_id = "m-1"

        self.assertTrue(app.execute("/autoriser"))
        self.assertEqual([call[:2] for call in client.calls], [
            ("GET", "/api/missions/m-1"),
            ("GET", "/api/missions/m-1"),
            ("POST", "/api/missions/m-1/approve"),
        ])
        self.assertEqual(client.calls[-1][2], {
            "scope": "once", "approve": True, "expected_action_id": "a-1",
        })
        self.assertIn("write_file", "\n".join(output))

    def test_approval_refuses_when_decision_json_action_id_disagrees_with_row_and_policy(self):
        client = RecordingClient({
            ("GET", "/api/missions/m-1"): {
                "mission": {"id": "m-1", "state": "WAITING_FOR_APPROVAL"},
                "awaiting_approval": True,
                "pending_approval_action_id": "a-1",
                "timeline": {
                    "policy_decisions": [{"action_id": "a-1", "requires_approval": 1}],
                    "orchestrator_decisions": [{
                        "action_id": "a-1",
                        "decision_json": '{"actionId":"other","action":{"tool":"write_file","arguments":{}}}',
                    }],
                },
            },
        })
        app, output = self.make_app(client)
        app.selected_mission_id = "m-1"

        self.assertTrue(app.execute("/autoriser"))
        self.assertEqual([call[:2] for call in client.calls], [("GET", "/api/missions/m-1")])
        self.assertIn("refusée", "\n".join(output).lower())

    def test_stop_cancels_selected_run_without_global_stop(self):
        client = RecordingClient({
            ("POST", "/api/chat/runs/run-1/cancel"): {"state": "CANCELLED"},
        })
        app, _ = self.make_app(client)
        app.selected_run_id = "run-1"

        self.assertTrue(app.execute("/stop"))
        self.assertEqual([call[:2] for call in client.calls], [("POST", "/api/chat/runs/run-1/cancel")])

    def test_stop_without_selection_refuses_without_posting_global_stop(self):
        client = RecordingClient()
        app, output = self.make_app(client)

        self.assertTrue(app.execute("/stop"))
        self.assertEqual(client.calls, [])
        self.assertIn("sélectionne", "\n".join(output).lower())

    def test_follow_interruption_does_not_cancel_selected_run(self):
        client = RecordingClient({
            ("GET", "/api/chat/runs/run-1"): {"id": "run-1", "state": "WAITING_FOR_CHATGPT"},
            ("GET", "/api/status"): {},
            ("GET", "/api/pipeline/status"): {},
        })
        output = []
        app = TerminalApp(client, output=output.append)
        app.selected_run_id = "run-1"
        app._sleep = lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt())
        self.assertTrue(app.execute("/suivre"))
        self.assertFalse(any("/cancel" in path for _, path, _, _ in client.calls))
        self.assertIn("rien n’a été annulé", "\n".join(output).lower())

    def test_follow_polls_selected_run_at_least_one_second_until_terminal_state(self):
        states = iter([
            {"id": "run-1", "state": "WAITING_FOR_CHATGPT"},
            {"id": "run-1", "state": "COMPLETED"},
        ])
        client = RecordingClient({("GET", "/api/chat/runs/run-1"): lambda *_args: next(states)})
        app, _ = self.make_app(client)
        app.selected_run_id = "run-1"
        sleeps = []
        app._sleep = sleeps.append

        self.assertTrue(app.execute("/suivre"))
        self.assertEqual(sleeps, [1.0])
        self.assertEqual([call[:2] for call in client.calls], [
            ("GET", "/api/chat/runs/run-1"),
            ("GET", "/api/chat/runs/run-1"),
        ])

    def test_follow_ctrl_c_leaves_selected_mission_running(self):
        client = RecordingClient({
            ("GET", "/api/missions/m-1"): {"mission": {"state": "WAITING_FOR_CHATGPT"}},
        })
        app, output = self.make_app(client)
        app.selected_mission_id = "m-1"

        def interrupted(_seconds):
            raise KeyboardInterrupt()

        app._sleep = interrupted
        self.assertTrue(app.execute("/suivre"))
        self.assertFalse(any("/cancel" in path for _, path, _, _ in client.calls))
        self.assertIn("rien n’a été annulé", "\n".join(output).lower())

    def test_settings_change_fetches_merges_confirms_and_never_sends_capabilities(self):
        settings = {
            "default_workspace": "/tmp/ws", "theme": "dark", "language": "fr",
            "process_capabilities": {"allowed": True}, "never_delete_files": True,
        }
        client = RecordingClient({
            ("GET", "/api/settings"): settings,
            ("PUT", "/api/settings"): {**settings, "theme": "light"},
        })
        app, _ = self.make_app(client, ["oui"])

        self.assertTrue(app.execute("/reglage theme light"))
        body = client.calls[-1][2]
        self.assertEqual(body["theme"], "light")
        self.assertNotIn("process_capabilities", body)

    def test_consent_requires_explicit_confirmation_before_opt_in(self):
        client = RecordingClient({
            ("GET", "/api/transport/status"): {"experimental_warning": "warning"},
        })
        app, _ = self.make_app(client, ["non"])

        self.assertTrue(app.execute("/consentement"))
        self.assertEqual([call[:2] for call in client.calls], [("GET", "/api/transport/status")])

    def test_model_selection_accepts_only_backend_discovered_label(self):
        client = RecordingClient({
            ("GET", "/api/models/chatgpt"): {"models": [{"label": "Visible", "selected": True}]},
            ("PUT", "/api/models/chatgpt"): {"selected": "Visible", "confirmed": True},
        })
        app, _ = self.make_app(client)

        self.assertTrue(app.execute("/modele Invisible"))
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(app.execute("/modele Visible"))
        self.assertEqual(client.calls[-1][2]["label"], "Visible")

    def test_model_selection_refuses_backend_fallback_after_discovery_error(self):
        client = RecordingClient({
            ("GET", "/api/models/chatgpt"): {
                "models": [{"label": "Configured candidate", "selected": True, "available": True}],
                "error": "selector unavailable",
            },
        })
        app, output = self.make_app(client)

        self.assertTrue(app.execute("/modele Configured candidate"))
        self.assertEqual([call[:2] for call in client.calls], [("GET", "/api/models/chatgpt")])
        self.assertIn("indisponible", "\n".join(output).lower())

    def test_unpaired_connect_opens_cortex_page_only_after_callback_succeeds(self):
        client = RecordingClient({("GET", "/api/chrome-extension/status"): {"paired": False}})
        opened = []
        app = TerminalApp(client, output=lambda _message: None, open_ui=lambda: opened.append("cortex"))

        self.assertTrue(app.execute("/connecter"))
        self.assertEqual(opened, ["cortex"])
        self.assertEqual([call[:2] for call in client.calls], [("GET", "/api/chrome-extension/status")])

    def test_ui_callback_false_reports_failure_and_manual_loopback_url(self):
        client = RecordingClient()
        client.base_url = "http://127.0.0.1:9911"
        output = []
        app = TerminalApp(client, output=output.append, open_ui=lambda: False)

        self.assertTrue(app.execute("/ui"))

        rendered = "\n".join(output).lower()
        self.assertIn("impossible", rendered)
        self.assertIn("http://127.0.0.1:9911/", rendered)
        self.assertNotIn("interface cortex ouverte", rendered)

    def test_unpaired_connect_without_ui_reports_instruction_without_token_or_open_claim(self):
        client = RecordingClient({("GET", "/api/chrome-extension/status"): {"paired": False, "token": "secret"}})
        app, output = self.make_app(client)

        self.assertTrue(app.execute("/connecter"))
        rendered = "\n".join(output).lower()
        self.assertIn("http://127.0.0.1:8420/", rendered)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("page cortex ouverte", rendered)

    def test_unpaired_connect_without_ui_uses_the_configured_loopback_base_url(self):
        client = RecordingClient({("GET", "/api/chrome-extension/status"): {"paired": False}})
        client.base_url = "http://127.0.0.1:9911"
        app, output = self.make_app(client)

        self.assertTrue(app.execute("/connecter"))

        self.assertIn("http://127.0.0.1:9911/", "\n".join(output))
