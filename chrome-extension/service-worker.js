import {
  HEARTBEAT_INTERVAL_MS,
  routeCommand,
} from "./service-worker-core.js";
import { commandError, isChatGPTUrl } from "./protocol.js";

const SOCKET_URL = "ws://127.0.0.1:8420/api/chrome-extension/ws";
const context = {
  chrome,
  cortexTab: null,
  sessionTabs: new Map(),
  pendingCapture: null,
};

let socket = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let pendingPair = null;

function send(message) {
  if (socket?.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(message));
  return true;
}

function startHeartbeat() {
  clearInterval(heartbeatTimer);
  heartbeatTimer = setInterval(() => {
    send({ type: "bridge.heartbeat" });
  }, HEARTBEAT_INTERVAL_MS);
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, 1_500);
}

function connect() {
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
  socket = new WebSocket(SOCKET_URL);
  socket.addEventListener("open", () => {
    startHeartbeat();
    if (pendingPair) send({ type: "pair", token: pendingPair });
  });
  socket.addEventListener("message", async (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (message.type === "pair.result") {
      if (message.ok) pendingPair = null;
      return;
    }
    if (message.type !== "command") return;
    try {
      const result = await routeCommand(context, message);
      send({
        type: "command.result",
        request_id: message.request_id,
        ok: true,
        result,
      });
    } catch (error) {
      send({
        type: "command.result",
        request_id: message.request_id,
        ok: false,
        error: commandError(error),
      });
    }
  });
  socket.addEventListener("close", () => {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    socket = null;
    scheduleReconnect();
  });
  socket.addEventListener("error", () => socket?.close());
}

chrome.action.onClicked.addListener(async (tab) => {
  if (
    !Number.isInteger(tab?.id)
    || !Number.isInteger(tab?.windowId)
    || !isChatGPTUrl(tab.url || tab.pendingUrl)
  ) {
    return;
  }
  try {
    const data_url = await chrome.tabs.captureVisibleTab(tab.windowId, {
      format: "png",
    });
    context.pendingCapture = {
      data_url,
      tab_id: tab.id,
      url: tab.url || tab.pendingUrl,
      captured_at: Date.now(),
    };
  } catch {
    context.pendingCapture = null;
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (
    message?.type !== "cortex.pair"
    || message?.source !== "cortex-bridge-page"
    || !sender.tab
    || sender.tab.url?.startsWith("http://127.0.0.1:8420/") !== true
    || typeof message.token !== "string"
    || message.token.length < 43
  ) {
    return false;
  }
  context.cortexTab = {
    id: sender.tab.id,
    windowId: sender.tab.windowId,
    index: sender.tab.index,
  };
  pendingPair = message.token;
  connect();
  if (send({ type: "pair", token: pendingPair })) {
    sendResponse({ ok: true, state: "pairing" });
  } else {
    sendResponse({ ok: true, state: "connecting" });
  }
  return false;
});

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
