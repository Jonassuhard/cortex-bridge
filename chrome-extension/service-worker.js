import {
  HEARTBEAT_INTERVAL_MS,
  captureTabViaDebuggerExactly,
  ensureCortexTabGroup,
  forgetClosedTab,
  restoreQuarantinedWriterTabs,
  routeCommand,
} from "./service-worker-core.js";
import {
  commandError,
  createPairMessage,
  isChatGPTUrl,
  SESSION_RECEIPT_CAPABILITY,
} from "./protocol.js";

const SOCKET_URL = "ws://127.0.0.1:8420/api/chrome-extension/ws";
const RECONNECT_ALARM = "cortex-bridge-reconnect";
function createWorkerEpoch() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  // Chrome 116 supplies crypto.randomUUID(). This fallback only keeps the
  // worker testable in minimal JS contexts; a restart still gets a new epoch.
  return `fallback-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
const context = {
  chrome,
  workerEpoch: createWorkerEpoch(),
  cortexTab: null,
  sessionTabs: new Map(),
  reusableWriterTabs: new Set(),
  quarantinedWriterTabs: new Set(),
  pendingCapture: null,
};
const contextReady = restoreQuarantinedWriterTabs(context);

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
  const activeSocket = new WebSocket(SOCKET_URL);
  socket = activeSocket;
  activeSocket.addEventListener("open", () => {
    if (socket !== activeSocket) return;
    startHeartbeat();
    if (pendingPair) {
      send(createPairMessage(pendingPair, {
        workerEpoch: context.workerEpoch,
        capabilities: [SESSION_RECEIPT_CAPABILITY],
      }));
    }
  });
  activeSocket.addEventListener("message", async (event) => {
    if (socket !== activeSocket) return;
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
      await contextReady;
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
  activeSocket.addEventListener("close", () => {
    if (socket !== activeSocket) return;
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    socket = null;
    scheduleReconnect();
  });
  activeSocket.addEventListener("error", () => {
    if (socket !== activeSocket) return;
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    socket = null;
    activeSocket.close();
    scheduleReconnect();
  });
}

chrome.action.onClicked.addListener(async (tab) => {
  connect();
  await contextReady;
  if (
    !Number.isInteger(tab?.id)
    || !Number.isInteger(tab?.windowId)
    || !isChatGPTUrl(tab.url || tab.pendingUrl)
  ) {
    return;
  }
  try {
    const data_url = await captureTabViaDebuggerExactly(chrome, tab);
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
  void ensureCortexTabGroup(chrome, context.cortexTab);
  pendingPair = message.token;
  connect();
  if (send(createPairMessage(pendingPair, {
    workerEpoch: context.workerEpoch,
    capabilities: [SESSION_RECEIPT_CAPABILITY],
  }))) {
    sendResponse({ ok: true, state: "pairing" });
  } else {
    sendResponse({ ok: true, state: "connecting" });
  }
  return false;
});

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.alarms.create(RECONNECT_ALARM, { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  // Self-heal after a console restart: the alarm wakes the service worker
  // even when idle-killed, and connect() no-ops while the socket is alive.
  if (alarm?.name === RECONNECT_ALARM) connect();
});
chrome.tabs.onRemoved.addListener((tabId) => {
  void forgetClosedTab(context, tabId);
});
connect();
