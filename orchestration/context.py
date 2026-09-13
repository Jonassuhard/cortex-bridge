"""Bounded context packets for Codex → ChatGPT supervisor loops.

The packet is deliberately independent from the browser transport.  It is a
small, deterministic manifest describing what Codex knows and what may be
proposed to ChatGPT.  It never reads files or sends attachments by itself.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from urllib.parse import urlparse

MAX_GOAL_CHARS = 4_000
MAX_CONVERSATION_CHARS = 24_000
MAX_FACTS = 50
MAX_CONTEXT_ITEMS = 20
MAX_ITEM_REASON_CHARS = 500
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_REPORT_FIELD_CHARS = 2_000

DESKTOP_ATTACHMENT_LIMITATION = (
    "The desktop ChatGPT application's native attachment capability is not "
    "exposed by this repository. Treat files, screenshots and links as "
    "proposals until an explicit local approval and supported transport exist."
)

_SHA256_RE = re.compile(r"\A[0-9a-fA-F]{64}\Z")
_SECRET_RE = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|secret)\b"
    r"\s*[:=]\s*)([^\s,;]+)"
)
_ABSOLUTE_PATH_PREFIXES = ("/" + "Users/", "/" + "private/", "/" + "Volumes/", "/" + "home/")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"(?:" + "|".join(re.escape(prefix) for prefix in _ABSOLUTE_PATH_PREFIXES) + r")"
    r"[^\s,;)\]}>\"']+|[A-Za-z]:[\\/][^\s,;)\]}>\"']+)"
)


class ContextPacketError(ValueError):
    """The proposed supervisor context is not safe or well formed."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _text(value: object, field: str, *, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextPacketError("MALFORMED_CONTEXT", f"{field} must be non-empty text")
    value = value.strip()
    if len(value) > max_chars:
        raise ContextPacketError(
            "CONTEXT_TOO_LARGE", f"{field} exceeds {max_chars} characters"
        )
    return value


def _optional_text(value: object, field: str, *, max_chars: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContextPacketError("MALFORMED_CONTEXT", f"{field} must be text")
    value = value.strip()
    if len(value) > max_chars:
        raise ContextPacketError(
            "CONTEXT_TOO_LARGE", f"{field} exceeds {max_chars} characters"
        )
    return value or None


def _redact(value: str) -> str:
    """Remove paths and common inline secrets before context leaves the local host."""

    value = _ABSOLUTE_PATH_RE.sub("[REDACTED_PATH]", value)
    return _SECRET_RE.sub(r"\1[REDACTED]", value)


def _report_text(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    text = _text(value, field, max_chars=MAX_REPORT_FIELD_CHARS)
    if _ABSOLUTE_PATH_RE.search(text):
        raise ContextPacketError(
            "UNSAFE_REPORT",
            f"{field} must not contain an absolute path",
        )
    return _redact(text)


def _report_list(values: Iterable[str], field: str) -> list[str]:
    result: list[str] = []
    for index, value in enumerate(values):
        result.append(_report_text(value, f"{field}[{index}]") or "")
    return result


def _relative_path(value: object) -> str:
    path = _text(value, "available_context.path", max_chars=1_024)
    if path.startswith(("/", "~", "\\")) or re.match(r"^[A-Za-z]:[\\/]", path):
        raise ContextPacketError("ABSOLUTE_CONTEXT_PATH", "file paths must be workspace-relative")
    parts = re.split(r"[\\/]+", path)
    if any(part in {"", ".", ".."} for part in parts):
        raise ContextPacketError(
            "UNSAFE_CONTEXT_PATH", "file paths must not contain empty, '.' or '..' segments"
        )
    if "\x00" in path:
        raise ContextPacketError("UNSAFE_CONTEXT_PATH", "file paths must not contain NUL")
    return "/".join(parts)


def _reason(item: Mapping[str, object]) -> str:
    return _text(item.get("reason"), "available_context.reason", max_chars=MAX_ITEM_REASON_CHARS)


def _context_item(item: Mapping[str, object]) -> dict[str, object]:
    kind = item.get("kind")
    if kind not in {"file", "screenshot", "link"}:
        raise ContextPacketError(
            "UNSUPPORTED_CONTEXT_KIND",
            "kind must be one of file, screenshot or link",
        )
    result: dict[str, object] = {
        "kind": kind,
        "reason": _reason(item),
        # Every item is a proposal until the user explicitly approves it.
        "transmission": "proposal_required",
    }
    if kind == "file":
        result["path"] = _relative_path(item.get("path"))
        size = item.get("size_bytes", 0)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ContextPacketError("MALFORMED_CONTEXT", "file size_bytes must be a non-negative integer")
        if size > MAX_FILE_BYTES:
            raise ContextPacketError(
                "CONTEXT_ITEM_TOO_LARGE", f"file exceeds {MAX_FILE_BYTES} bytes"
            )
        result["size_bytes"] = size
        digest = item.get("sha256")
        if digest is not None:
            if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                raise ContextPacketError("MALFORMED_CONTEXT", "sha256 must be a 64-character hexadecimal digest")
            result["sha256"] = digest.lower()
    elif kind == "screenshot":
        result["target"] = _text(item.get("target"), "available_context.target", max_chars=300)
    else:
        url = _text(item.get("url"), "available_context.url", max_chars=2_048)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ContextPacketError("UNSAFE_CONTEXT_LINK", "links must use http or https")
        result["url"] = url
    return result


def _deduplicate(items: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, object]] = []
    for item in items:
        key_name = {"file": "path", "screenshot": "target", "link": "url"}[str(item["kind"])]
        key = (str(item["kind"]), str(item[key_name]))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def build_context_packet(
    *,
    goal: str,
    conversation_text: str = "",
    conversation_mode: str = "relevant_excerpt",
    conversation_consent: bool = False,
    facts: Iterable[Mapping[str, object]] = (),
    constraints: Iterable[str] = (),
    available_context: Iterable[Mapping[str, object]] = (),
    capabilities: Iterable[str] = (),
    missing_information: Iterable[str] = (),
) -> dict[str, object]:
    """Build a deterministic, redacted and bounded context packet."""

    if conversation_mode not in {"relevant_excerpt", "full_with_consent"}:
        raise ContextPacketError("MALFORMED_CONTEXT", "conversation_mode is not supported")
    if conversation_mode == "full_with_consent" and conversation_consent is not True:
        raise ContextPacketError(
            "FULL_TRANSCRIPT_CONSENT_REQUIRED",
            "full conversation context requires explicit consent",
        )
    if not isinstance(conversation_consent, bool):
        raise ContextPacketError("MALFORMED_CONTEXT", "conversation_consent must be boolean")

    goal_text = _redact(_text(goal, "goal", max_chars=MAX_GOAL_CHARS))
    conversation = _redact(conversation_text.strip()) if conversation_text else ""
    if len(conversation) > MAX_CONVERSATION_CHARS:
        raise ContextPacketError(
            "CONTEXT_TOO_LARGE", f"conversation_text exceeds {MAX_CONVERSATION_CHARS} characters"
        )

    fact_values: list[dict[str, str]] = []
    for index, fact in enumerate(facts):
        if index >= MAX_FACTS:
            raise ContextPacketError("CONTEXT_TOO_LARGE", f"at most {MAX_FACTS} facts are allowed")
        if not isinstance(fact, Mapping):
            raise ContextPacketError("MALFORMED_CONTEXT", "facts must contain objects")
        fact_values.append(
            {
                "value": _redact(_text(fact.get("value"), f"facts[{index}].value", max_chars=1_000)),
                "source": _redact(_text(fact.get("source"), f"facts[{index}].source", max_chars=500)),
                "confidence": _text(fact.get("confidence"), f"facts[{index}].confidence", max_chars=40),
            }
        )

    item_values: list[dict[str, object]] = []
    for index, item in enumerate(available_context):
        if index >= MAX_CONTEXT_ITEMS:
            raise ContextPacketError(
                "CONTEXT_TOO_LARGE", f"at most {MAX_CONTEXT_ITEMS} context items are allowed"
            )
        if not isinstance(item, Mapping):
            raise ContextPacketError("MALFORMED_CONTEXT", "available_context must contain objects")
        item_values.append(_context_item(item))

    def text_list(values: Iterable[str], field: str, max_items: int = 50) -> list[str]:
        result: list[str] = []
        for index, value in enumerate(values):
            if index >= max_items:
                raise ContextPacketError("CONTEXT_TOO_LARGE", f"at most {max_items} {field} are allowed")
            result.append(_redact(_text(value, f"{field}[{index}]", max_chars=500)))
        return result

    capability_values = text_list(capabilities, "capabilities")
    return {
        "protocol": "desktop-supervisor.v1",
        "goal": goal_text,
        "conversation": {
            "consent": conversation_consent,
            "mode": conversation_mode,
            "text": conversation,
        },
        "facts": fact_values,
        "constraints": text_list(constraints, "constraints"),
        "available_context": _deduplicate(item_values),
        "capabilities": capability_values,
        "missing_information": text_list(missing_information, "missing_information"),
    }


def render_context_packet(packet: Mapping[str, object]) -> str:
    """Render a packet as stable JSON for inclusion in a supervisor prompt."""

    validated = validate_context_packet(packet)
    return json.dumps(validated, ensure_ascii=False, sort_keys=True, indent=2)


def render_supervisor_prompt(
    packet: Mapping[str, object],
    decision_contract: str,
) -> str:
    """Render the bounded packet as an explicit desktop-supervisor prompt.

    This is a pure formatter: it never reads a file, opens a browser or sends
    a message.  Keeping this boundary pure makes the supervisor loop testable
    without pretending that the desktop ChatGPT app exposes attachments.
    """

    contract = _text(decision_contract, "decision_contract", max_chars=MAX_CONVERSATION_CHARS)
    return (
        "You are the ChatGPT supervisor for Cortex Bridge.\n"
        "Propose one safe, verifiable next step; do not claim local work happened.\n"
        f"Capability boundary: {DESKTOP_ATTACHMENT_LIMITATION}\n\n"
        "Decision contract:\n"
        f"{contract}\n\n"
        "Bounded context packet (read-only until explicitly approved):\n"
        "```json\n"
        f"{render_context_packet(packet)}\n"
        "```\n"
        "Return exactly one cortex-decision block or state that the task is BLOCKED."
    )


def render_supervisor_report(
    status: str,
    *,
    requested_action: str,
    executed_action: str | None = None,
    command: str | None = None,
    result: str | None = None,
    evidence: Iterable[str] = (),
    unknowns: Iterable[str] = (),
    next_safe_action: str | None = None,
) -> str:
    """Render a truthful report without leaking secrets or host paths."""

    if status not in {"SUCCEEDED", "FAILED", "BLOCKED", "DENIED", "CANCELLED"}:
        raise ContextPacketError("MALFORMED_REPORT", "status is not supported")
    report: dict[str, object] = {
        "protocol": "desktop-supervisor-report.v1",
        "status": status,
        "requested_action": _report_text(requested_action, "requested_action"),
        "executed_action": _report_text(executed_action, "executed_action", optional=True),
        "command": _report_text(command, "command", optional=True),
        "result": _report_text(result, "result", optional=True),
        "evidence": _report_list(evidence, "evidence"),
        "unknowns": _report_list(unknowns, "unknowns"),
        "next_safe_action": _report_text(next_safe_action, "next_safe_action", optional=True),
    }
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)


def validate_context_packet(packet: object) -> dict[str, object]:
    """Validate an already serialized packet before it reaches a transport."""

    if not isinstance(packet, Mapping) or packet.get("protocol") != "desktop-supervisor.v1":
        raise ContextPacketError("MALFORMED_CONTEXT", "packet protocol must be desktop-supervisor.v1")
    conversation = packet.get("conversation")
    if not isinstance(conversation, Mapping):
        raise ContextPacketError("MALFORMED_CONTEXT", "conversation must be an object")
    return build_context_packet(
        goal=packet.get("goal", ""),
        conversation_text=conversation.get("text", "") or "",
        conversation_mode=conversation.get("mode", "relevant_excerpt"),
        # A packet that has already crossed a trust boundary must carry the
        # explicit consent marker when it contains a full transcript.
        conversation_consent=conversation.get("consent") is True,
        facts=packet.get("facts", ()) or (),
        constraints=packet.get("constraints", ()) or (),
        available_context=packet.get("available_context", ()) or (),
        capabilities=packet.get("capabilities", ()) or (),
        missing_information=packet.get("missing_information", ()) or (),
    )
