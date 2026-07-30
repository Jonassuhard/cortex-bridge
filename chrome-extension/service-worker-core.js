import { ExtensionCommandError, isChatGPTUrl } from "./protocol.js";

export const HEARTBEAT_INTERVAL_MS = 20_000;
let tabAllocationTail = Promise.resolve();
const SCREENSHOT_CAPTURE_TTL_MS = 60_000;

export const ALLOWED_COMMANDS = new Set([
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
]);

function requireCortexTab(cortexTab) {
  if (!cortexTab || !Number.isInteger(cortexTab.id) || !Number.isInteger(cortexTab.windowId)) {
    throw new ExtensionCommandError(
      "EXTENSION_UNPAIRED",
      "The Cortex tab is not paired with this extension",
    );
  }
  return cortexTab;
}

function comparableChatGPTUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return `${url.origin}${url.pathname.replace(/\/+$/, "") || "/"}`;
  } catch {
    return "";
  }
}

export async function findOrOpenChatGPTTab(chromeApi, cortexTab, excludedTabIds = new Set()) {
  const source = requireCortexTab(cortexTab);
  const candidates = await chromeApi.tabs.query({
    windowId: source.windowId,
    url: ["https://chatgpt.com/*"],
  });
  const existing = candidates.find((tab) => (
    isChatGPTUrl(tab.url || tab.pendingUrl) && !excludedTabIds.has(tab.id)
  ));
  if (existing?.id) {
    await chromeApi.tabs.update(existing.id, { active: true });
    return existing;
  }
  return chromeApi.tabs.create({
    windowId: source.windowId,
    index: Math.max(0, (source.index ?? 0) + 1),
    url: "https://chatgpt.com/",
    active: true,
  });
}

async function boundTab(context, session) {
  const tabId = context.sessionTabs.get(session);
  if (!Number.isInteger(tabId)) {
    throw new ExtensionCommandError(
      "TAB_UNAVAILABLE",
      "No ChatGPT tab is bound to this Cortex session",
    );
  }
  try {
    return await context.chrome.tabs.get(tabId);
  } catch {
    context.sessionTabs.delete(session);
    throw new ExtensionCommandError("TAB_CLOSED", "The bound ChatGPT tab was closed");
  }
}

async function sendToContentScript(context, session, action, payload) {
  if (!context.sessionTabs.has(session) && !session.startsWith("cortex-conv-")) {
    await openForSession(context, session);
  }
  const tab = await boundTab(context, session);
  if (!isChatGPTUrl(tab.url || tab.pendingUrl)) {
    throw new ExtensionCommandError("TAB_UNAVAILABLE", "The bound tab is not ChatGPT");
  }
  try {
    const response = await context.chrome.tabs.sendMessage(tab.id, {
      source: "cortex-bridge-extension",
      action,
      payload,
    });
    if (!response?.ok) {
      throw new ExtensionCommandError(
        response?.error?.code || "CHATGPT_COMMAND_FAILED",
        response?.error?.message || "The ChatGPT page rejected the command",
      );
    }
    return response.result;
  } catch (error) {
    if (error instanceof ExtensionCommandError) throw error;
    throw new ExtensionCommandError(
      "TAB_UNAVAILABLE",
      "The ChatGPT content script is not available yet",
    );
  }
}

async function reserveTabAllocation(work) {
  const previous = tabAllocationTail;
  let release;
  tabAllocationTail = new Promise((resolve) => {
    release = resolve;
  });
  await previous;
  try {
    return await work();
  } finally {
    release();
  }
}

async function openForSession(context, session) {
  return reserveTabAllocation(() => openForSessionUnlocked(context, session));
}

async function openForSessionUnlocked(context, session) {
  const currentTabId = context.sessionTabs.get(session);
  if (Number.isInteger(currentTabId)) {
    try {
      const current = await context.chrome.tabs.get(currentTabId);
      await context.chrome.tabs.update(currentTabId, { active: true });
      return {
        tab_id: currentTabId,
        window_id: current.windowId,
        url: current.url || current.pendingUrl || "https://chatgpt.com/",
      };
    } catch {
      context.sessionTabs.delete(session);
    }
  }
  const writer = session.startsWith("cortex-conv-");
  const excluded = new Set();
  for (const [boundSession, tabId] of context.sessionTabs.entries()) {
    if (writer || boundSession.startsWith("cortex-conv-")) excluded.add(tabId);
  }
  const tab = await findOrOpenChatGPTTab(
    context.chrome,
    context.cortexTab,
    excluded,
  );
  if (!Number.isInteger(tab.id)) {
    throw new ExtensionCommandError("TAB_UNAVAILABLE", "Chrome did not create a ChatGPT tab");
  }
  context.sessionTabs.set(session, tab.id);
  return {
    tab_id: tab.id,
    window_id: tab.windowId,
    url: tab.url || tab.pendingUrl || "https://chatgpt.com/",
  };
}

export async function routeCommand(context, command) {
  const { session, action, payload = {} } = command;
  if (!ALLOWED_COMMANDS.has(action)) {
    throw new ExtensionCommandError(
      "COMMAND_NOT_ALLOWED",
      `Chrome extension command is not allowed: ${action}`,
    );
  }
  if (!session || typeof session !== "string") {
    throw new ExtensionCommandError("INVALID_SESSION", "A Cortex session ID is required");
  }
  if (action === "open_chatgpt") return openForSession(context, session);
  if (action === "list_tabs") {
    const tabs = [];
    for (const [boundSession, tabId] of context.sessionTabs.entries()) {
      try {
        const tab = await context.chrome.tabs.get(tabId);
        tabs.push({
          session: boundSession,
          tab_id: tabId,
          window_id: tab.windowId,
          url: tab.url || tab.pendingUrl || null,
          active: Boolean(tab.active),
        });
      } catch {
        context.sessionTabs.delete(boundSession);
      }
    }
    return { tabs };
  }
  if (action === "focus_tab") {
    const tab = await boundTab(context, session);
    await context.chrome.tabs.update(tab.id, { active: true });
    return { tab_id: tab.id, window_id: tab.windowId };
  }
  if (action === "navigate") {
    if (!isChatGPTUrl(payload.url)) {
      throw new ExtensionCommandError("NAVIGATION_REJECTED", "Only chatgpt.com can be opened");
    }
    let tab;
    if (context.sessionTabs.has(session)) {
      try {
        tab = await boundTab(context, session);
      } catch (error) {
        if (error?.code !== "TAB_CLOSED") throw error;
        const opened = await openForSession(context, session);
        tab = await context.chrome.tabs.get(opened.tab_id);
      }
      await context.chrome.tabs.update(tab.id, { url: payload.url, active: true });
    } else {
      const opened = await openForSession(context, session);
      tab = await context.chrome.tabs.get(opened.tab_id);
      await context.chrome.tabs.update(tab.id, { url: payload.url, active: true });
    }
    return { tab_id: tab.id, window_id: tab.windowId, url: payload.url };
  }
  if (action === "close_tab") {
    const tab = await boundTab(context, session);
    await context.chrome.tabs.remove(tab.id);
    context.sessionTabs.delete(session);
    return { closed: true };
  }
  if (action === "capture_screenshot") {
    const tab = await boundTab(context, session);
    const capture = context.pendingCapture;
    const captureAge = Date.now() - Number(capture?.captured_at || 0);
    if (
      !capture
      || typeof capture.data_url !== "string"
      || !capture.data_url.startsWith("data:image/png;base64,")
      || captureAge < 0
      || captureAge > SCREENSHOT_CAPTURE_TTL_MS
    ) {
      context.pendingCapture = null;
      throw new ExtensionCommandError(
        "SCREENSHOT_PERMISSION_REQUIRED",
        "Click the Cortex Bridge extension icon on the ChatGPT tab, then retry within 60 seconds",
      );
    }
    if (comparableChatGPTUrl(capture.url) !== comparableChatGPTUrl(tab.url || tab.pendingUrl)) {
      throw new ExtensionCommandError(
        "SCREENSHOT_TARGET_MISMATCH",
        "The authorized screenshot belongs to a different ChatGPT conversation",
      );
    }
    context.pendingCapture = null;
    return { data_url: capture.data_url, tab_id: capture.tab_id };
  }
  return sendToContentScript(context, session, action, payload);
}
