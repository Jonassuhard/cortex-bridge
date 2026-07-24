"""DOM health-probe tests (adaptive transport, no real ChatGPT).

Covers:
  - _summarize_probe ok/failures/warnings semantics
  - ChatGPTWebTransport.probe() delegation + unsupported-driver fallback
  - GET /api/transport/probe handler logic (factory monkeypatched, no server)

stdlib unittest:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

from fastapi import HTTPException  # noqa: E402

import missions as missions_api  # noqa: E402  (console/missions.py)
from transport.chatgpt_web.adapter import (  # noqa: E402
    ChatGPTWebTransport,
    DriverError,
    LocalFixtureDriver,
    _summarize_probe,
)


def _roles(composer=True, messages=True, send=True, stop=False):
    def entry(ok):
        return {"ok": ok, "selector": "#sel" if ok else None, "count": 1 if ok else 0}
    return {
        "composer": entry(composer),
        "messages": entry(messages),
        "send": entry(send),
        "stop": entry(stop),
    }


class SummarizeProbeTest(unittest.TestCase):
    def test_all_ok(self):
        result = _summarize_probe({"url": "https://chatgpt.com/c/x", "roles": _roles()})
        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["warnings"], ["stop"])  # stop absent while idle: fine

    def test_composer_missing_is_failure(self):
        result = _summarize_probe({"roles": _roles(composer=False)})
        self.assertFalse(result["ok"])
        self.assertIn("composer", result["failures"])

    def test_messages_missing_is_failure(self):
        result = _summarize_probe({"roles": _roles(messages=False)})
        self.assertFalse(result["ok"])
        self.assertIn("messages", result["failures"])

    def test_send_missing_is_warning_only(self):
        # Idle composer -> the real send button does not exist yet. A
        # read-only probe must not cry wolf: warning, never failure.
        result = _summarize_probe({"roles": _roles(send=False)})
        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])
        self.assertIn("send", result["warnings"])

    def test_missing_roles_key(self):
        result = _summarize_probe({})
        self.assertFalse(result["ok"])
        self.assertIn("composer", result["failures"])
        self.assertIn("messages", result["failures"])


class FakeProbeDriver:
    """Minimal driver exposing an async probe (fixture drivers do not)."""

    def __init__(self, payload=None, exc=None):
        self.payload = payload or {"ok": True, "roles": _roles(), "failures": [], "warnings": []}
        self.exc = exc
        self.calls = 0

    async def probe(self):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.payload


class TransportProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_driver(self):
        transport = ChatGPTWebTransport(LocalFixtureDriver("http://127.0.0.1:1"))
        result = await transport.probe()
        self.assertFalse(result["ok"])
        self.assertIn("unsupported-driver", result["failures"])
        self.assertIn("error", result)

    async def test_delegates_to_driver(self):
        driver = FakeProbeDriver()
        transport = ChatGPTWebTransport(driver)
        result = await transport.probe()
        self.assertEqual(driver.calls, 1)
        self.assertTrue(result["ok"])


class ProbeEndpointTest(unittest.TestCase):
    def setUp(self):
        self._saved_factory = missions_api.transport_factory
        self.addCleanup(setattr, missions_api, "transport_factory", self._saved_factory)

    def test_endpoint_returns_payload(self):
        driver = FakeProbeDriver(payload={"ok": True, "failures": [], "warnings": ["stop"]})
        missions_api.transport_factory = lambda: ChatGPTWebTransport(driver)
        result = asyncio.run(missions_api.transport_probe())
        self.assertTrue(result["ok"])
        self.assertEqual(result["warnings"], ["stop"])

    def test_endpoint_503_on_driver_error(self):
        driver = FakeProbeDriver(exc=DriverError("daemon unreachable"))
        missions_api.transport_factory = lambda: ChatGPTWebTransport(driver)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(missions_api.transport_probe())
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("daemon unreachable", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
