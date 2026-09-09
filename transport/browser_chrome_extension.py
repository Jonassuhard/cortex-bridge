"""BrowserDriver implementation backed by the paired Chrome extension."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import mimetypes
import os
import re
import shutil
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    from chrome_extension import (
        BridgeProtocolError,
        ChromeExtensionManager,
        chrome_extension_manager,
    )
    from cortex_paths import build_paths
except ModuleNotFoundError:
    from console.chrome_extension import (
        BridgeProtocolError,
        ChromeExtensionManager,
        chrome_extension_manager,
    )
    from console.cortex_paths import build_paths

from transport.chatgpt_web.adapter import DriverError, TabClosedError


RUNTIME_PATHS = build_paths()
EXTENSION_FILE_LIMIT_BYTES = 25 * 1024 * 1024
TRANSFER_CHUNK_CHARACTERS = 256 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CONTENT_SCRIPT_RETRY_DELAY_SECONDS = 0.25
CONTENT_SCRIPT_RECOVERY_FAILURES = 3
CONTENT_SCRIPT_WRITE_READY_TIMEOUT_SECONDS = 10.0
OPEN_LOGIN_BUDGET_SECONDS = 8.0
OPEN_LOGIN_LOADING_ERROR_CODES = frozenset({"EXTENSION_TIMEOUT", "TAB_UNAVAILABLE"})
CONTENT_SCRIPT_NOT_READY_MESSAGE = "The ChatGPT content script is not available yet"
MACOS_AX_HELPER_SOURCE = Path(__file__).with_name("macos_ax_send.swift")
MACOS_AX_HELPER_NAME = "cortex-macos-ax-send"
_DUPLICATE_ATTACHMENT_INDEX = re.compile(
    r" ?\((?:[0-9]+|[0-9]{8}-[0-9]{6})\)$"
)
_SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")
CONTENT_SCRIPT_READ_ACTIONS = frozenset(
    {
        "probe",
        "get_state",
        "get_light_state",
        "list_conversations",
        "list_models",
    }
)
SESSION_RECEIPT_CAPABILITY = "session_quiescence_receipt_v1"
SESSION_RECEIPT_ACTIONS = frozenset(
    {
        "open_chatgpt",
        "focus_tab",
        "navigate",
        "list_tabs",
        "close_tab",
        "probe",
        "get_state",
        "get_light_state",
        "spa_navigate",
        "list_conversations",
        "send_text",
        "press_stop",
        "attachment_begin",
        "attachment_chunk",
        "attachment_commit",
        "await_attachment",
        "send_bare",
        "capture_screenshot",
        "list_models",
        "select_model",
    }
)


def _coded_driver_error(code: str, message: str) -> DriverError:
    error = DriverError(message)
    error.code = code
    return error


def _attachment_name_matches(actual: str, expected: str) -> bool:
    actual_name = Path(str(actual or "")).name
    expected_name = Path(str(expected or "")).name
    if not actual_name or not expected_name:
        return False
    if actual_name == expected_name:
        return True
    suffix = Path(expected_name).suffix
    stem = expected_name[: -len(suffix)] if suffix else expected_name
    if suffix and not actual_name.endswith(suffix):
        return False
    actual_stem = actual_name[: -len(suffix)] if suffix else actual_name
    duplicate = _DUPLICATE_ATTACHMENT_INDEX.search(actual_stem)
    return bool(duplicate and actual_stem[: duplicate.start()] == stem)


def _normalized_message_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _normalized_message_text_sha256(value: str) -> str:
    normalized = _normalized_message_text(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _same_chatgpt_route(actual_url: str, expected_url: str) -> bool:
    actual = urllib.parse.urlsplit(str(actual_url or ""))
    expected = urllib.parse.urlsplit(str(expected_url or ""))
    return (
        actual.scheme.lower() == expected.scheme.lower()
        and actual.netloc.lower() == expected.netloc.lower()
        and (actual.path.rstrip("/") or "/")
        == (expected.path.rstrip("/") or "/")
    )


async def _compile_macos_ax_helper() -> Path:
    override = os.environ.get("CORTEX_MACOS_AX_HELPER")
    if override:
        helper = Path(override).expanduser()
        if (
            not helper.is_absolute()
            or helper.is_symlink()
            or not helper.is_file()
            or not os.access(helper, os.X_OK)
        ):
            raise _coded_driver_error(
                "NATIVE_HELPER_UNAVAILABLE",
                "Le helper macOS configuré est invalide.",
            )
        return helper.resolve()
    if sys.platform != "darwin":
        raise _coded_driver_error(
            "NATIVE_HELPER_UNAVAILABLE",
            "L’envoi de pièces jointes via Chrome nécessite macOS.",
        )
    source = MACOS_AX_HELPER_SOURCE
    if source.is_symlink() or not source.is_file():
        raise _coded_driver_error(
            "NATIVE_HELPER_UNAVAILABLE",
            "La source du helper macOS est absente.",
        )
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise _coded_driver_error(
            "NATIVE_HELPER_UNAVAILABLE",
            "Installe les outils de ligne de commande Apple pour activer l’envoi de fichiers.",
        )
    home = Path(os.environ.get("CORTEX_HOME", str(RUNTIME_PATHS.home))).expanduser()
    if not home.is_absolute():
        raise _coded_driver_error(
            "NATIVE_HELPER_UNAVAILABLE",
            "CORTEX_HOME doit être un chemin absolu.",
        )
    bin_dir = home.resolve(strict=False) / "bin"
    if bin_dir.exists() and bin_dir.is_symlink():
        raise _coded_driver_error(
            "NATIVE_HELPER_UNAVAILABLE",
            "Le dossier des helpers Cortex ne peut pas être un lien symbolique.",
        )
    bin_dir.mkdir(parents=True, exist_ok=True)
    helper = bin_dir / MACOS_AX_HELPER_NAME
    if helper.is_symlink():
        raise _coded_driver_error(
            "NATIVE_HELPER_UNAVAILABLE",
            "Le helper Cortex ne peut pas être un lien symbolique.",
        )
    if (
        helper.is_file()
        and os.access(helper, os.X_OK)
        and helper.stat().st_mtime_ns >= source.stat().st_mtime_ns
    ):
        return helper
    temporary = bin_dir / f".{MACOS_AX_HELPER_NAME}.{uuid.uuid4().hex}.tmp"
    try:
        process = await asyncio.create_subprocess_exec(
            swiftc,
            str(source),
            "-o",
            str(temporary),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
            try:
                await asyncio.shield(process.communicate())
            except (OSError, ProcessLookupError):
                pass
            raise
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise _coded_driver_error(
                "NATIVE_HELPER_UNAVAILABLE",
                "La compilation du helper macOS a dépassé 30 secondes.",
            ) from exc
        if process.returncode != 0 or not temporary.is_file():
            raise _coded_driver_error(
                "NATIVE_HELPER_UNAVAILABLE",
                "La compilation du helper macOS a échoué.",
            )
        temporary.chmod(0o700)
        os.replace(temporary, helper)
        return helper
    finally:
        temporary.unlink(missing_ok=True)


async def activate_macos_ax_send(
    expected_url: str,
    expected_name: str,
    expected_text_hash: str,
) -> None:
    if not _SHA256_HEX.fullmatch(expected_text_hash):
        raise _coded_driver_error(
            "SEND_REJECTED",
            "L’empreinte du message préparé est invalide.",
        )
    helper = await _compile_macos_ax_helper()
    try:
        process = await asyncio.create_subprocess_exec(
            str(helper),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise _coded_driver_error(
            "NATIVE_HELPER_UNAVAILABLE",
            "Le helper macOS ne peut pas démarrer.",
        ) from exc
    try:
        request = json.dumps(
            {
                "expected_url": expected_url,
                "expected_file_name": expected_name,
                "expected_text_sha256": expected_text_hash,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(request),
            timeout=10,
        )
    except asyncio.CancelledError as exc:
        if process.returncode is None:
            process.kill()
        try:
            await asyncio.shield(process.communicate())
        except (OSError, ProcessLookupError):
            pass
        raise _coded_driver_error(
            "DELIVERY_UNCERTAIN",
            "L’activation macOS a été interrompue après son démarrage; aucune répétition automatique n’est sûre.",
        ) from exc
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise _coded_driver_error(
            "DELIVERY_UNCERTAIN",
            "L’activation macOS a démarré sans confirmation finale.",
        ) from exc
    output = stdout.decode("utf-8", errors="replace").strip()
    if process.returncode == 0 and output == "PRESS_STARTED":
        return
    if process.returncode == 3:
        raise _coded_driver_error(
            "NATIVE_PERMISSION_REQUIRED",
            "Autorise Cortex Bridge dans Réglages Système > Confidentialité et sécurité > Accessibilité, puis réessaie.",
        )
    if process.returncode == 7:
        raise _coded_driver_error(
            "DELIVERY_UNCERTAIN",
            "L’appui macOS a commencé sans preuve finale de livraison.",
        )
    native_errors = {
        2: "La requête adressée au helper macOS est invalide.",
        4: "Chrome n’est pas resté au premier plan pendant la vérification.",
        5: "L’onglet ChatGPT préparé n’est pas resté la cible active.",
        6: "Le bouton d’envoi ChatGPT exact n’est pas disponible.",
        8: "La pièce jointe préparée n’est pas visible près du bouton d’envoi.",
        9: "Le texte visible dans ChatGPT ne correspond pas au message préparé.",
        10: "Le délai de sécurité de l’accessibilité macOS n’a pas pu être appliqué.",
    }
    if process.returncode in native_errors:
        raise _coded_driver_error(
            "SEND_REJECTED",
            native_errors[process.returncode],
        )
    raise _coded_driver_error(
        "DELIVERY_UNCERTAIN",
        "Le helper macOS s’est interrompu sans état final vérifiable.",
    )


class ChromeExtensionBrowserDriver:
    driver_name = "chrome_extension"
    supports_raw_evaluation = False
    requires_content_stability = True

    def __init__(
        self,
        *,
        session: str,
        manager: ChromeExtensionManager = chrome_extension_manager,
        allowed_root: str | Path | None = None,
        retry_sleep: Callable[[float], Awaitable[None] | None] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        native_activator: Callable[[str, str, str], Awaitable[None] | None] | None = None,
        native_confirmation_timeout: float = 20.0,
    ) -> None:
        self.session = session
        self.manager = manager
        self.allowed_root = Path(allowed_root or RUNTIME_PATHS.home).expanduser().resolve()
        self._retry_sleep = retry_sleep
        self._monotonic = monotonic
        self._native_activator = native_activator or activate_macos_ax_send
        self._native_confirmation_timeout = max(0.0, native_confirmation_timeout)
        self.target_url: str | None = None
        self.selection_used_full_navigation = False
        self._closed = False
        self._release_confirmed = False
        self._release_pending = False
        self._session_receipt: dict[str, str] | None = None
        self._session_command_issued = False
        self._pending_attachment_name: str | None = None
        self._writer_reusable = True

    @property
    def live(self) -> bool:
        return not self._closed

    async def _command(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 10.0,
    ) -> Any:
        if self._closed and action != "release_session":
            raise TabClosedError("Chrome extension driver session is closed")
        deadline = self._monotonic() + timeout
        if action in SESSION_RECEIPT_ACTIONS:
            await self._ensure_session_receipt(deadline)
        unavailable_failures = 0
        recovery_attempted = False
        write_ready_deadline: float | None = None
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise DriverError(
                    f"TAB_UNAVAILABLE: ChatGPT did not become ready within {timeout:g} seconds"
                )
            try:
                command_payload = dict(payload or {})
                if action in SESSION_RECEIPT_ACTIONS:
                    # This flips before the await: cancellation after a command
                    # enters the bridge is uncertain and requires an attested
                    # remote release rather than local disposal.
                    self._session_command_issued = True
                    command_payload["session_epoch"] = self._session_receipt[
                        "session_epoch"
                    ]
                return await self.manager.command(
                    self.session,
                    action,
                    command_payload,
                    remaining,
                )
            except Exception as exc:
                code = getattr(exc, "code", None)
                recoverable_read = (
                    action in CONTENT_SCRIPT_READ_ACTIONS
                    and bool(self.target_url)
                    and not recovery_attempted
                )
                if code == "TAB_CLOSED" and recoverable_read:
                    await self._recover_read_session(deadline)
                    recovery_attempted = True
                    continue
                if code == "TAB_CLOSED":
                    raise TabClosedError(str(exc)) from exc
                safe_pre_delivery_wait = (
                    action == "send_text"
                    and (
                        code == "PRE_DELIVERY_NOT_READY"
                        or (
                            code == "TAB_UNAVAILABLE"
                            and str(exc) == CONTENT_SCRIPT_NOT_READY_MESSAGE
                        )
                    )
                )
                if safe_pre_delivery_wait:
                    now = self._monotonic()
                    if write_ready_deadline is None:
                        write_ready_deadline = min(
                            deadline,
                            now + CONTENT_SCRIPT_WRITE_READY_TIMEOUT_SECONDS,
                        )
                    if now < write_ready_deadline:
                        pending_sleep = self._retry_sleep(
                            min(
                                CONTENT_SCRIPT_RETRY_DELAY_SECONDS,
                                write_ready_deadline - now,
                            )
                        )
                        if pending_sleep is not None:
                            await pending_sleep
                        continue
                if (
                    code == "TAB_UNAVAILABLE"
                    and action in CONTENT_SCRIPT_READ_ACTIONS
                    and remaining > CONTENT_SCRIPT_RETRY_DELAY_SECONDS
                ):
                    unavailable_failures += 1
                    if (
                        recoverable_read
                        and unavailable_failures >= CONTENT_SCRIPT_RECOVERY_FAILURES
                    ):
                        await self._recover_read_session(deadline)
                        recovery_attempted = True
                        continue
                    pending_sleep = self._retry_sleep(
                        min(CONTENT_SCRIPT_RETRY_DELAY_SECONDS, remaining)
                    )
                    if pending_sleep is not None:
                        await pending_sleep
                    continue
                if code:
                    error = DriverError(f"{code}: {exc}")
                    error.code = code
                    raise error from exc
                raise

    def _session_protocol_proof(self) -> dict[str, Any]:
        getter = getattr(self.manager, "session_protocol_proof", None)
        if not callable(getter):
            raise _coded_driver_error(
                "SESSION_PROTOCOL_UNAVAILABLE",
                "Chrome extension cannot attest the session-release protocol",
            )
        proof = getter()
        if not isinstance(proof, dict):
            raise _coded_driver_error(
                "SESSION_PROTOCOL_UNAVAILABLE",
                "Chrome extension returned an invalid session protocol proof",
            )
        worker_epoch = proof.get("worker_epoch")
        capabilities = proof.get("capabilities")
        if (
            proof.get("protocol_version") != 3
            or not isinstance(worker_epoch, str)
            or not worker_epoch
            or not isinstance(capabilities, (tuple, list, set, frozenset))
            or SESSION_RECEIPT_CAPABILITY not in capabilities
        ):
            raise _coded_driver_error(
                "SESSION_PROTOCOL_UNAVAILABLE",
                "Chrome extension has not negotiated the required session-release protocol",
            )
        return {"worker_epoch": worker_epoch}

    async def _ensure_session_receipt(self, deadline: float) -> None:
        current = self._session_protocol_proof()
        if self._session_receipt is not None:
            if current["worker_epoch"] != self._session_receipt["worker_epoch"]:
                raise _coded_driver_error(
                    "SESSION_PROTOCOL_CHANGED",
                    "Chrome extension restarted; the existing session release cannot be attested",
                )
            return
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise _coded_driver_error(
                "SESSION_PROTOCOL_UNAVAILABLE",
                "No time remains to negotiate the session-release protocol",
            )
        result = await self.manager.command(self.session, "session_init", {}, remaining)
        if not isinstance(result, dict):
            raise _coded_driver_error(
                "SESSION_PROTOCOL_UNAVAILABLE",
                "Chrome extension returned an invalid session initialization receipt",
            )
        session_epoch = result.get("session_epoch")
        if (
            result.get("receipt_type") != "session_init.v1"
            or result.get("capability") != SESSION_RECEIPT_CAPABILITY
            or result.get("session") != self.session
            or result.get("worker_epoch") != current["worker_epoch"]
            or not isinstance(session_epoch, str)
            or not session_epoch
        ):
            raise _coded_driver_error(
                "SESSION_PROTOCOL_UNAVAILABLE",
                "Chrome extension could not attest the initialized session",
            )
        self._session_receipt = {
            "worker_epoch": current["worker_epoch"],
            "session_epoch": session_epoch,
        }

    def _validate_release_receipt(self, result: Any, release_request_id: str) -> None:
        receipt = self._session_receipt
        if receipt is None or not isinstance(result, dict):
            raise _coded_driver_error(
                "SESSION_RELEASE_PENDING",
                "Chrome extension did not attest the session release",
            )
        current = self._session_protocol_proof()
        if (
            current["worker_epoch"] != receipt["worker_epoch"]
            or result.get("receipt_type") != "session_release.v1"
            or result.get("capability") != SESSION_RECEIPT_CAPABILITY
            or result.get("session") != self.session
            or result.get("worker_epoch") != receipt["worker_epoch"]
            or result.get("session_epoch") != receipt["session_epoch"]
            or result.get("release_request_id") != release_request_id
            or result.get("released") is not True
            or result.get("quiescent") is not True
        ):
            raise _coded_driver_error(
                "SESSION_RELEASE_PENDING",
                "Chrome extension did not attest the session release",
            )

    async def _recover_read_session(self, deadline: float) -> None:
        remaining = deadline - self._monotonic()
        if remaining <= 0 or not self.target_url:
            raise DriverError("TAB_UNAVAILABLE: no time or canonical URL for recovery")
        try:
            await self.manager.command(
                self.session,
                "navigate",
                {
                    "url": self.target_url,
                    "session_epoch": self._session_receipt["session_epoch"],
                },
                remaining,
            )
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code:
                error = DriverError(f"{code}: {exc}")
                error.code = code
                raise error from exc
            raise

    async def navigate(self, url: str) -> None:
        self.selection_used_full_navigation = True
        # A session's first navigation opens its dedicated tab. Inside the
        # extension, tab allocations are serialized across writer sessions, so
        # this command may legitimately queue behind another writer's open on
        # the real site. Give the initial open a bounded 30 s budget; existing
        # conversation switches keep the strict 10 s contract.
        budget = 30 if self.target_url is None else 10
        result = await self._command("navigate", {"url": url}, timeout=budget)
        self.target_url = str((result or {}).get("url") or url)
        await self._wait_until_page_ready(timeout=budget, expected_url=url)

    async def _wait_until_page_ready(
        self,
        *,
        timeout: float,
        expected_url: str,
    ) -> dict[str, Any]:
        deadline = self._monotonic() + timeout
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise DriverError(
                    f"TAB_UNAVAILABLE: ChatGPT composer did not become ready within {timeout:g} seconds"
                )
            state = await self._command("get_state", timeout=remaining)
            if not isinstance(state, dict):
                raise DriverError("Chrome extension returned an invalid page state")
            if state.get("blocker") or (
                state.get("composer_present")
                and _same_chatgpt_route(state.get("url", ""), expected_url)
            ):
                return state
            pending_sleep = self._retry_sleep(
                min(CONTENT_SCRIPT_RETRY_DELAY_SECONDS, remaining)
            )
            if pending_sleep is not None:
                await pending_sleep

    async def evaluate(self, code: str, timeout: float = 30) -> Any:
        del code, timeout
        raise DriverError(
            "raw evaluation is unavailable on the Chrome extension transport"
        )

    async def list_tabs(self) -> list[dict[str, Any]]:
        result = await self._command("list_tabs", timeout=5)
        if isinstance(result, dict):
            return list(result.get("tabs") or [])
        return list(result or [])

    async def spa_navigate(self, url: str) -> bool:
        self.selection_used_full_navigation = False
        try:
            result = await self._command("spa_navigate", {"url": url}, timeout=10)
        except TabClosedError:
            # Selection is read-only at this point. Recreate the dedicated
            # tab before any user message is attempted. Do not wait for the
            # composer here: the adapter's identity poll is the authoritative
            # readiness check and shares the same absolute 10 s budget.
            result = await self._command("navigate", {"url": url}, timeout=10)
            self.target_url = str((result or {}).get("url") or url)
            self.selection_used_full_navigation = True
            return True
        except DriverError as exc:
            if getattr(exc, "code", None) != "TAB_UNAVAILABLE":
                raise
            # A fresh writer session has no tab yet. Full navigation safely
            # creates its dedicated tab; no user message is involved. The
            # adapter immediately polls the exact conversation identity, so a
            # second composer-readiness loop here only burns the same budget.
            result = await self._command("navigate", {"url": url}, timeout=10)
            self.target_url = str((result or {}).get("url") or url)
            self.selection_used_full_navigation = True
            return True
        handled = bool((result or {}).get("handled"))
        if handled:
            self.target_url = url
            return True
        # A new Cortex-owned writer tab may not have the target conversation
        # in its currently rendered sidebar. Direct navigation is still safe:
        # no user message has been prepared or activated at this point.
        result = await self._command("navigate", {"url": url}, timeout=10)
        self.target_url = str((result or {}).get("url") or url)
        self.selection_used_full_navigation = True
        return True

    async def get_state(self) -> dict[str, Any]:
        result = await self._command("get_state", timeout=10)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid page state")
        return result

    async def get_light_state(self) -> dict[str, Any]:
        result = await self._command("get_light_state", timeout=5)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid light state")
        return result

    async def _confirm_native_attachment_delivery(
        self,
        *,
        text: str,
        expected_name: str,
        before_user_message_ids: set[str],
    ) -> dict[str, Any]:
        deadline = self._monotonic() + self._native_confirmation_timeout
        expected_text = _normalized_message_text(text)
        while True:
            remaining = deadline - self._monotonic()
            if remaining < 0:
                break
            try:
                state = await self._command(
                    "get_state",
                    timeout=max(0.1, min(5.0, remaining or 0.1)),
                )
            except (DriverError, TabClosedError):
                state = {}
            for message in (state or {}).get("messages", []):
                if not isinstance(message, dict) or message.get("role") != "user":
                    continue
                message_id = str(message.get("id") or "")
                if not message_id or message_id in before_user_message_ids:
                    continue
                attachments = message.get("attachments") or []
                if not any(
                    isinstance(attachment, dict)
                    and _attachment_name_matches(
                        str(attachment.get("name") or ""),
                        expected_name,
                    )
                    for attachment in attachments
                ):
                    continue
                if expected_text and _normalized_message_text(message.get("text") or "") != expected_text:
                    continue
                if state.get("url"):
                    self.target_url = str(state["url"])
                return message
            if self._monotonic() >= deadline:
                break
            pending_sleep = self._retry_sleep(
                min(CONTENT_SCRIPT_RETRY_DELAY_SECONDS, max(0.0, remaining))
            )
            if pending_sleep is not None:
                await pending_sleep
        raise _coded_driver_error(
            "DELIVERY_UNCERTAIN",
            "La pièce jointe n’est pas visible dans un nouveau message ChatGPT.",
        )

    async def _send_native_attachment(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        text: str,
        timeout: float,
    ) -> dict[str, Any]:
        expected_name = str(payload.get("name") or "")
        self._writer_reusable = False
        result = await self._command(
            action,
            {**payload, "native_activation": True},
            timeout=timeout,
        )
        if not isinstance(result, dict) or result.get("native_activation") is not True:
            raise _coded_driver_error(
                "NATIVE_ACTIVATION_REQUIRED",
                "L’extension n’a pas préparé l’activation macOS vérifiée.",
            )
        activation_url = str(result.get("url") or "")
        activation_name = str(result.get("attachment_name") or "")
        if (
            not activation_url.startswith("https://chatgpt.com/")
            or activation_name != expected_name
        ):
            raise _coded_driver_error(
                "SEND_REJECTED",
                "La cible ChatGPT a changé avant l’activation macOS.",
            )
        expected_text_hash = _normalized_message_text_sha256(text)
        activation = self._native_activator(
            activation_url,
            expected_name,
            expected_text_hash,
        )
        if inspect.isawaitable(activation):
            await activation
        before_ids = {
            str(value)
            for value in (result.get("before_user_message_ids") or [])
            if str(value or "")
        }
        await self._confirm_native_attachment_delivery(
            text=text,
            expected_name=expected_name,
            before_user_message_ids=before_ids,
        )
        self._writer_reusable = True
        return {**result, "confirmed": True}

    async def send_message(self, text: str) -> None:
        expected_name = self._pending_attachment_name
        payload = {"text": text}
        if expected_name:
            payload["name"] = expected_name
        try:
            if expected_name:
                result = await self._send_native_attachment(
                    action="send_text",
                    payload=payload,
                    text=text,
                    timeout=60,
                )
            else:
                result = await self._command("send_text", payload, timeout=60)
            if isinstance(result, dict) and result.get("ok") is False:
                raise DriverError(str(result.get("error") or "ChatGPT send was rejected"))
        finally:
            if expected_name:
                # Once text + file activation is attempted, the attachment
                # expectation is single-use. Keeping it could bind a later
                # plain message to a stale chip after DELIVERY_UNCERTAIN.
                self._pending_attachment_name = None

    async def press_stop(self) -> None:
        await self._command("press_stop", timeout=10)

    async def focus_tab(self) -> None:
        await self._command("focus_tab", timeout=10)

    async def list_conversations(self) -> list[dict[str, Any]]:
        result = await self._command("list_conversations", timeout=10)
        if isinstance(result, dict):
            rows = result.get("conversations") or []
        else:
            rows = result or []
        return list(rows)[:50]

    async def probe(self) -> dict[str, Any]:
        result = await self._command("probe", timeout=10)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid probe")
        return result

    def capabilities(self) -> dict[str, Any]:
        return {
            "send_text": True,
            "upload_file": True,
            "upload_image": True,
            "take_screenshot": True,
            "limits": {
                "file_bytes": EXTENSION_FILE_LIMIT_BYTES,
                "image_bytes": EXTENSION_FILE_LIMIT_BYTES,
            },
        }

    def _managed_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute() or candidate.is_symlink():
            raise DriverError("attachment must be inside the managed staging directory")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise DriverError(
                "attachment must be inside the managed staging directory"
            ) from exc
        if not resolved.is_file():
            raise DriverError("staged attachment does not exist")
        return resolved

    async def upload_files(self, selector: str, paths: list[str]) -> None:
        await self.upload_files_named(selector, paths, None)

    async def upload_files_named(
        self,
        selector: str,
        paths: list[str],
        name: str | None,
    ) -> None:
        del selector
        if len(paths) != 1:
            raise DriverError("the Chrome extension accepts one attachment at a time")
        path = self._managed_file(paths[0])
        display_name = str(name or path.name).strip()
        if not display_name or Path(display_name).name != display_name:
            raise DriverError("attachment display name must be a plain filename")
        size = path.stat().st_size
        if size > EXTENSION_FILE_LIMIT_BYTES:
            raise DriverError("attachment exceeds the 25 MiB Chrome bridge limit")
        # From the first remote upload command onward, a late ChatGPT chip or
        # restored draft could contaminate the tab even if readiness fails.
        # Only a confirmed post-send message may make this writer reusable.
        self._writer_reusable = False
        transfer_id = uuid.uuid4().hex
        mime = mimetypes.guess_type(display_name)[0] or "application/octet-stream"
        await self._command(
            "attachment_begin",
            {
                "transfer_id": transfer_id,
                "name": display_name,
                "mime": mime,
                "size": size,
            },
            timeout=10,
        )
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        for offset in range(0, len(encoded), TRANSFER_CHUNK_CHARACTERS):
            await self._command(
                "attachment_chunk",
                {
                    "transfer_id": transfer_id,
                    "index": offset // TRANSFER_CHUNK_CHARACTERS,
                    "data": encoded[offset : offset + TRANSFER_CHUNK_CHARACTERS],
                },
                timeout=10,
            )
        await self._command(
            "attachment_commit",
            {"transfer_id": transfer_id},
            timeout=30,
        )
        self._pending_attachment_name = display_name

    async def await_attachment(self) -> dict[str, Any]:
        try:
            result = await self._command(
                "await_attachment",
                {"name": self._pending_attachment_name}
                if self._pending_attachment_name
                else {},
                timeout=70,
            )
        except Exception:
            self._pending_attachment_name = None
            raise
        if not isinstance(result, dict) or not result.get("ok"):
            self._pending_attachment_name = None
        return dict(result or {})

    async def send_bare(self) -> dict[str, Any]:
        expected_name = self._pending_attachment_name
        if not expected_name:
            raise DriverError("no confirmed attachment is ready for bare send")
        try:
            result = await self._send_native_attachment(
                action="send_bare",
                payload={"name": expected_name},
                text="",
                timeout=30,
            )
            return dict(result or {})
        finally:
            # A bare-send activation is never replayable: clear the local
            # expectation even when Chrome reports DELIVERY_UNCERTAIN.
            self._pending_attachment_name = None

    def _managed_destination(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise DriverError("screenshot path must be absolute")
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise DriverError("screenshot path must remain inside CORTEX_HOME") from exc
        current = resolved.parent
        while current != self.allowed_root:
            if current.is_symlink():
                raise DriverError("screenshot path must not contain symlinks")
            current = current.parent
        return resolved

    async def take_screenshot(self, path: str) -> dict[str, Any]:
        destination = self._managed_destination(path)
        if not self.target_url:
            raise DriverError("screenshot requires a selected ChatGPT target")
        result = await self._command(
            "capture_screenshot",
            {"expected_url": self.target_url},
            timeout=30,
        )
        data_url = str((result or {}).get("data_url") or "")
        prefix = "data:image/png;base64,"
        if not data_url.startswith(prefix):
            raise DriverError("Chrome extension returned an invalid screenshot")
        try:
            data = base64.b64decode(data_url[len(prefix) :], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise DriverError("Chrome extension returned invalid PNG data") from exc
        if not data.startswith(PNG_SIGNATURE):
            raise DriverError("Chrome extension screenshot is not a PNG")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, destination)
        return {
            "path": str(destination),
            "bytes": len(data),
            "tab_id": (result or {}).get("tab_id"),
        }

    async def health(self) -> dict[str, Any]:
        status = self.manager.public_status()
        if not status.get("paired"):
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "state": status.get("state", "disconnected"),
            }
        try:
            tabs = await self.list_tabs()
        except DriverError as exc:
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "state": "disconnected",
                "error": str(exc),
            }
        return {
            "connected": True,
            "tabs": len(tabs),
            "driver": self.driver_name,
            "session": self.session,
            "state": "paired",
        }

    async def list_models(self) -> dict[str, Any]:
        result = await self._command("list_models", timeout=30)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid model list")
        return {
            "current": result.get("selected") or result.get("current"),
            "models": list(result.get("models") or []),
        }

    async def select_model(self, label: str) -> str:
        result = await self._command("select_model", {"label": label}, timeout=40)
        return str((result or {}).get("selected") or label)

    async def close_tab(self) -> None:
        await self._command("close_tab", timeout=10)
        self.target_url = None

    async def close(self, *, deadline: float | None = None) -> None:
        # Closed means no further browser action is permitted.  It does not
        # mean the extension acknowledged release of this logical binding.
        self._closed = True
        self.target_url = None
        if self._release_confirmed:
            return
        if not self._session_command_issued:
            # `session_init` is protocol-only. Without a browser command the
            # driver owns no tab operation that needs a remote acknowledgement.
            self._release_pending = False
            self._release_confirmed = True
            return
        timeout = 5.0
        if deadline is not None:
            timeout = deadline - self._monotonic()
            if timeout <= 0:
                self._release_pending = True
                raise _coded_driver_error(
                    "SESSION_RELEASE_PENDING",
                    "Chrome extension release was not confirmed before the snapshot deadline",
                )
        try:
            # Release only Cortex's logical binding. The Chrome tab remains
            # open and can be reused by the next writer session; close_tab is
            # still reserved for an explicit user action.
            if self._session_receipt is None:
                raise _coded_driver_error(
                    "SESSION_RELEASE_PENDING",
                    "Chrome extension session proof is unavailable for release",
                )
            release_request_id = uuid.uuid4().hex
            result = await self._command(
                "release_session",
                {
                    "reusable": self._writer_reusable,
                    "session_epoch": self._session_receipt["session_epoch"],
                    "release_request_id": release_request_id,
                },
                timeout=timeout,
            )
            self._validate_release_receipt(result, release_request_id)
        except BaseException:
            self._release_pending = True
            raise
        self._release_pending = False
        self._release_confirmed = True

    async def close_with_deadline(self, deadline: float) -> None:
        await self.close(deadline=deadline)

    async def open_login(self) -> dict[str, Any]:
        deadline = self._monotonic() + OPEN_LOGIN_BUDGET_SECONDS
        opened = await self._command(
            "open_chatgpt",
            timeout=max(0.001, deadline - self._monotonic()),
        )
        self.target_url = str((opened or {}).get("url") or "https://chatgpt.com/")
        last_error: DriverError | None = None
        last_probe: dict[str, Any] | None = None

        def connection_payload(probe: dict[str, Any]) -> dict[str, Any]:
            return {
                "connected": True,
                "tabs": 1,
                "driver": self.driver_name,
                "session": self.session,
                "tab_id": (opened or {}).get("tab_id"),
                "window_id": (opened or {}).get("window_id"),
                "url": (opened or {}).get("url"),
                "probe": probe,
            }

        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            try:
                probe = await self._command("probe", timeout=remaining)
                if not isinstance(probe, dict):
                    raise DriverError("Chrome extension returned an invalid probe")
                last_probe = probe
                blocker = str(probe.get("blocker") or "").lower()
                failures = {
                    str(value).lower() for value in probe.get("failures") or []
                }
                if (
                    probe.get("ok") is True
                    and probe.get("composer_present") is True
                ) or blocker in {"login", "captcha", "rate_limit"} or failures.intersection(
                    {"login", "captcha", "rate_limit"}
                ):
                    return connection_payload(probe)
            except DriverError as exc:
                last_error = exc
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            pending_sleep = self._retry_sleep(
                min(CONTENT_SCRIPT_RETRY_DELAY_SECONDS, remaining)
            )
            if pending_sleep is not None:
                await pending_sleep
        if last_probe is not None:
            return connection_payload(last_probe)
        if last_error is not None:
            error_code = getattr(last_error, "code", None) or str(last_error).split(":", 1)[0]
            if error_code not in OPEN_LOGIN_LOADING_ERROR_CODES:
                raise last_error
        return connection_payload(
            {
                "ok": False,
                "url": self.target_url,
                "blocker": None,
                "composer_present": False,
                "failures": ["composer-missing"],
                "warnings": ["chatgpt-loading"],
            }
        )
