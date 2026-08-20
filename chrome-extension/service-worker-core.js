import { ExtensionCommandError, isChatGPTUrl } from "./protocol.js";

export const HEARTBEAT_INTERVAL_MS = 20_000;
let tabAllocationTail = Promise.resolve();
const SCREENSHOT_CAPTURE_TTL_MS = 60_000;
const MAX_REUSABLE_WRITER_TABS = 2;
const CONTENT_SCRIPT_READY_TIMEOUT_MS = 10_000;
const CONTENT_SCRIPT_RETRY_INTERVAL_MS = 150;
const DELIVERY_SENSITIVE_ACTIONS = new Set([
  "send_text",
  "send_bare",
  "attachment_begin",
  "attachment_chunk",
  "attachment_commit",
]);

export const ALLOWED_COMMANDS = new Set([
  "open_chatgpt",
  "release_session",
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

export async function findOrOpenChatGPTTab(
  chromeApi,
  cortexTab,
  excludedTabIds = new Set(),
  { focus = true } = {},
) {
  const source = requireCortexTab(cortexTab);
  const candidates = await chromeApi.tabs.query({
    windowId: source.windowId,
    url: ["https://chatgpt.com/*"],
  });
  const existing = candidates.find((tab) => (
    isChatGPTUrl(tab.url || tab.pendingUrl) && !excludedTabIds.has(tab.id)
  ));
  if (existing?.id) {
    if (focus) await chromeApi.tabs.update(existing.id, { active: true });
    return existing;
  }
  return chromeApi.tabs.create({
    windowId: source.windowId,
    index: Math.max(0, (source.index ?? 0) + 1),
    url: "https://chatgpt.com/",
    active: focus,
  });
}

async function createChatGPTTab(
  chromeApi,
  cortexTab,
  { focus = true, initialUrl = "https://chatgpt.com/" } = {},
) {
  const source = requireCortexTab(cortexTab);
  const url = isChatGPTUrl(initialUrl) ? initialUrl : "https://chatgpt.com/";
  return chromeApi.tabs.create({
    windowId: source.windowId,
    index: Math.max(0, (source.index ?? 0) + 1),
    url,
    active: focus,
  });
}

function writerTabPool(context) {
  if (!(context.reusableWriterTabs instanceof Set)) {
    context.reusableWriterTabs = new Set();
  }
  return context.reusableWriterTabs;
}

function rememberReusableWriterTab(context, tabId) {
  if (!Number.isInteger(tabId)) return;
  const pool = writerTabPool(context);
  pool.add(tabId);
  while (pool.size > MAX_REUSABLE_WRITER_TABS) {
    pool.delete(pool.values().next().value);
  }
}

async function takeReusableWriterTab(context, { focus = true } = {}) {
  const pool = writerTabPool(context);
  const boundIds = new Set(context.sessionTabs.values());
  for (const tabId of [...pool]) {
    pool.delete(tabId);
    if (boundIds.has(tabId)) continue;
    try {
      const tab = await context.chrome.tabs.get(tabId);
      if (
        tab.windowId !== requireCortexTab(context.cortexTab).windowId
        || !isChatGPTUrl(tab.url || tab.pendingUrl)
      ) {
        continue;
      }
      if (focus) await context.chrome.tabs.update(tabId, { active: true });
      return tab;
    } catch {
      // Closed or inaccessible Cortex-owned tabs are simply discarded.
    }
  }
  return null;
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

function isMissingContentScriptError(error) {
  const message = String(error?.message || error || "");
  return (
    message.includes("Could not establish connection")
    && message.includes("Receiving end does not exist")
  );
}

async function sendToContentScript(context, session, action, payload) {
  const writer = session.startsWith("cortex-conv-");
  if (
    !context.sessionTabs.has(session)
    && (!writer || action === "spa_navigate")
  ) {
    await openForSession(context, session, {
      focus: writer,
      initialUrl: action === "spa_navigate" ? payload.url : undefined,
    });
  }
  const tab = await boundTab(context, session);
  if (!isChatGPTUrl(tab.url || tab.pendingUrl)) {
    throw new ExtensionCommandError("TAB_UNAVAILABLE", "The bound tab is not ChatGPT");
  }
  const message = {
    source: "cortex-bridge-extension",
    action,
    payload,
  };
  const unwrapResponse = (response) => {
    if (!response?.ok) {
      throw new ExtensionCommandError(
        response?.error?.code || "CHATGPT_COMMAND_FAILED",
        response?.error?.message || "The ChatGPT page rejected the command",
      );
    }
    return response.result;
  };
  try {
    const response = await context.chrome.tabs.sendMessage(tab.id, message);
    return unwrapResponse(response);
  } catch (error) {
    if (error instanceof ExtensionCommandError) throw error;
    if (
      DELIVERY_SENSITIVE_ACTIONS.has(action)
      && !isMissingContentScriptError(error)
    ) {
      throw new ExtensionCommandError(
        "DELIVERY_UNCERTAIN",
        "The ChatGPT command channel closed before delivery could be confirmed",
      );
    }
    if (action !== "probe" || typeof context.chrome.tabs.reload !== "function") {
      throw new ExtensionCommandError(
        "TAB_UNAVAILABLE",
        "The ChatGPT content script is not available yet",
      );
    }
  }

  try {
    await context.chrome.tabs.reload(tab.id);
  } catch {
    throw new ExtensionCommandError(
      "TAB_UNAVAILABLE",
      "The ChatGPT tab could not be reloaded",
    );
  }

  const deadline = Date.now() + CONTENT_SCRIPT_READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const response = await context.chrome.tabs.sendMessage(tab.id, message);
      return unwrapResponse(response);
    } catch (error) {
      if (error instanceof ExtensionCommandError) throw error;
    }
    await new Promise((resolve) => {
      setTimeout(resolve, CONTENT_SCRIPT_RETRY_INTERVAL_MS);
    });
  }
  throw new ExtensionCommandError(
    "TAB_UNAVAILABLE",
    "The ChatGPT content script did not become available within 10 seconds",
  );
}

async function captureViaDebugger(chromeApi, tab) {
  const debuggerApi = chromeApi.debugger;
  if (!debuggerApi?.attach || !debuggerApi?.sendCommand) {
    throw new ExtensionCommandError(
      "SCREENSHOT_PERMISSION_REQUIRED",
      "Click the Cortex Bridge extension icon on the ChatGPT tab, then retry within 60 seconds",
    );
  }
  try {
    await debuggerApi.attach({ tabId: tab.id }, "1.3");
  } catch (error) {
    throw new ExtensionCommandError(
      "SCREENSHOT_CAPTURE_FAILED",
      `Chrome debugger attach failed: ${String(error?.message || error)}`,
    );
  }
  try {
    const result = await debuggerApi.sendCommand(
      { tabId: tab.id },
      "Page.captureScreenshot",
      { format: "png" },
    );
    if (typeof result?.data !== "string" || result.data.length === 0) {
      throw new ExtensionCommandError(
        "SCREENSHOT_CAPTURE_FAILED",
        "Chrome debugger returned no screenshot data",
      );
    }
    return `data:image/png;base64,${result.data}`;
  } finally {
    try {
      await debuggerApi.detach({ tabId: tab.id });
    } catch {
      // Detach is best effort: Chrome drops the session with the tab anyway.
    }
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

async function activateChatGPTSend(context, session, payload) {
  try {
    await sendToContentScript(context, session, "prepare_text", payload);
  } catch (error) {
    if (
      error instanceof ExtensionCommandError
      && ["COMPOSER_MISSING", "COMPOSER_INPUT_FAILED", "SEND_REJECTED"].includes(error.code)
    ) {
      throw new ExtensionCommandError(
        "PRE_DELIVERY_NOT_READY",
        `${error.code}: ${error.message}`,
      );
    }
    throw error;
  }
  const tab = await boundTab(context, session);
  if (typeof context.chrome.scripting?.executeScript !== "function") {
    throw new ExtensionCommandError(
      "TRUSTED_INPUT_UNAVAILABLE",
      "Chrome scripting support is unavailable for ChatGPT activation",
    );
  }
  let executions;
  let activationError = null;
  try {
    executions = await context.chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      func: () => {
        const selectors = [
          "button[data-testid=send-button]",
          "button[aria-label*='Send']",
          "button[aria-label*='Envoyer']",
        ];
        const button = selectors
          .map((selector) => document.querySelector(selector))
          .find((candidate) => (
            candidate instanceof HTMLButtonElement
            && !candidate.disabled
            && candidate.getClientRects().length > 0
          ));
        if (!button) return { ok: false, error: "send control unavailable" };
        button.click();
        return { ok: true };
      },
    });
  } catch (error) {
    activationError = error;
  }
  const activation = executions?.[0]?.result;
  if (activation?.ok) return { ok: true };
  if (activation && activation.ok === false) {
    throw new ExtensionCommandError(
      "SEND_REJECTED",
      activation?.error || "ChatGPT rejected the send activation",
    );
  }

  // On a brand-new chat, a successful click can immediately replace `/`
  // with `/c/<id>`. Chrome then rejects executeScript because the document
  // that ran the click disappeared before its result crossed the extension
  // boundary. Never click again: prove delivery from the newly rendered user
  // message, or fail closed as DELIVERY_UNCERTAIN.
  const marker = String(payload?.text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => !line.startsWith("```") && line.length >= 8)
    ?.slice(0, 60) || "";
  const confirmationTimeout = Number.isFinite(context.activationConfirmationTimeoutMs)
    ? Math.max(0, context.activationConfirmationTimeoutMs)
    : 10_000;
  const deadline = Date.now() + confirmationTimeout;
  while (marker && Date.now() <= deadline) {
    try {
      const state = await sendToContentScript(context, session, "get_state", {});
      const visibleUserMessage = (state?.messages || []).some((message) => (
        message?.role === "user"
        && `${message?.text || ""} ${(message?.code_blocks || [])
          .map((block) => block?.text || "")
          .join(" ")}`.includes(marker)
      ));
      if (visibleUserMessage) return { ok: true, confirmed_after_navigation: true };
    } catch {
      // The new document may not have received its content script yet.
    }
    if (Date.now() >= deadline) break;
    await new Promise((resolve) => {
      setTimeout(resolve, CONTENT_SCRIPT_RETRY_INTERVAL_MS);
    });
  }
  void activationError;
  throw new ExtensionCommandError(
    "DELIVERY_UNCERTAIN",
    "ChatGPT activation started but no sent user message could be confirmed",
  );
}

async function openForSession(context, session, options = {}) {
  return reserveTabAllocation(() => openForSessionUnlocked(context, session, options));
}

async function openForSessionUnlocked(
  context,
  session,
  { focus = true, initialUrl = undefined } = {},
) {
  const currentTabId = context.sessionTabs.get(session);
  if (Number.isInteger(currentTabId)) {
    try {
      const current = await context.chrome.tabs.get(currentTabId);
      if (focus) await context.chrome.tabs.update(currentTabId, { active: true });
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
  if (writer) {
    const reusable = await takeReusableWriterTab(context, { focus });
    const tab = reusable || await createChatGPTTab(
      context.chrome,
      context.cortexTab,
      { focus, initialUrl },
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
  const excluded = new Set();
  for (const [boundSession, tabId] of context.sessionTabs.entries()) {
    if (boundSession.startsWith("cortex-conv-")) excluded.add(tabId);
  }
  for (const tabId of writerTabPool(context)) excluded.add(tabId);
  const tab = await findOrOpenChatGPTTab(
    context.chrome,
    context.cortexTab,
    excluded,
    { focus },
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
  if (action === "send_text") {
    return activateChatGPTSend(context, session, payload);
  }
  if (action === "release_session") {
    const tabId = context.sessionTabs.get(session);
    context.sessionTabs.delete(session);
    if (session.startsWith("cortex-conv-")) {
      rememberReusableWriterTab(context, tabId);
    }
    return {
      released: Number.isInteger(tabId),
      tab_id: Number.isInteger(tabId) ? tabId : null,
    };
  }
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
      if (comparableChatGPTUrl(tab.url || tab.pendingUrl) === comparableChatGPTUrl(payload.url)) {
        await context.chrome.tabs.update(tab.id, { active: true });
      } else {
        await context.chrome.tabs.update(tab.id, { url: payload.url, active: true });
      }
    } else {
      const opened = await openForSession(context, session);
      tab = await context.chrome.tabs.get(opened.tab_id);
      if (comparableChatGPTUrl(tab.url || tab.pendingUrl) === comparableChatGPTUrl(payload.url)) {
        await context.chrome.tabs.update(tab.id, { active: true });
      } else {
        await context.chrome.tabs.update(tab.id, { url: payload.url, active: true });
      }
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
    const captureValid = Boolean(
      capture
      && typeof capture.data_url === "string"
      && capture.data_url.startsWith("data:image/png;base64,")
      && captureAge >= 0
      && captureAge <= SCREENSHOT_CAPTURE_TTL_MS
    );
    if (!captureValid) {
      context.pendingCapture = null;
      // No fresh toolbar-click authorization: fall back to an immediate CDP
      // capture of the Cortex-bound tab (debugger permission), so unattended
      // local automation never depends on a physical icon click.
      const dataUrl = await captureViaDebugger(context.chrome, tab);
      return { data_url: dataUrl, tab_id: tab.id };
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
