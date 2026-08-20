from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONSOLE = ROOT / "console"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(CONSOLE) not in sys.path:
    sys.path.insert(0, str(CONSOLE))

from console.chrome_extension import (  # noqa: E402
    ALLOWED_ACTIONS,
    BridgeProtocolError,
    ChromeExtensionManager,
)


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class HangingConnection(FakeConnection):
    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)
        await asyncio.Event().wait()


class ChromeExtensionPairingTest(unittest.TestCase):
    def test_pairing_message_rejects_an_outdated_extension_without_spending_the_ticket(self) -> None:
        manager = ChromeExtensionManager()
        connection = FakeConnection()
        ticket = manager.issue_pairing_token()

        self.assertTrue(hasattr(manager, "consume_pairing_message"))
        paired, code = manager.consume_pairing_message(
            {
                "type": "pair",
                "token": ticket.value,
                "protocol_version": 1,
            },
            connection,
        )

        self.assertFalse(paired)
        self.assertEqual(code, "EXTENSION_PROTOCOL_MISMATCH")
        self.assertEqual(
            manager.public_status(),
            {
                "state": "extension_outdated",
                "extension_connected": False,
                "paired": False,
                "pending_commands": 0,
                "protocol_compatible": False,
                "extension_protocol_version": 1,
                "required_protocol_version": 2,
            },
        )
        paired, code = manager.consume_pairing_message(
            {
                "type": "pair",
                "token": ticket.value,
                "protocol_version": 2,
            },
            connection,
        )
        self.assertTrue(paired)
        self.assertEqual(code, "PAIRED")

    def test_pairing_message_requires_an_explicit_protocol_version(self) -> None:
        manager = ChromeExtensionManager()
        ticket = manager.issue_pairing_token()

        self.assertTrue(hasattr(manager, "consume_pairing_message"))
        paired, code = manager.consume_pairing_message(
            {"type": "pair", "token": ticket.value},
            FakeConnection(),
        )

        self.assertFalse(paired)
        self.assertEqual(code, "EXTENSION_PROTOCOL_MISMATCH")
        self.assertEqual(manager.public_status()["state"], "extension_outdated")

    def test_outdated_second_extension_cannot_corrupt_an_active_pairing_status(self) -> None:
        manager = ChromeExtensionManager()
        active_connection = FakeConnection()
        active_ticket = manager.issue_pairing_token()
        paired, code = manager.consume_pairing_message(
            {
                "type": "pair",
                "token": active_ticket.value,
                "protocol_version": 2,
            },
            active_connection,
        )
        self.assertTrue(paired)
        self.assertEqual(code, "PAIRED")

        replacement_ticket = manager.issue_pairing_token()
        paired, code = manager.consume_pairing_message(
            {
                "type": "pair",
                "token": replacement_ticket.value,
                "protocol_version": 1,
            },
            FakeConnection(),
        )

        self.assertFalse(paired)
        self.assertEqual(code, "EXTENSION_PROTOCOL_MISMATCH")
        self.assertEqual(
            manager.public_status(),
            {
                "state": "paired",
                "extension_connected": True,
                "paired": True,
                "pending_commands": 0,
                "protocol_compatible": True,
                "extension_protocol_version": 2,
                "required_protocol_version": 2,
            },
        )

    def test_pairing_token_has_256_bits_of_entropy_and_is_single_use(self) -> None:
        now = [100.0]
        manager = ChromeExtensionManager(clock=lambda: now[0])
        connection = FakeConnection()

        ticket = manager.issue_pairing_token()

        self.assertGreaterEqual(len(ticket.value), 43)
        self.assertEqual(ticket.expires_in_seconds, 60)
        self.assertTrue(manager.consume_pairing_token(ticket.value, connection))
        self.assertFalse(manager.consume_pairing_token(ticket.value, connection))
        self.assertEqual(manager.public_status()["state"], "paired")

    def test_expired_pairing_token_is_rejected(self) -> None:
        now = [100.0]
        manager = ChromeExtensionManager(clock=lambda: now[0])
        ticket = manager.issue_pairing_token()
        now[0] = 161.0

        self.assertFalse(manager.consume_pairing_token(ticket.value, FakeConnection()))
        self.assertEqual(manager.public_status()["state"], "disconnected")

    def test_pairing_status_never_exposes_the_token(self) -> None:
        manager = ChromeExtensionManager()
        ticket = manager.issue_pairing_token()

        serialized = json.dumps(manager.public_status())

        self.assertNotIn(ticket.value, serialized)
        self.assertEqual(manager.public_status()["state"], "awaiting_extension")


class ChromeExtensionCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_release_session_is_allowlisted_by_local_manager(self) -> None:
        self.assertIn("release_session", ALLOWED_ACTIONS)

    async def test_command_requires_a_paired_connection(self) -> None:
        manager = ChromeExtensionManager()

        with self.assertRaisesRegex(BridgeProtocolError, "not paired") as caught:
            await manager.command("session-a", "probe", {})

        self.assertEqual(caught.exception.code, "EXTENSION_UNPAIRED")

    async def test_unknown_command_is_rejected_before_sending(self) -> None:
        manager = ChromeExtensionManager()
        connection = FakeConnection()
        ticket = manager.issue_pairing_token()
        self.assertTrue(manager.consume_pairing_token(ticket.value, connection))

        with self.assertRaises(BridgeProtocolError) as caught:
            await manager.command("session-a", "raw_evaluate", {})

        self.assertEqual(caught.exception.code, "COMMAND_NOT_ALLOWED")
        self.assertEqual(connection.sent, [])
        self.assertNotIn("raw_evaluate", ALLOWED_ACTIONS)

    async def test_correlated_result_completes_the_matching_command(self) -> None:
        manager = ChromeExtensionManager()
        connection = FakeConnection()
        ticket = manager.issue_pairing_token()
        self.assertTrue(manager.consume_pairing_token(ticket.value, connection))

        task = asyncio.create_task(
            manager.command("session-a", "probe", {"detail": "light"}, timeout=1)
        )
        await asyncio.sleep(0)
        request = connection.sent[0]
        self.assertEqual(request["type"], "command")
        self.assertEqual(request["session"], "session-a")
        self.assertEqual(request["action"], "probe")

        accepted = manager.receive_result(
            connection,
            {
                "type": "command.result",
                "request_id": request["request_id"],
                "ok": True,
                "result": {"ok": True, "composer_present": True},
            },
        )

        self.assertTrue(accepted)
        self.assertEqual(
            await task,
            {"ok": True, "composer_present": True},
        )

    async def test_extension_error_is_preserved_as_a_stable_code(self) -> None:
        manager = ChromeExtensionManager()
        connection = FakeConnection()
        ticket = manager.issue_pairing_token()
        self.assertTrue(manager.consume_pairing_token(ticket.value, connection))

        task = asyncio.create_task(
            manager.command("session-a", "probe", {}, timeout=1)
        )
        await asyncio.sleep(0)
        request_id = connection.sent[0]["request_id"]
        manager.receive_result(
            connection,
            {
                "type": "command.result",
                "request_id": request_id,
                "ok": False,
                "error": {"code": "TAB_CLOSED", "message": "bound tab closed"},
            },
        )

        with self.assertRaises(BridgeProtocolError) as caught:
            await task
        self.assertEqual(caught.exception.code, "TAB_CLOSED")

    async def test_command_timeout_removes_the_pending_request(self) -> None:
        manager = ChromeExtensionManager()
        connection = FakeConnection()
        ticket = manager.issue_pairing_token()
        self.assertTrue(manager.consume_pairing_token(ticket.value, connection))

        with self.assertRaises(BridgeProtocolError) as caught:
            await manager.command("session-a", "probe", {}, timeout=0.001)

        self.assertEqual(caught.exception.code, "EXTENSION_TIMEOUT")
        self.assertEqual(manager.pending_count, 0)

    async def test_command_timeout_also_bounds_a_stalled_websocket_send(self) -> None:
        manager = ChromeExtensionManager()
        connection = HangingConnection()
        ticket = manager.issue_pairing_token()
        self.assertTrue(manager.consume_pairing_token(ticket.value, connection))

        with self.assertRaises(BridgeProtocolError) as caught:
            await asyncio.wait_for(
                manager.command("session-a", "probe", {}, timeout=0.01),
                timeout=0.1,
            )

        self.assertEqual(caught.exception.code, "EXTENSION_TIMEOUT")
        self.assertEqual(manager.pending_count, 0)

    async def test_disconnect_fails_pending_commands_and_clears_pairing(self) -> None:
        manager = ChromeExtensionManager()
        connection = FakeConnection()
        ticket = manager.issue_pairing_token()
        self.assertTrue(manager.consume_pairing_token(ticket.value, connection))
        task = asyncio.create_task(
            manager.command("session-a", "probe", {}, timeout=1)
        )
        await asyncio.sleep(0)

        manager.disconnect(connection)

        with self.assertRaises(BridgeProtocolError) as caught:
            await task
        self.assertEqual(caught.exception.code, "EXTENSION_DISCONNECTED")
        self.assertEqual(manager.public_status()["state"], "disconnected")


if __name__ == "__main__":
    unittest.main()
