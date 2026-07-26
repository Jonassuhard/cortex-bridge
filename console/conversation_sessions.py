"""Conversation-scoped WebBridge writer sessions."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field


class SessionCapacityError(RuntimeError):
    """The two distinct writer-conversation slots are already occupied."""


class SessionRekeyError(RuntimeError):
    """A provisional session cannot be moved onto another active writer."""


def _normalize(conversation_key: str) -> str:
    return (conversation_key or "").strip().rstrip("/")


def new_conversation_key() -> str:
    """Return a collision-proof key for a chat that has no canonical URL yet."""
    return f"provisional:{uuid.uuid4()}"


@dataclass
class SessionLease:
    conversation_key: str
    session_id: str
    target_url: str
    _registry: "ConversationSessionRegistry" = field(repr=False, compare=False)
    _token: str = field(default_factory=lambda: uuid.uuid4().hex, repr=False, compare=False)
    released: bool = field(default=False, init=False)

    async def release(self) -> None:
        """Release this ownership token once; stale releases cannot free a successor."""
        if self.released:
            return
        await self._registry._release(self.conversation_key, self._token)


@dataclass
class _SessionState:
    key: str
    session_id: str
    target_url: str
    held: bool = False
    waiters: int = 0
    current: SessionLease | None = None


class ConversationSessionRegistry:
    """Own the bounded, serialized set of active writer conversations."""

    def __init__(self, capacity: int = 2):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._states: dict[str, _SessionState] = {}
        self._aliases: dict[str, str] = {}
        self._condition = asyncio.Condition()

    def _resolve(self, conversation_key: str) -> str:
        key = _normalize(conversation_key)
        seen: set[str] = set()
        while key in self._aliases and key not in seen:
            seen.add(key)
            key = self._aliases[key]
        return key

    def _lease(self, state: _SessionState) -> SessionLease:
        lease = SessionLease(
            conversation_key=state.key,
            session_id=state.session_id,
            target_url=state.target_url,
            _registry=self,
        )
        state.current = lease
        return lease

    async def acquire_writer(self, conversation_key: str) -> SessionLease:
        key = self._resolve(conversation_key)
        if not key:
            raise ValueError("conversation_key must not be empty")
        async with self._condition:
            state = self._states.get(key)
            if state is None:
                if len(self._states) >= self.capacity:
                    raise SessionCapacityError("writer conversation capacity reached")
                state = _SessionState(
                    key=key,
                    session_id=f"cortex-conv-{uuid.uuid4().hex}",
                    target_url=key,
                )
                self._states[key] = state

            if state.held:
                state.waiters += 1
                try:
                    while state.held:
                        await self._condition.wait()
                finally:
                    state.waiters -= 1
            state.held = True
            return self._lease(state)

    async def rekey(self, provisional_key: str, canonical_key: str) -> SessionLease:
        provisional = self._resolve(provisional_key)
        canonical = _normalize(canonical_key)
        if not canonical:
            raise ValueError("canonical_key must not be empty")
        async with self._condition:
            state = self._states.get(provisional)
            if state is None or state.current is None:
                raise SessionRekeyError(f"unknown provisional writer {provisional_key}")
            collision = self._states.get(canonical)
            if collision is not None and collision is not state:
                raise SessionRekeyError(f"canonical writer already active: {canonical}")
            if provisional != canonical:
                self._states.pop(provisional, None)
                self._states[canonical] = state
                self._aliases[_normalize(provisional_key)] = canonical
            state.key = canonical
            state.target_url = canonical
            state.current.conversation_key = canonical
            state.current.target_url = canonical
            return state.current

    async def _release(self, conversation_key: str, token: str) -> None:
        async with self._condition:
            key = self._resolve(conversation_key)
            state = self._states.get(key)
            if (
                state is None
                or not state.held
                or state.current is None
                or state.current._token != token
            ):
                return
            state.current.released = True
            state.held = False
            if state.waiters == 0:
                self._states.pop(state.key, None)
                for alias, target in list(self._aliases.items()):
                    if target == state.key:
                        self._aliases.pop(alias, None)
            self._condition.notify_all()

    async def release_writer(self, conversation_key: str) -> None:
        """Compatibility release by key; lease.release() is stale-safe."""
        key = self._resolve(conversation_key)
        state = self._states.get(key)
        if state is None or state.current is None:
            return
        await self._release(key, state.current._token)

    def restore_writer(
        self,
        conversation_key: str,
        session_id: str,
        target_url: str,
    ) -> SessionLease:
        """Reserve a persisted non-terminal writer before accepting new work."""
        key = self._resolve(conversation_key)
        if not key or not session_id:
            raise ValueError("persisted conversation_key and session_id are required")
        existing = self._states.get(key)
        if existing is not None:
            if existing.session_id != session_id:
                raise SessionRekeyError(f"writer already restored with another session: {key}")
            return existing.current  # type: ignore[return-value]
        if len(self._states) >= self.capacity:
            raise SessionCapacityError("persisted writers exceed configured capacity")
        state = _SessionState(
            key=key,
            session_id=session_id,
            target_url=_normalize(target_url) or key,
            held=True,
        )
        state.current = self._lease(state)
        self._states[key] = state
        return state.current

    def active_leases(self) -> tuple[SessionLease, ...]:
        return tuple(
            state.current
            for state in self._states.values()
            if state.current is not None
        )
