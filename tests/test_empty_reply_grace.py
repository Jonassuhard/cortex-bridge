"""Empty-reply grace tests (thinking-model adaptation, 2026-07-25).

Live incident: on a thinking model, ChatGPT renders an EMPTY assistant
shell while reasoning, with a gap between "stop button gone" and the code
block being painted. The transport extracted that empty shell after the
stability interval and declared NO_DECISION_BLOCK three times on replies
that were in fact perfect cortex-decision blocks.

The fix: an empty assistant message is never final within
`empty_reply_grace` seconds; the stability signature also covers code
block contents.

These tests use a scripted fake driver — no fixture server, no browser.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from transport.chatgpt_web.adapter import (  # noqa: E402
    CHATGPT_RESPONSE_TIMEOUT,
    ChatGPTWebTransport,
    TransportError,
    protocol_text,
)

DECISION = '{"protocol": "cortex.v1", "state": "COMPLETE"}'


def _assistant(mid: str, text: str = "", blocks: list | None = None) -> dict:
    return {
        "id": mid,
        "role": "assistant",
        "text": text,
        "code_blocks": blocks or [],
    }


def _state(messages: list, streaming: bool = False) -> dict:
    return {
        "url": "https://chatgpt.com/c/fake",
        "conversation_id": "fake",
        "blocker": None,
        "composer_present": True,
        "stop_button_present": streaming,
        "streaming": streaming,
        "messages": messages,
    }


class ScriptedDriver:
    """Returns each queued state in order, then repeats the last one."""

    def __init__(self, states: list[dict]):
        self.states = list(states)
        self.calls = 0

    async def get_state(self) -> dict:
        idx = min(self.calls, len(self.states) - 1)
        self.calls += 1
        return self.states[idx]


def make_transport(driver, **overrides):
    params = {
        "stability_interval": 0.15,
        "post_stream_stability_interval": 0.15,
        "poll_interval": 0.05,
        "max_wait": 5.0,
        "empty_reply_grace": 0.6,
    }
    params.update(overrides)
    return ChatGPTWebTransport(driver, **params)


class EmptyReplyGraceTest(unittest.IsolatedAsyncioTestCase):
    async def test_empty_shell_then_code_block_is_waited_out(self):
        """Thinking-model timeline: empty shell for ~0.35s, then the
        cortex-decision block paints. Must extract the real content."""
        states = [_state([_assistant("m1")]) for _ in range(7)]  # ~0.35s empty
        states += [
            _state([_assistant("m1", "", [{"lang": "cortex-decision", "text": DECISION}])])
            for _ in range(20)
        ]
        transport = make_transport(ScriptedDriver(states))
        result = await transport.await_response()
        self.assertEqual(result["id"], "m1")
        self.assertIn(DECISION, result["protocol_text"])

    async def test_empty_shell_beyond_grace_is_extracted_empty(self):
        """A genuinely empty reply still surfaces (as empty) once the grace
        window plus stability interval elapse — the loop then records its
        usual protocol violation instead of hanging."""
        states = [_state([_assistant("m1")]) for _ in range(40)]  # always empty
        transport = make_transport(ScriptedDriver(states), empty_reply_grace=0.2)
        result = await transport.await_response()
        self.assertEqual(result["text"], "")

    async def test_zero_grace_preserves_legacy_fast_extraction(self):
        """grace=0 disables the protection (fixture/back-compat mode)."""
        states = [_state([_assistant("m1")]) for _ in range(20)]
        transport = make_transport(ScriptedDriver(states), empty_reply_grace=0.0)
        result = await transport.await_response()
        self.assertEqual(result["text"], "")

    async def test_code_block_growth_defeats_stability(self):
        """Prose stable but code block still growing -> not stable yet."""
        growing = [
            _state([_assistant("m1", "Answer:", [{"lang": "cortex-decision", "text": DECISION[:i]}])])
            for i in (5, 10, 15, 20, 25)
        ]
        final = _state([_assistant("m1", "Answer:", [{"lang": "cortex-decision", "text": DECISION}])])
        states = growing + [final] * 20
        transport = make_transport(ScriptedDriver(states))
        result = await transport.await_response()
        self.assertIn(DECISION, result["protocol_text"])

    async def test_empty_forever_times_out_not_extracts(self):
        """Empty shell shorter than grace, forever, with max_wait < grace:
        must raise CHATGPT_RESPONSE_TIMEOUT, never extract mid-grace."""
        states = [_state([_assistant("m1")]) for _ in range(200)]
        transport = make_transport(
            ScriptedDriver(states), empty_reply_grace=45.0, max_wait=0.5
        )
        with self.assertRaises(TransportError) as ctx:
            await transport.await_response()
        self.assertIn(CHATGPT_RESPONSE_TIMEOUT, str(ctx.exception))

    async def test_streaming_resets_grace_window(self):
        """Streaming phases (stop button visible) reset the grace clock:
        empty shell -> streaming -> empty gap -> content paints."""
        states = (
            [_state([_assistant("m1")], streaming=False) for _ in range(3)]
            + [_state([_assistant("m1")], streaming=True) for _ in range(4)]
            + [_state([_assistant("m1")], streaming=False) for _ in range(3)]
            + [
                _state([_assistant("m1", "", [{"lang": "cortex-decision", "text": DECISION}])])
                for _ in range(20)
            ]
        )
        transport = make_transport(ScriptedDriver(states), empty_reply_grace=0.6)
        result = await transport.await_response()
        self.assertIn(DECISION, result["protocol_text"])


class ProtocolTextReconstructionTest(unittest.TestCase):
    def test_visible_protocol_label_restores_language_when_dom_drops_it(self):
        """Regression: current ChatGPT renders the language label outside the
        code element, so the block's DOM language is empty even though the
        visible message begins with ``cortex-decision``."""
        message = {
            "text": f"cortex-decision\n{DECISION}",
            "code_blocks": [{"lang": "", "text": DECISION}],
        }

        rebuilt = protocol_text(message)

        self.assertEqual(rebuilt, f"```cortex-decision\n{DECISION}\n```")


if __name__ == "__main__":
    unittest.main()
