"""Self-contained local ChatGPT-surface fixture (mission spec §22).

A stdlib-only loopback HTTP server (random port) imitating the minimum
ChatGPT interaction surface:

* conversation page at /c/<id> with a stable conversation identity;
* message list with [data-message-author-role] / [data-message-id];
* contenteditable composer + send button;
* simulated assistant streaming: the reply is appended empty, then mutates
  over ~1s while a stop button is visible; the stop button disappears and
  the message stabilizes at completion;
* switchable states: login screen, CAPTCHA placeholder, rate-limit warning;
* tab closure and transient unreadability (for uncertain-delivery tests).

Rendered-message emulation: like real ChatGPT, markdown fence MARKERS are
consumed by rendering while code content survives verbatim — state therefore
exposes per-message ``text`` (prose + bare code content) plus structured
``code_blocks: [{lang, text}]``.

Tests control the fixture through the FixtureServer Python API (scripted
reply queue, modes, streaming speed, tab closure, fail-next-state). Drivers
reach it only through HTTP, exactly like the real WebBridge daemon path.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

FENCE_RE = re.compile(r"```([A-Za-z0-9_.+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)

BLOCKER_MODES = ("login", "captcha", "rate_limit")


def render_message(raw: str) -> tuple[str, list[dict]]:
    """Emulate markdown rendering: fence markers consumed, code kept verbatim.

    Returns (rendered_text, code_blocks).
    """
    code_blocks: list[dict] = []
    out: list[str] = []
    last = 0
    for match in FENCE_RE.finditer(raw):
        out.append(raw[last : match.start()])
        code = match.group(2).rstrip("\n")
        code_blocks.append({"lang": match.group(1) or "", "text": code})
        out.append(code)  # code content stays visible inside <pre>
        last = match.end()
    out.append(raw[last:])
    return "".join(out), code_blocks


class Conversation:
    """Server-side state of one fixture conversation."""

    def __init__(self, cid: str):
        self.id = cid
        self.title = f"Fixture conversation {cid}"
        self.messages: list[dict] = []
        self.replies: list[str] = []
        self.mode = "normal"  # normal | login | captcha | rate_limit
        self.stream_chunks = 6
        self.stream_interval = 0.15
        self.streaming = False
        self._stop = False
        self._seq = 0
        self._lock = threading.Lock()

    def add_message(self, role: str, text: str) -> dict:
        with self._lock:
            self._seq += 1
            msg = {"id": f"m-{self._seq}", "role": role, "text": text}
            self.messages.append(msg)
            return msg

    def start_stream(self, full_text: str) -> dict:
        msg = self.add_message("assistant", "")
        chunks = max(1, self.stream_chunks)
        interval = self.stream_interval

        def _run():
            for i in range(1, chunks + 1):
                time.sleep(interval)
                with self._lock:
                    if self._stop:
                        self.streaming = False
                        self._stop = False
                        return  # partial text stays — generation cancelled
                    msg["text"] = full_text[: int(len(full_text) * i / chunks)]
                    self.streaming = True
            with self._lock:
                msg["text"] = full_text
                self.streaming = False

        with self._lock:
            self.streaming = True
            self._stop = False
        threading.Thread(target=_run, daemon=True).start()
        return msg

    def request_stop(self) -> None:
        with self._lock:
            self._stop = True

    def snapshot(self) -> dict:
        with self._lock:
            messages = []
            for msg in self.messages:
                rendered, code_blocks = render_message(msg["text"])
                messages.append(
                    {
                        "id": msg["id"],
                        "role": msg["role"],
                        "text": rendered,
                        "code_blocks": code_blocks,
                    }
                )
            streaming = self.streaming
        return {
            "conversation_id": self.id,
            "title": self.title,
            "blocker": None if self.mode == "normal" else self.mode,
            "composer_present": self.mode in ("normal", "rate_limit"),
            "send_button_present": self.mode in ("normal", "rate_limit"),
            "stop_button_present": streaming,
            "streaming": streaming,
            "messages": messages,
        }


_PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>ChatGPT Fixture</title></head>
<body>
<div id="app">
  <header id="conv-title">fixture</header>
  <main id="messages"></main>
  <div id="composer-wrap">
    <div id="prompt-textarea" contenteditable="true"></div>
    <button id="send-btn" type="button">Send</button>
    <button id="stop-btn" type="button" style="display:none">Stop generating</button>
  </div>
  <div id="login-wall" style="display:none"><h1>Log in to ChatGPT</h1></div>
  <div id="captcha-wall" style="display:none"><h1>Verify you are human</h1><div class="cf-chl-placeholder"></div></div>
  <div id="rate-limit-banner" style="display:none">You have reached your rate limit. Please try again later.</div>
</div>
<script>
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
async function refresh(){
  let st;
  try { st = await (await fetch('/__state')).json(); } catch(e) { return; }
  if (st.tab_closed) { document.body.innerHTML = '<h1>Tab closed</h1>'; return; }
  document.getElementById('conv-title').textContent = st.title || '';
  document.getElementById('login-wall').style.display = st.blocker === 'login' ? 'block' : 'none';
  document.getElementById('captcha-wall').style.display = st.blocker === 'captcha' ? 'block' : 'none';
  document.getElementById('rate-limit-banner').style.display = st.blocker === 'rate_limit' ? 'block' : 'none';
  document.getElementById('composer-wrap').style.display = st.composer_present ? 'block' : 'none';
  document.getElementById('stop-btn').style.display = st.stop_button_present ? 'inline-block' : 'none';
  const main = document.getElementById('messages');
  main.innerHTML = '';
  for (const m of (st.messages || [])) {
    const div = document.createElement('div');
    div.setAttribute('data-message-author-role', m.role);
    div.setAttribute('data-message-id', m.id);
    let html = esc(m.text);
    main.appendChild(div);
    div.textContent = m.text;
    for (const b of (m.code_blocks || [])) {
      const pre = document.createElement('pre');
      pre.setAttribute('data-lang', b.lang);
      const code = document.createElement('code');
      code.textContent = b.text;
      pre.appendChild(code);
      div.appendChild(pre);
    }
  }
}
document.getElementById('send-btn').addEventListener('click', async () => {
  const composer = document.getElementById('prompt-textarea');
  const text = composer.innerText;
  await fetch('/__send', {method: 'POST', body: JSON.stringify({text})});
  composer.innerText = '';
  refresh();
});
document.getElementById('stop-btn').addEventListener('click', async () => {
  await fetch('/__stop', {method: 'POST'});
  refresh();
});
setInterval(refresh, 300);
refresh();
</script>
</body></html>
"""


class FixtureServer:
    """Loopback-only fixture server on a random port."""

    def __init__(self):
        self.conversations: dict[str, Conversation] = {}
        self.current: str | None = None
        self.tab_closed = False
        self.fail_state_after = 0  # fail the Nth next /__state call (0 = never)
        self.pending_chat = False  # GET / opens a brand-new chat surface
        self.new_chat_replies: list[str] = []
        self._lock = threading.Lock()
        self.httpd: ThreadingHTTPServer | None = None
        self.port: int | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> "FixtureServer":
        server_state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _json(self, payload: dict, status: int = 200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/__health":
                    self._json({"ok": True})
                    return
                if path == "/__state":
                    with server_state._lock:
                        if server_state.fail_state_after > 0:
                            server_state.fail_state_after -= 1
                            if server_state.fail_state_after == 0:
                                self._json({"error": "state temporarily unreadable"}, status=500)
                                return
                        tab_closed = server_state.tab_closed
                        current = server_state.current
                        pending = server_state.pending_chat
                    if tab_closed:
                        self._json({"tab_closed": True})
                        return
                    if current is None:
                        if pending:
                            # Brand-new chat: surface exists, identity not yet.
                            self._json(
                                {
                                    "tab_closed": False,
                                    "url": f"{server_state.base_url}/",
                                    "conversation_id": None,
                                    "title": "New chat",
                                    "blocker": None,
                                    "composer_present": True,
                                    "send_button_present": True,
                                    "stop_button_present": False,
                                    "streaming": False,
                                    "messages": [],
                                }
                            )
                        else:
                            self._json({"tab_closed": True})
                        return
                    conv = server_state.conversations[current]
                    snap = conv.snapshot()
                    snap["tab_closed"] = False
                    snap["url"] = f"{server_state.base_url}/c/{conv.id}"
                    self._json(snap)
                    return
                if path == "/__conversations":
                    with server_state._lock:
                        convs = [
                            {
                                "url": f"{server_state.base_url}/c/{c.id}",
                                "identity": c.id,
                                "title": c.title,
                            }
                            for c in server_state.conversations.values()
                        ]
                    self._json(convs)
                    return
                if path == "/":
                    with server_state._lock:
                        server_state.pending_chat = True
                        server_state.current = None
                        server_state.tab_closed = False
                    body = _PAGE_HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path.startswith("/c/"):
                    cid = path[3:].strip("/") or "default"
                    conv = server_state.conversation(cid)
                    with server_state._lock:
                        server_state.current = conv.id
                        server_state.tab_closed = False
                    body = _PAGE_HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._json({"error": "not found"}, status=404)

            def do_POST(self):
                path = urlparse(self.path).path
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    self._json({"error": "bad json"}, status=400)
                    return
                with server_state._lock:
                    tab_closed = server_state.tab_closed
                    current = server_state.current
                    pending = server_state.pending_chat
                if tab_closed:
                    self._json({"error": "tab_closed"}, status=409)
                    return
                if current is None:
                    if not pending:
                        self._json({"error": "tab_closed"}, status=409)
                        return
                    if path == "/__send":
                        # First send on a brand-new chat assigns the identity.
                        conv = server_state.conversation(f"conv-{uuid.uuid4().hex[:8]}")
                        conv.replies.extend(server_state.new_chat_replies)
                        server_state.new_chat_replies = []
                        with server_state._lock:
                            server_state.current = conv.id
                            server_state.pending_chat = False
                        text = str(payload.get("text", ""))
                        user_msg = conv.add_message("user", text)
                        if conv.replies:
                            conv.start_stream(conv.replies.pop(0))
                        self._json({"ok": True, "user_message_id": user_msg["id"]})
                        return
                    self._json({"error": "not found"}, status=404)
                    return
                conv = server_state.conversations[current]
                if path == "/__send":
                    if conv.mode != "normal":
                        self._json({"error": conv.mode}, status=409)
                        return
                    text = str(payload.get("text", ""))
                    user_msg = conv.add_message("user", text)
                    if conv.replies:
                        conv.start_stream(conv.replies.pop(0))
                    self._json({"ok": True, "user_message_id": user_msg["id"]})
                    return
                if path == "/__stop":
                    conv.request_stop()
                    self._json({"ok": True})
                    return
                self._json({"error": "not found"}, status=404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # -- test controls (never used by drivers) ------------------------------------

    def conversation(self, cid: str) -> Conversation:
        with self._lock:
            if cid not in self.conversations:
                self.conversations[cid] = Conversation(cid)
            return self.conversations[cid]

    def set_mode(self, mode: str, cid: str | None = None) -> None:
        if mode not in ("normal", *BLOCKER_MODES):
            raise ValueError(f"unknown mode {mode!r}")
        self.conversation(cid or self.current or "default").mode = mode

    def queue_replies(self, replies: list[str], cid: str | None = None) -> None:
        self.conversation(cid or self.current or "default").replies.extend(replies)

    def queue_new_chat_replies(self, replies: list[str]) -> None:
        """Replies used for the conversation created by the first send on a
        brand-new chat surface (GET /)."""
        self.new_chat_replies.extend(replies)

    def set_streaming(self, chunks: int, interval: float, cid: str | None = None) -> None:
        conv = self.conversation(cid or self.current or "default")
        conv.stream_chunks = chunks
        conv.stream_interval = interval

    def close_tab(self) -> None:
        with self._lock:
            self.tab_closed = True

    def fail_next(self, skip: int = 0) -> None:
        """Fail the (skip+1)-th next /__state call once."""
        with self._lock:
            self.fail_state_after = skip + 1
