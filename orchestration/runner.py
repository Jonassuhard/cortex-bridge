"""Mode A end-to-end runner (mission spec §3, §8, §9, §12 + §6 opt-in gate).

Wires the ChatGPT web transport into the Phase 3 MissionLoop:

    create mission (SQLite)
    → lock conversation (§8 — existing /c/<id> or brand-new chat capture)
    → send the §9 orchestrator contract (ORCHESTRATOR_CONTRACT_TEMPLATE)
    → MissionLoop with TransportOrchestratorClient:
        verify_lock before every browser op, multi-signal completion,
        fenced-block extraction, strict validation, policy, tools, reports
    → transport errors map to safe mission pauses (never bypassed)

§6 gate: the experimental transport may send NOTHING unless the caller
explicitly passes experimental_transport_accepted=True (the UI sets this
only after the user accepts EXPERIMENTAL_TRANSPORT_WARNING). Default off.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from executor.policy import PolicyEngine
from executor.tools import ToolExecutor

from .loop import MAX_CYCLES, MissionLoop, MockReply
from .state import Budgets
from .store import Store, StoreError, TERMINAL_STATES
from transport.chatgpt_web.adapter import (
    EXPERIMENTAL_TRANSPORT_WARNING,
    BlockerDetected,
    ChatGPTWebTransport,
    TransportError,
)

EXPERIMENTAL_TRANSPORT_NOT_ACCEPTED = "EXPERIMENTAL_TRANSPORT_NOT_ACCEPTED"

ALLOWED_TOOLS_CSV = (
    "list_directory, read_file, file_exists, search_text, write_file, "
    "apply_patch, create_directory, run_process, run_tests, git_status, git_diff"
)

# §9 orchestrator contract + cortex.v1 fenced protocol + report format.
ORCHESTRATOR_CONTRACT_TEMPLATE = """You are the cloud orchestrator for Cortex Bridge.

You analyze the global objective.
You produce one bounded local action per iteration.
You do not directly claim that local work happened.
You wait for the validated execution report.
You adapt the next action based on the report.
You terminate only when all global acceptance criteria are satisfied.

Mission ID: {mission_id}
Workspace: {workspace}

Objective:
{objective}

Reply with EXACTLY ONE fenced block and no other structured payload:

```cortex-decision
{{
  "protocol": "cortex.v1",
  "missionId": "{mission_id}",
  "actionId": "<new UUID v4 for every decision>",
  "iteration": <1 for the first decision, +1 per decision>,
  "state": "EXECUTE" | "REQUEST_CONTEXT" | "COMPLETE" | "BLOCKED",
  "summary": "<one sentence>",
  "action": {{ "tool": "<one of: {tools}>", "arguments": {{ ... }} }} or null,
  "acceptanceCriteria": ["<verifiable criterion>", "..."],
  "requiresApproval": false,
  "terminal": false
}}
```

Rules:
- EXECUTE: exactly one bounded action using the allowed tools. Paths are
  workspace-relative only. Never absolute paths, never '..' traversal.
- REQUEST_CONTEXT: a read-only tool (or null) when you need more context.
- COMPLETE: only when every acceptance criterion of the objective is met;
  set "terminal": true and put the final validation instructions in
  acceptanceCriteria.
- BLOCKED: when you cannot proceed; set "terminal": true.
- After each EXECUTE or REQUEST_CONTEXT you receive exactly one
  ```cortex-report fenced block with the validated tool result
  (status SUCCEEDED | FAILED | BLOCKED | DENIED | CANCELLED). Adapt your
  next decision to it. Never emit more than one decision block per reply.
"""


class OptInRequired(Exception):
    """§6: experimental transport used without explicit user acceptance."""


def render_contract(objective: str, mission_id: str, workspace: str) -> str:
    return ORCHESTRATOR_CONTRACT_TEMPLATE.format(
        mission_id=mission_id, workspace=workspace, objective=objective, tools=ALLOWED_TOOLS_CSV
    )


class TransportOrchestratorClient:
    """Adapts ChatGPTWebTransport to the MissionLoop orchestrator interface."""

    def __init__(self, transport: ChatGPTWebTransport, store=None, mission_id: str | None = None):
        self.transport = transport
        self.store = store
        self.mission_id = mission_id

    @property
    def conversation_identity(self) -> str:
        lock = self.transport.lock
        return lock.identity if lock else "unknown-conversation"

    async def next_decision(self, message: str | None) -> MockReply:
        if message is not None:
            await self.transport.send_message(message)  # verifies lock first
            if self.store is not None and self.mission_id is not None:
                # Persist proven delivery (vs REPORT_SENT which is recorded at
                # finalize time, before the browser send). Resume logic relies
                # on this distinction to decide whether to resend or await.
                self.store.record_transport_event(
                    str(uuid.uuid4()), self.mission_id, "MESSAGE_DELIVERED",
                    {"kind": "report" if "```cortex-report" in message else "contract",
                     "bytes": len(message)},
                )
                # New-chat case: the lock is only captured after the first
                # send — persist it so resume can re-attach by identity.
                lock = getattr(self.transport, "lock", None)
                if lock is not None and "/c/" in lock.url:
                    self.store.update_conversation_binding(
                        self.mission_id, lock.url, lock.title, lock.identity
                    )
        reply = await self.transport.await_response()
        return MockReply(text=reply["protocol_text"], message_id=reply["id"])


@dataclass
class ModeARunner:
    """Runs a Mode A mission (user types the mission into Cortex Bridge)."""

    store: Store
    transport: ChatGPTWebTransport
    tools: ToolExecutor
    policy: PolicyEngine | None = None
    budgets: Budgets | None = None
    approval_callback: Callable | None = None
    action_validator: Callable | None = None
    final_validator: Callable | None = None
    experimental_transport_accepted: bool = False  # §6: default OFF
    max_cycles: int = MAX_CYCLES

    async def run_mission(
        self,
        objective: str,
        *,
        conversation_url: str | None = None,
        new_conversation_url: str | None = None,
        mission_id: str | None = None,
    ) -> dict:
        """End-to-end Mode A. Exactly one of conversation_url (existing
        /c/<id>) or new_conversation_url (fresh chat surface) is required."""
        if not self.experimental_transport_accepted:
            raise OptInRequired(
                "Experimental ChatGPT Web Transport not accepted. The user must "
                "explicitly enable it after reading the warning:\n"
                + EXPERIMENTAL_TRANSPORT_WARNING
            )
        if (conversation_url is None) == (new_conversation_url is None):
            raise ValueError("provide exactly one of conversation_url / new_conversation_url")

        mission_id = mission_id or str(uuid.uuid4())
        self.store.create_mission(
            mission_id,
            objective,
            str(self.tools.workspace),
            max_iterations=(self.budgets or Budgets()).max_iterations,
            max_duration_seconds=(self.budgets or Budgets()).max_duration_seconds,
        )

        # §8: lock exactly one conversation (or capture a brand-new one).
        if conversation_url is not None:
            lock = await self.transport.select_conversation(conversation_url)
        else:
            await self.transport.start_new_conversation(new_conversation_url)
            lock = None  # captured after the contract send creates /c/<id>

        client = TransportOrchestratorClient(self.transport, store=self.store, mission_id=mission_id)
        loop = MissionLoop(
            store=self.store,
            mission_id=mission_id,
            orchestrator=client,
            tools=self.tools,
            policy=self.policy,
            approval_callback=self.approval_callback,
            action_validator=self.action_validator,
            final_validator=self.final_validator,
            budgets=self.budgets,
            conversation=(
                {"url": lock.url, "title": lock.title, "target_id": lock.identity}
                if lock
                else {"url": new_conversation_url, "title": None, "target_id": None}
            ),
            contract=render_contract(objective, mission_id, str(self.tools.workspace)),
        )
        try:
            return await loop.run(max_cycles=self.max_cycles)
        except BlockerDetected as exc:
            # §5: login/CAPTCHA/rate-limit — pause safely, never bypass.
            return self._pause_mission(loop, exc.code)
        except TransportError as exc:
            return self._pause_mission(loop, exc.code)

    def _pause_mission(self, loop: MissionLoop, reason: str) -> dict:
        try:
            loop.sm.transition("PAUSED", pause_reason=reason)
        except StoreError:
            pass
        self.store.record_transport_event(
            str(uuid.uuid4()), loop.mission_id, "TRANSPORT_PAUSED", {"reason": reason}
        )
        return self.store.get_mission(loop.mission_id)
