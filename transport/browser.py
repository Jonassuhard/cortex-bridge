"""Browser-driver contract and the single runtime transport factory."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from transport.browser_playwright import PlaywrightBrowserDriver
from transport.browser_chrome_extension import ChromeExtensionBrowserDriver
from transport.chatgpt_web.adapter import WebBridgeDriver
try:
    from cortex_paths import build_paths
except ModuleNotFoundError:  # imported as a package from the repository root
    from console.cortex_paths import build_paths


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PATHS = build_paths()
SETTINGS_FILE = RUNTIME_PATHS.settings
DEFAULT_BROWSER_SETTINGS = {
    "browser_transport": "chrome_extension",
    "browser_profile_root": str(RUNTIME_PATHS.browser_profiles),
}
ALLOWED_BROWSER_TRANSPORTS = frozenset(
    {"chrome_extension", "playwright", "webbridge"}
)


@runtime_checkable
class BrowserDriver(Protocol):
    driver_name: str
    session: str

    async def navigate(self, url: str) -> None: ...
    async def evaluate(self, code: str, timeout: float = 30) -> Any: ...
    async def list_tabs(self) -> list[dict[str, Any]]: ...
    async def upload_files(self, selector: str, paths: list[str]) -> None: ...
    async def take_screenshot(self, path: str) -> dict[str, Any]: ...
    async def health(self) -> dict[str, Any]: ...
    async def close(self) -> None: ...
    async def get_state(self) -> dict[str, Any]: ...
    async def send_message(self, text: str) -> None: ...
    async def press_stop(self) -> None: ...
    async def list_conversations(self) -> list[dict[str, Any]]: ...
    async def get_light_state(self) -> dict[str, Any]: ...
    async def spa_navigate(self, url: str) -> bool: ...
    async def probe(self) -> dict[str, Any]: ...
    def capabilities(self) -> dict[str, Any]: ...
    async def await_attachment(self) -> dict[str, Any]: ...
    async def send_bare(self) -> dict[str, Any]: ...
    async def list_models(self) -> dict[str, Any]: ...
    async def select_model(self, label: str) -> str: ...
    async def close_tab(self) -> None: ...
    async def open_login(self) -> dict[str, Any]: ...


_driver_cache: dict[tuple[str, str, str, bool | None], BrowserDriver] = {}
_driver_cache_lock = threading.Lock()


def load_browser_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings is None:
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    else:
        raw = settings
    result = {**DEFAULT_BROWSER_SETTINGS, **raw}
    transport = str(result["browser_transport"])
    if transport not in ALLOWED_BROWSER_TRANSPORTS:
        raise ValueError(
            "browser_transport must be exactly one of: chrome_extension, playwright, webbridge"
        )
    _profile_root(str(result["browser_profile_root"]))
    return result


def _profile_root(value: str | Path) -> Path:
    raw = str(value).strip()
    if not raw:
        raise ValueError("browser_profile_root must not be empty")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ValueError("browser_profile_root must be absolute")
    absolute = root.absolute()
    configured = Path(raw).expanduser()
    if configured.is_symlink():
        raise ValueError("browser_profile_root must not contain symlinks")
    resolved = absolute.resolve()
    return resolved


def create_browser_driver(
    session: str,
    settings: dict[str, Any] | None = None,
    *,
    profile_root: str | Path | None = None,
    transport_name: str | None = None,
    headless: bool | None = None,
) -> BrowserDriver:
    config = load_browser_settings(settings)
    selected = transport_name or str(config["browser_transport"])
    if selected not in ALLOWED_BROWSER_TRANSPORTS:
        raise ValueError(
            "browser_transport must be exactly one of: chrome_extension, playwright, webbridge"
        )
    if selected == "chrome_extension":
        key = (selected, "extension", session, None)
        with _driver_cache_lock:
            cached = _driver_cache.get(key)
            if cached is not None and cached.live:
                return cached
            driver = ChromeExtensionBrowserDriver(session=session)
            _driver_cache[key] = driver
            return driver
    if selected == "webbridge":
        return WebBridgeDriver(session=session)

    root = _profile_root(profile_root or str(config["browser_profile_root"]))
    key = (selected, str(root), session, headless)
    with _driver_cache_lock:
        cached = _driver_cache.get(key)
        if cached is not None and cached.live:
            return cached
        driver = PlaywrightBrowserDriver(
            session=session,
            profile_root=root,
            headless=headless,
        )
        _driver_cache[key] = driver
        return driver


def create_transport(session: str, settings: dict[str, Any] | None = None):
    from transport.chatgpt_web.adapter import ChatGPTWebTransport

    return ChatGPTWebTransport(create_browser_driver(session, settings))
