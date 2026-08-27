import { ExtensionCommandError, isChatGPTUrl } from "./protocol.js";

export const HEARTBEAT_INTERVAL_MS = 20_000;
let tabAllocationTail = Promise.resolve();
let deliveryActivationTail = Promise.resolve();
const debuggerTabTails = new Map();
const privateCaptureTabTails = new Map();
const SCREENSHOT_CAPTURE_TTL_MS = 60_000;
const MAX_REUSABLE_WRITER_TABS = 2;
const QUARANTINED_WRITER_TABS_KEY = "quarantinedWriterTabIds";
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

export const CORTEX_GROUP_TITLE = "Cortex Bridge";
export const CORTEX_GROUP_COLOR = "blue";

// Regroupe l'onglet console et les onglets ChatGPT pilotés dans un même
// groupe d'onglets Chrome « Cortex Bridge ». Jamais bloquant : tout échec
// (onglet fermé, API indisponible) est ignoré pour ne pas casser une commande.
export async function ensureCortexTabGroup(chromeApi, cortexTab, tabIds = []) {
  try {
    if (!chromeApi?.tabs?.group || !chromeApi?.tabGroups?.update) return null;
    const ids = new Set();
    if (Number.isInteger(cortexTab?.id)) ids.add(cortexTab.id);
    for (const id of tabIds) {
      if (Number.isInteger(id)) ids.add(id);
    }
    if (!ids.size) return null;
    const tabs = [];
    for (const id of ids) {
      try {
        const tab = await chromeApi.tabs.get(id);
        if (tab?.windowId != null) tabs.push(tab);
      } catch {
        // onglet fermé entre-temps : ignoré
      }
    }
    if (!tabs.length) return null;
    const windowId = cortexTab?.windowId ?? tabs[0].windowId;
    const inWindow = tabs.filter((tab) => tab.windowId === windowId);
    if (!inWindow.length) return null;

    let groupId = inWindow.find((tab) => Number.isInteger(tab.groupId) && tab.groupId >= 0)?.groupId;
    if (!Number.isInteger(groupId) && chromeApi.tabGroups.query) {
      try {
        const groups = await chromeApi.tabGroups.query({ title: CORTEX_GROUP_TITLE, windowId });
        if (groups.length) groupId = groups[0].id;
      } catch {
        // recherche impossible : on créera un nouveau groupe
      }
    }
    const tabIdsInWindow = inWindow.map((tab) => tab.id);
    if (Number.isInteger(groupId)) {
      await chromeApi.tabs.group({ tabIds: tabIdsInWindow, groupId });
    } else {
      groupId = await chromeApi.tabs.group({
        tabIds: tabIdsInWindow,
        createProperties: { windowId },
      });
    }
    await chromeApi.tabGroups.update(groupId, {
      title: CORTEX_GROUP_TITLE,
      color: CORTEX_GROUP_COLOR,
      collapsed: false,
    });
    return groupId;
  } catch {
    return null;
  }
}

function comparableChatGPTUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return `${url.origin}${url.pathname.replace(/\/+$/, "") || "/"}`;
  } catch {
    return "";
  }
}

function canonicalAttachmentName(rawName) {
  const filename = String(rawName || "").trim();
  const dot = filename.lastIndexOf(".");
  const stem = dot > 0 ? filename.slice(0, dot) : filename;
  const extension = dot > 0 ? filename.slice(dot) : "";
  return `${stem.replace(/\((?:[0-9]+|[0-9]{8}-[0-9]{6})\)$/, "")}${extension}`;
}

function attachmentNameMatches(rawActual, rawExpected) {
  const expected = canonicalAttachmentName(rawExpected);
  return Boolean(expected) && canonicalAttachmentName(rawActual) === expected;
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

function quarantinedWriterTabPool(context) {
  if (!(context.quarantinedWriterTabs instanceof Set)) {
    context.quarantinedWriterTabs = new Set();
  }
  return context.quarantinedWriterTabs;
}

async function persistQuarantinedWriterTabs(context) {
  const storageApi = context.chrome.storage;
  if (!storageApi) return;
  const durable = storageApi.local;
  if (typeof durable?.set !== "function") {
    context.quarantinePersistenceReady = false;
    throw new ExtensionCommandError(
      "QUARANTINE_PERSIST_FAILED",
      "Chrome durable storage is unavailable for the uncertain-tab quarantine",
    );
  }
  const payload = {
    [QUARANTINED_WRITER_TABS_KEY]: [...quarantinedWriterTabPool(context)],
  };
  try {
    await durable.set(payload);
  } catch {
    context.quarantinePersistenceReady = false;
    throw new ExtensionCommandError(
      "QUARANTINE_PERSIST_FAILED",
      "Chrome could not durably quarantine the uncertain ChatGPT tab",
    );
  }
  try {
    await storageApi.session?.set?.(payload);
  } catch {
    // Session storage is only a cache; storage.local is authoritative.
  }
  context.quarantinePersistenceReady = true;
}

export async function restoreQuarantinedWriterTabs(context) {
  const storageApi = context.chrome.storage;
  if (!storageApi) return quarantinedWriterTabPool(context);
  const durable = storageApi.local;
  if (typeof durable?.get !== "function") {
    context.quarantinePersistenceReady = false;
    return quarantinedWriterTabPool(context);
  }
  const restored = new Set(quarantinedWriterTabPool(context));
  let stored;
  try {
    stored = await durable.get(QUARANTINED_WRITER_TABS_KEY);
  } catch {
    context.quarantinePersistenceReady = false;
    return restored;
  }
  for (const tabId of stored?.[QUARANTINED_WRITER_TABS_KEY] || []) {
    if (Number.isInteger(tabId)) restored.add(tabId);
  }
  try {
    const cached = await storageApi.session?.get?.(QUARANTINED_WRITER_TABS_KEY);
    for (const tabId of cached?.[QUARANTINED_WRITER_TABS_KEY] || []) {
      if (Number.isInteger(tabId)) restored.add(tabId);
    }
  } catch {
    // The durable local tombstone is sufficient.
  }
  context.quarantinePersistenceReady = true;
  context.quarantinedWriterTabs = restored;
  return restored;
}

export async function forgetClosedTab(context, tabId) {
  if (!Number.isInteger(tabId)) return;
  writerTabPool(context).delete(tabId);
  quarantinedWriterTabPool(context).delete(tabId);
  for (const [session, boundTabId] of context.sessionTabs.entries()) {
    if (boundTabId === tabId) context.sessionTabs.delete(session);
  }
  if (context.pendingCapture?.tab_id === tabId) context.pendingCapture = null;
  try {
    await persistQuarantinedWriterTabs(context);
  } catch {
    // In-memory quarantine remains authoritative until this worker stops.
  }
}

function rememberReusableWriterTab(context, tabId) {
  if (!Number.isInteger(tabId)) return;
  quarantinedWriterTabPool(context).delete(tabId);
  const pool = writerTabPool(context);
  pool.add(tabId);
  while (pool.size > MAX_REUSABLE_WRITER_TABS) {
    pool.delete(pool.values().next().value);
  }
}

async function takeReusableWriterTab(context, { focus = true } = {}) {
  const pool = writerTabPool(context);
  const quarantined = quarantinedWriterTabPool(context);
  const boundIds = new Set(context.sessionTabs.values());
  for (const tabId of [...pool]) {
    pool.delete(tabId);
    if (boundIds.has(tabId) || quarantined.has(tabId)) continue;
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
    await forgetClosedTab(context, tabId);
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

async function reserveDebuggerTab(tabId, work) {
  const previous = debuggerTabTails.get(tabId) || Promise.resolve();
  let release;
  const current = new Promise((resolve) => {
    release = resolve;
  });
  debuggerTabTails.set(tabId, current);
  await previous;
  try {
    return await work();
  } finally {
    release();
    if (debuggerTabTails.get(tabId) === current) debuggerTabTails.delete(tabId);
  }
}

async function reservePrivateCaptureTab(tabId, work) {
  const previous = privateCaptureTabTails.get(tabId) || Promise.resolve();
  let release;
  const current = new Promise((resolve) => {
    release = resolve;
  });
  privateCaptureTabTails.set(tabId, current);
  await previous;
  try {
    return await work();
  } finally {
    release();
    if (privateCaptureTabTails.get(tabId) === current) {
      privateCaptureTabTails.delete(tabId);
    }
  }
}

async function withDebuggerSession(
  chromeApi,
  tab,
  { missingCode, missingMessage, attachCode, attachMessage },
  work,
) {
  return reserveDebuggerTab(tab.id, async () => {
    const debuggerApi = chromeApi.debugger;
    if (!debuggerApi?.attach || !debuggerApi?.sendCommand || !debuggerApi?.detach) {
      throw new ExtensionCommandError(missingCode, missingMessage);
    }
    const target = { tabId: tab.id };
    try {
      await debuggerApi.attach(target, "1.3");
    } catch (error) {
      throw new ExtensionCommandError(
        attachCode,
        `${attachMessage}: ${String(error?.message || error)}`,
      );
    }
    try {
      return await work(debuggerApi, target);
    } finally {
      try {
        await debuggerApi.detach(target);
      } catch {
        // Detach is best effort: Chrome drops the session with the tab anyway.
      }
    }
  });
}

async function privateMaskCommand(chromeApi, tabId, action, payload, failureCode) {
  let response;
  try {
    response = await chromeApi.tabs.sendMessage(tabId, {
      source: "cortex-bridge-extension",
      action,
      payload,
    });
  } catch (error) {
    throw new ExtensionCommandError(
      failureCode,
      `ChatGPT private capture control is unavailable: ${String(error?.message || error)}`,
    );
  }
  if (!response?.ok) {
    throw new ExtensionCommandError(
      failureCode,
      response?.error?.message || "ChatGPT rejected the private capture mask",
    );
  }
  return response.result;
}

async function forceRestorePrivateMask(chromeApi, tabId, token) {
  if (typeof chromeApi.scripting?.executeScript !== "function") return false;
  try {
    const executions = await chromeApi.scripting.executeScript({
      target: { tabId },
      args: [{ token }],
      func: ({ token: expectedToken }) => {
        const roots = Array.from(document.querySelectorAll(
          "[data-cortex-private-capture-mask]",
        ));
        for (const root of roots) {
          if (root.getAttribute("data-cortex-private-capture-mask") === expectedToken) {
            root.remove();
          }
        }
        return {
          restored: !Array.from(document.querySelectorAll(
            "[data-cortex-private-capture-mask]",
          )).some((root) => (
            root.getAttribute("data-cortex-private-capture-mask") === expectedToken
          )),
        };
      },
    });
    return executions?.some((execution) => execution?.result?.restored === true) === true;
  } catch {
    return false;
  }
}

async function withPrivateCaptureMaskUnlocked(chromeApi, tab, capture) {
  let mask;
  try {
    mask = await privateMaskCommand(
      chromeApi,
      tab.id,
      "privacy_mask_begin",
      {},
      "SCREENSHOT_PRIVACY_MASK_FAILED",
    );
  } catch (error) {
    if (error instanceof ExtensionCommandError) throw error;
    throw new ExtensionCommandError(
      "SCREENSHOT_PRIVACY_MASK_FAILED",
      "ChatGPT private capture mask could not be started",
    );
  }
  if (
    mask?.confirmed !== true
    || typeof mask.token !== "string"
    || !mask.token
    || !Number.isInteger(mask.masked_zones)
    || mask.masked_zones < 1
  ) {
    throw new ExtensionCommandError(
      "SCREENSHOT_PRIVACY_MASK_FAILED",
      "ChatGPT did not confirm an opaque private-zone mask",
    );
  }

  let captureResult;
  let captureError = null;
  try {
    captureResult = await capture();
  } catch (error) {
    captureError = error;
  }

  let restored = false;
  try {
    const result = await privateMaskCommand(
      chromeApi,
      tab.id,
      "privacy_mask_restore",
      { token: mask.token },
      "SCREENSHOT_PRIVACY_RESTORE_FAILED",
    );
    restored = result?.restored === true;
  } catch {
    restored = false;
  }
  if (!restored) {
    await forceRestorePrivateMask(chromeApi, tab.id, mask.token);
    throw new ExtensionCommandError(
      "SCREENSHOT_PRIVACY_RESTORE_FAILED",
      "ChatGPT private capture mask restoration could not be attested on the same page",
    );
  }
  if (captureError) throw captureError;
  return captureResult;
}

export async function withPrivateCaptureMask(chromeApi, tab, capture) {
  return reservePrivateCaptureTab(
    tab.id,
    () => withPrivateCaptureMaskUnlocked(chromeApi, tab, capture),
  );
}

export async function captureTabViaDebuggerExactly(chromeApi, tab) {
  return withDebuggerSession(
    chromeApi,
    tab,
    {
      missingCode: "SCREENSHOT_PERMISSION_REQUIRED",
      missingMessage: "Click the Cortex Bridge extension icon on the ChatGPT tab, then retry within 60 seconds",
      attachCode: "SCREENSHOT_CAPTURE_FAILED",
      attachMessage: "Chrome debugger attach failed",
    },
    async (debuggerApi, target) => withPrivateCaptureMask(
      chromeApi,
      tab,
      async () => {
        let result;
        try {
          result = await debuggerApi.sendCommand(
            target,
            "Page.captureScreenshot",
            { format: "png" },
          );
        } catch (error) {
          throw new ExtensionCommandError(
            "SCREENSHOT_CAPTURE_FAILED",
            `Chrome debugger capture failed: ${String(error?.message || error)}`,
          );
        }
        if (typeof result?.data !== "string" || result.data.length === 0) {
          throw new ExtensionCommandError(
            "SCREENSHOT_CAPTURE_FAILED",
            "Chrome debugger returned no screenshot data",
          );
        }
        return `data:image/png;base64,${result.data}`;
      },
    ),
  );
}

function trustedInputRevalidationExpression(config) {
  const validate = ({
    point,
    expectedComparableUrl,
    expectedAttachmentName,
    expectedAttachmentLabel,
    expectedComposerText,
  }) => {
    const queryFirst = (root, selectors) => selectors
      .map((selector) => root?.querySelector?.(selector))
      .find(Boolean) || null;
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const composer = queryFirst(document, [
      "#prompt-textarea",
      "textarea[data-testid=prompt-textarea]",
      "div[contenteditable=true][data-testid=prompt-textarea]",
      "form div[contenteditable=true]",
    ]);
    const form = composer?.closest?.("form") || null;
    const button = queryFirst(form, [
      "button[data-testid=send-button]",
      "button[aria-label='Send prompt']",
      "button[aria-label='Envoyer le prompt']",
      "button[aria-label*='Send']",
      "button[aria-label*='Envoyer']",
    ]);
    const currentComparableUrl = `${location.origin}${
      String(location.pathname || "/").replace(/\/+$/, "") || "/"
    }`;
    if (
      location.origin !== "https://chatgpt.com"
      || (expectedComparableUrl && currentComparableUrl !== expectedComparableUrl)
    ) {
      return { ok: false, error: "conversation changed before trusted input" };
    }
    if (
      typeof expectedComposerText === "string"
      && normalize(composer?.value ?? composer?.innerText ?? composer?.textContent)
        !== normalize(expectedComposerText)
    ) {
      return { ok: false, error: "composer changed before trusted input" };
    }
    if (
      !(button instanceof HTMLButtonElement)
      || button.disabled
      || !button.getClientRects?.().length
    ) {
      return { ok: false, error: "send control changed before trusted input" };
    }
    const rect = button.getBoundingClientRect?.();
    const trustedPoint = rect ? {
      x: rect.left + (rect.width / 2),
      y: rect.top + (rect.height / 2),
    } : null;
    if (
      !trustedPoint
      || !Number.isFinite(trustedPoint.x)
      || !Number.isFinite(trustedPoint.y)
      || rect.width <= 0
      || rect.height <= 0
    ) {
      return { ok: false, error: "send control has no trusted input bounds" };
    }
    const hit = document.elementFromPoint?.(trustedPoint.x, trustedPoint.y) || null;
    if (!(hit === button || button.contains?.(hit))) {
      return { ok: false, error: "send control is not the trusted input target" };
    }
    if (queryFirst(form, ["[role=progressbar]", "[aria-busy=true]"])) {
      return { ok: false, error: "attachment is still processing" };
    }
    const attachmentCandidates = Array.from(form?.querySelectorAll?.([
      "[data-testid*='attachment']",
      "[data-testid*='file-chip']",
      "[data-testid*='file-thumbnail']",
      "[class*='attachment']",
      "[class*='file-chip']",
      "[role='group'][class*='file-tile'][aria-label]",
      "[data-filename]",
      "[data-file-name]",
      "[data-attachment-name]",
      "button[aria-label*='file']",
      "button[aria-label*='fichier']",
    ].join(", ")) || []);
    const fileTileClass = (node) => normalize(node?.getAttribute?.("class"));
    const isFileTileLike = (node) => fileTileClass(node).includes("file-tile");
    const isFileTile = (node) => fileTileClass(node)
      .split(" ")
      .some((token) => token === "file-tile" || token === "group/file-tile");
    const labelOf = (node) => {
      if (isFileTileLike(node)) {
        if (!isFileTile(node)) return "";
        if (node?.getAttribute?.("role") !== "group") return "";
        return normalize(node?.getAttribute?.("aria-label"));
      }
      return normalize([
        node?.getAttribute?.("data-filename"),
        node?.getAttribute?.("data-file-name"),
        node?.getAttribute?.("data-attachment-name"),
        node?.getAttribute?.("download"),
        node?.getAttribute?.("title"),
        node?.getAttribute?.("aria-label"),
        node?.innerText,
        node?.textContent,
      ].filter(Boolean).join(" "));
    };
    const expectedName = normalize(expectedAttachmentName);
    if (expectedName) {
      const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const dot = expectedName.lastIndexOf(".");
      const stem = dot > 0 ? expectedName.slice(0, dot) : expectedName;
      const extension = dot > 0 ? expectedName.slice(dot) : "";
      const matches = (node) => {
        const label = labelOf(node);
        const exactFileTile = isFileTileLike(node);
        const exact = new RegExp(
          `${exactFileTile ? "^" : "(?:^|\\s)"}${escape(expectedName)}${exactFileTile ? "$" : "(?:\\s|$)"}`,
        );
        const duplicate = new RegExp(
          `${exactFileTile ? "^" : "(?:^|\\s)"}${escape(stem)}\\((?:[0-9]+|[0-9]{8}-[0-9]{6})\\)${escape(extension)}${exactFileTile ? "$" : "(?:\\s|$)"}`,
        );
        return exact.test(label) || duplicate.test(label);
      };
      if (!attachmentCandidates.some((node) => matches(node))) {
        return { ok: false, error: "expected attachment changed before trusted input" };
      }
    } else if (
      expectedAttachmentLabel
      && !attachmentCandidates
        .map((node) => labelOf(node))
        .filter(Boolean)
        .includes(normalize(expectedAttachmentLabel))
    ) {
      return { ok: false, error: "staged attachment changed before trusted input" };
    }
    return { ok: true, point: trustedPoint };
  };
  return `(${validate.toString()})(${JSON.stringify(config)})`;
}

async function dispatchTrustedSendClick(
  chromeApi,
  tab,
  {
    point,
    expectedUrl = "",
    expectedAttachmentName = "",
    expectedAttachmentLabel = "",
    expectedComposerText = null,
    deadlineMs = Number.POSITIVE_INFINITY,
  },
) {
  return withDebuggerSession(
    chromeApi,
    tab,
    {
      missingCode: "SEND_REJECTED",
      missingMessage: "Chrome trusted input is unavailable before delivery",
      attachCode: "SEND_REJECTED",
      attachMessage: "Chrome trusted input attach failed before delivery",
    },
    async (debuggerApi, target) => {
      const evaluateValidation = async (candidatePoint) => {
        try {
          return await debuggerApi.sendCommand(target, "Runtime.evaluate", {
            expression: trustedInputRevalidationExpression({
              point: candidatePoint,
              expectedComparableUrl: comparableChatGPTUrl(expectedUrl),
              expectedAttachmentName,
              expectedAttachmentLabel,
              expectedComposerText,
            }),
            returnByValue: true,
          });
        } catch (error) {
          throw new ExtensionCommandError(
            "SEND_REJECTED",
            `ChatGPT trusted input revalidation failed before delivery: ${String(error?.message || error)}`,
          );
        }
      };
      const reacquireValidation = async (candidatePoint) => {
        let latestValidation;
        let latestResult;
        // React can replace the enabled send button for a few frames after
        // focus or hover. Reacquire only that transient condition. Route,
        // hit-target, attachment and deadline failures remain fail-closed.
        for (let attempt = 0; attempt < 10; attempt += 1) {
          latestValidation = await evaluateValidation(candidatePoint);
          latestResult = latestValidation?.result?.value;
          if (
            latestResult?.ok
            || latestResult?.error !== "send control changed before trusted input"
          ) {
            break;
          }
          if (Date.now() + 50 >= deadlineMs) {
            throw new ExtensionCommandError(
              "PRE_DELIVERY_NOT_READY",
              "The trusted activation deadline expired while reacquiring the send control",
            );
          }
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
        return { validation: latestValidation, result: latestResult };
      };
      let {
        validation,
        result: validationResult,
      } = await reacquireValidation(point);
      if (!validationResult?.ok) {
        throw new ExtensionCommandError(
          "SEND_REJECTED",
          validationResult?.error || "ChatGPT send control changed before delivery",
        );
      }
      const pointFrom = (result, fallback) => {
        const candidate = result?.point;
        return candidate
          && Number.isFinite(candidate.x)
          && Number.isFinite(candidate.y)
          ? { x: candidate.x, y: candidate.y }
          : fallback;
      };
      const samePoint = (left, right) => (
        Math.abs(left.x - right.x) <= 0.5
        && Math.abs(left.y - right.y) <= 0.5
      );
      let trustedPoint = pointFrom(validationResult, point);
      let pointerStable = false;
      try {
        // Match a real pointer sequence. The hover transition may rerender
        // or move a large mission composer. Reacquire the verified button
        // centre until it is stable before crossing the mousePressed delivery
        // boundary. A moving target is rejected without any click.
        for (let attempt = 0; attempt < 10; attempt += 1) {
          await debuggerApi.sendCommand(target, "Input.dispatchMouseEvent", {
            type: "mouseMoved",
            button: "none",
            buttons: 0,
            x: trustedPoint.x,
            y: trustedPoint.y,
            clickCount: 1,
            pointerType: "mouse",
          });
          await new Promise((resolve) => setTimeout(resolve, 50));
          ({ validation, result: validationResult } = await reacquireValidation(trustedPoint));
          const hoveredValidation = validationResult;
          if (!hoveredValidation?.ok) {
            throw new ExtensionCommandError(
              "SEND_REJECTED",
              hoveredValidation?.error || "ChatGPT send control changed after pointer movement",
            );
          }
          const refreshedPoint = pointFrom(hoveredValidation, trustedPoint);
          if (samePoint(refreshedPoint, trustedPoint)) {
            trustedPoint = refreshedPoint;
            pointerStable = true;
            break;
          }
          trustedPoint = refreshedPoint;
        }
      } catch (error) {
        if (error instanceof ExtensionCommandError) throw error;
        throw new ExtensionCommandError(
          "SEND_REJECTED",
          `ChatGPT trusted pointer could not be prepared before delivery: ${String(error?.message || error)}`,
        );
      }
      if (!pointerStable) {
        throw new ExtensionCommandError(
          "SEND_REJECTED",
          "ChatGPT send control did not stabilize before trusted input",
        );
      }
      if (Date.now() >= deadlineMs) {
        throw new ExtensionCommandError(
          "PRE_DELIVERY_NOT_READY",
          "The trusted activation deadline expired before mousePressed",
        );
      }
      try {
        // From this invocation onward delivery is ambiguous: Chrome can
        // reject the command response after mousePressed reached the page.
        await debuggerApi.sendCommand(target, "Input.dispatchMouseEvent", {
          type: "mousePressed",
          button: "left",
          buttons: 1,
          x: trustedPoint.x,
          y: trustedPoint.y,
          clickCount: 1,
          pointerType: "mouse",
        });
        await debuggerApi.sendCommand(target, "Input.dispatchMouseEvent", {
          type: "mouseReleased",
          button: "left",
          buttons: 0,
          x: trustedPoint.x,
          y: trustedPoint.y,
          clickCount: 1,
          pointerType: "mouse",
        });
        return { ok: true };
      } catch (error) {
        throw new ExtensionCommandError(
          "DELIVERY_UNCERTAIN",
          `Chrome trusted input started but could not be confirmed: ${String(error?.message || error)}`,
        );
      }
    },
  );
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

async function reserveDeliveryActivation(work, deadlineMs) {
  const previous = deliveryActivationTail.catch(() => undefined);
  let release;
  const slot = new Promise((resolve) => {
    release = resolve;
  });
  deliveryActivationTail = previous.then(() => slot);
  let acquired = false;
  let timer = null;
  try {
    const remaining = deadlineMs - Date.now();
    if (remaining <= 0) {
      throw new ExtensionCommandError(
        "PRE_DELIVERY_NOT_READY",
        "The trusted activation deadline expired before this writer acquired Chrome",
      );
    }
    await Promise.race([
      previous,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new ExtensionCommandError(
          "PRE_DELIVERY_NOT_READY",
          "Another writer still owns the trusted Chrome activation",
        )), remaining);
      }),
    ]);
    acquired = true;
    if (Date.now() >= deadlineMs) {
      throw new ExtensionCommandError(
        "PRE_DELIVERY_NOT_READY",
        "The trusted activation deadline expired in the writer queue",
      );
    }
    return await work();
  } finally {
    if (timer !== null) clearTimeout(timer);
    if (acquired) {
      release();
    } else {
      previous.finally(release);
    }
  }
}

async function focusWriterTab(context, session, deadlineMs) {
  if (Date.now() >= deadlineMs) {
    throw new ExtensionCommandError(
      "PRE_DELIVERY_NOT_READY",
      "The trusted activation deadline expired before focusing ChatGPT",
    );
  }
  const tab = await boundTab(context, session);
  try {
    if (typeof context.chrome.windows?.update === "function") {
      await context.chrome.windows.update(tab.windowId, { focused: true });
    }
    await context.chrome.tabs.update(tab.id, { active: true });
    const focused = await boundTab(context, session);
    if (focused.id !== tab.id || focused.active !== true) {
      throw new Error("the bound ChatGPT tab did not become active");
    }
    return focused;
  } catch (error) {
    if (error instanceof ExtensionCommandError) throw error;
    throw new ExtensionCommandError(
      "PRE_DELIVERY_NOT_READY",
      `The exact ChatGPT writer tab could not be focused: ${String(error?.message || error)}`,
    );
  }
}

async function activateChatGPTSend(
  context,
  session,
  payload,
  { attachmentOnly = false, deadlineMs = Date.now() + 55_000 } = {},
) {
  const expectedAttachmentName = String(payload?.name || "").trim();
  if (attachmentOnly && !expectedAttachmentName) {
    throw new ExtensionCommandError(
      "SEND_REJECTED",
      "An expected attachment filename is required before sending",
    );
  }
  await focusWriterTab(context, session, deadlineMs);
  let preparation;
  try {
    preparation = await sendToContentScript(
      context,
      session,
      attachmentOnly ? "send_bare" : "prepare_text",
      payload,
    );
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
      "SEND_REJECTED",
      "Chrome scripting support is unavailable for ChatGPT activation",
    );
  }
  let executions;
  let activationError = null;
  try {
    executions = await context.chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      args: [{ expectedAttachmentName }],
      func: async ({ expectedAttachmentName: rawExpectedAttachmentName = "" } = {}) => {
        const queryFirst = (root, selectors) => selectors
          .map((selector) => root?.querySelector?.(selector))
          .find(Boolean) || null;
        const composer = () => queryFirst(document, [
          "#prompt-textarea",
          "textarea[data-testid=prompt-textarea]",
          "div[contenteditable=true][data-testid=prompt-textarea]",
          "form div[contenteditable=true]",
        ]);
        const composerForm = () => composer()?.closest?.("form") || null;
        const sendButton = () => queryFirst(
          composerForm(),
          [
            "button[data-testid=send-button]",
            "button[aria-label='Send prompt']",
            "button[aria-label='Envoyer le prompt']",
            "button[aria-label*='Send']",
            "button[aria-label*='Envoyer']",
          ],
        );
        const visible = (node) => Boolean(node?.getClientRects?.().length);
        const textOf = (node) => String(
          node?.value ?? node?.innerText ?? node?.textContent ?? "",
        ).replace(/\s+/g, " ").trim();
        const wait = (milliseconds) => new Promise((resolve) => {
          setTimeout(resolve, milliseconds);
        });
        const attachmentCandidates = () => Array.from(
          composerForm()?.querySelectorAll?.([
            "[data-testid*='attachment']",
            "[data-testid*='file-chip']",
            "[data-testid*='file-thumbnail']",
            "[class*='attachment']",
            "[class*='file-chip']",
            "[role='group'][class*='file-tile'][aria-label]",
            "[data-filename]",
            "[data-file-name]",
            "[data-attachment-name]",
            "button[aria-label*='file']",
            "button[aria-label*='fichier']",
          ].join(", ")) || [],
        );
        const normalizeAttachmentText = (value) => String(value || "")
          .replace(/\s+/g, " ")
          .trim();
        const expectedAttachmentName = normalizeAttachmentText(rawExpectedAttachmentName);
        const fileTileClass = (node) => normalizeAttachmentText(
          node?.getAttribute?.("class"),
        );
        const isFileTileLike = (node) => fileTileClass(node).includes("file-tile");
        const isFileTile = (node) => fileTileClass(node)
          .split(" ")
          .some((token) => token === "file-tile" || token === "group/file-tile");
        const attachmentLabel = (node) => {
          if (isFileTileLike(node)) {
            if (!isFileTile(node)) return "";
            if (node?.getAttribute?.("role") !== "group") return "";
            return normalizeAttachmentText(node?.getAttribute?.("aria-label"));
          }
          return normalizeAttachmentText([
            node?.getAttribute?.("data-filename"),
            node?.getAttribute?.("data-file-name"),
            node?.getAttribute?.("data-attachment-name"),
            node?.getAttribute?.("download"),
            node?.getAttribute?.("title"),
            node?.getAttribute?.("aria-label"),
            node?.innerText,
            node?.textContent,
          ].filter(Boolean).join(" "));
        };
        const attachmentLabelMatches = (node) => {
          if (!expectedAttachmentName) return true;
          const label = attachmentLabel(node);
          const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          const exactFileTile = isFileTileLike(node);
          if (new RegExp(
            `${exactFileTile ? "^" : "(?:^|\\s)"}${escape(expectedAttachmentName)}${exactFileTile ? "$" : "(?:\\s|$)"}`,
          ).test(label)) return true;
          const dot = expectedAttachmentName.lastIndexOf(".");
          const stem = dot > 0
            ? expectedAttachmentName.slice(0, dot)
            : expectedAttachmentName;
          const extension = dot > 0 ? expectedAttachmentName.slice(dot) : "";
          return new RegExp(
            `${exactFileTile ? "^" : "(?:^|\\s)"}${escape(stem)}\\((?:[0-9]+|[0-9]{8}-[0-9]{6})\\)${escape(extension)}${exactFileTile ? "$" : "(?:\\s|$)"}`,
          ).test(label);
        };
        const expectedAttachment = () => attachmentCandidates()
          .find((candidate) => attachmentLabelMatches(candidate)) || null;

        const initialComposer = composer();
        const initialText = textOf(initialComposer);
        const button = sendButton();
        if (
          !(button instanceof HTMLButtonElement)
          || button.disabled
          || !visible(button)
          || (expectedAttachmentName && !expectedAttachment())
        ) {
          return {
            ok: false,
            activation_started: false,
            error: "send control unavailable",
          };
        }

        // Blurring ProseMirror is part of its React commit. With an uploaded
        // file the enabled button can appear one task before that commit is
        // actually ready to consume a click, so wait for stable live nodes.
        button.focus({ preventScroll: true });
        let stableChecks = 0;
        let committedButton = null;
        for (let attempt = 0; attempt < 20; attempt += 1) {
          await wait(50);
          const candidate = sendButton();
          const currentComposer = composer();
          const progress = queryFirst(
            composerForm(),
            ["[role=progressbar]", "[aria-busy=true]"],
          );
          if (
            candidate instanceof HTMLButtonElement
            && !candidate.disabled
            && visible(candidate)
            && currentComposer
            && !progress
            && (!initialText || textOf(currentComposer) === initialText)
            && (!expectedAttachmentName || expectedAttachment())
          ) {
            stableChecks += 1;
            committedButton = candidate;
            if (stableChecks >= 3) break;
          } else {
            stableChecks = 0;
            committedButton = null;
          }
        }
        if (!committedButton) {
          return {
            ok: false,
            activation_started: false,
            error: "send control did not stabilize after composer commit",
          };
        }

        if (expectedAttachmentName) {
          const committedComposer = composer();
          committedComposer?.focus?.({ preventScroll: true });
          await wait(50);
          const candidate = sendButton();
          const progress = queryFirst(
            composerForm(),
            ["[role=progressbar]", "[aria-busy=true]"],
          );
          if (
            !(candidate instanceof HTMLButtonElement)
            || candidate.disabled
            || !visible(candidate)
            || !committedComposer
            || document.activeElement !== committedComposer
            || progress
            || !expectedAttachment()
            || (initialText && textOf(committedComposer) !== initialText)
          ) {
            return {
              ok: false,
              activation_started: false,
              error: "attachment composer did not remain ready for keyboard activation",
            };
          }
          committedButton = candidate;
        }

        const rect = committedButton.getBoundingClientRect?.();
        const point = rect ? {
          x: rect.left + (rect.width / 2),
          y: rect.top + (rect.height / 2),
        } : null;
        if (
          !point
          || !Number.isFinite(point.x)
          || !Number.isFinite(point.y)
          || rect.width <= 0
          || rect.height <= 0
        ) {
          return {
            ok: false,
            activation_started: false,
            error: "send control has no dispatchable bounds",
          };
        }
        return {
          ok: true,
          activation_started: false,
          point,
          url: location.href,
          composer_text: initialText,
          attachment_label: attachmentCandidates()
            .map((candidate) => attachmentLabel(candidate))
            .find(Boolean) || "",
        };
      },
    });
  } catch (error) {
    throw new ExtensionCommandError(
      "SEND_REJECTED",
      `ChatGPT send control could not be prepared before delivery: ${String(error?.message || error)}`,
    );
  }
  const activation = executions?.[0]?.result;
  if (
    activation?.ok
    && expectedAttachmentName
    && payload?.native_activation === true
  ) {
    return {
      ok: true,
      native_activation: true,
      url: activation.url || tab.url || tab.pendingUrl || "https://chatgpt.com/",
      attachment_name: expectedAttachmentName,
      before_user_message_ids: Array.isArray(preparation?.user_message_ids)
        ? preparation.user_message_ids.map((value) => String(value || "")).filter(Boolean)
        : [],
    };
  }
  if (activation?.ok && expectedAttachmentName) {
    throw new ExtensionCommandError(
      "SEND_REJECTED",
      "A verified native activation is required for ChatGPT attachments",
    );
  }
  if (activation?.ok) {
    await focusWriterTab(context, session, deadlineMs);
    const point = activation.point;
    if (
      !point
      || !Number.isFinite(point.x)
      || !Number.isFinite(point.y)
    ) {
      throw new ExtensionCommandError(
        "SEND_REJECTED",
        "ChatGPT send control returned no trusted input coordinates",
      );
    }
    try {
      return await dispatchTrustedSendClick(context.chrome, tab, {
        point,
        expectedUrl: activation.url || tab.url || tab.pendingUrl || "",
        expectedAttachmentName,
        expectedAttachmentLabel: activation.attachment_label || "",
        expectedComposerText: typeof activation.composer_text === "string"
          ? activation.composer_text
          : null,
        deadlineMs,
      });
    } catch (error) {
      if (!(error instanceof ExtensionCommandError) || error.code !== "DELIVERY_UNCERTAIN") {
        throw error;
      }
      activationError = error;
    }
  }
  if (activation?.activation_started) {
    activationError = new ExtensionCommandError(
      "DELIVERY_UNCERTAIN",
      activation?.error || "ChatGPT send activation could not be confirmed",
    );
  }
  if (activation && activation.ok === false) {
    throw new ExtensionCommandError(
      "SEND_REJECTED",
      activation?.error || "ChatGPT rejected the send activation",
    );
  }
  if (!activationError) {
    throw new ExtensionCommandError(
      "SEND_REJECTED",
      "ChatGPT send control returned no pre-delivery result",
    );
  }

  // A debugger command can lose its response after mousePressed reached the
  // page, especially during a new-chat navigation. Never click again: prove
  // delivery from a new rendered user message or remain uncertain.
  const markerCandidates = String(payload?.text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("```"));
  const marker = (
    markerCandidates.find((line) => line.length >= 8)
    || markerCandidates[0]
    || ""
  ).slice(0, 60).replace(/\s+/g, " ").trim();
  const beforeUserMessageIds = Array.isArray(preparation?.user_message_ids)
    ? new Set(preparation.user_message_ids.map((value) => String(value || "")))
    : null;
  const confirmationTimeout = Number.isFinite(context.activationConfirmationTimeoutMs)
    ? Math.max(0, context.activationConfirmationTimeoutMs)
    : 10_000;
  const deadline = Date.now() + confirmationTimeout;
  while ((marker || expectedAttachmentName) && Date.now() <= deadline) {
    try {
      const state = await sendToContentScript(context, session, "get_state", {});
      const visibleUserMessage = (state?.messages || []).some((message) => {
        if (message?.role !== "user") return false;
        const id = String(message?.id || "");
        if (beforeUserMessageIds && (!id || beforeUserMessageIds.has(id))) return false;
        if (expectedAttachmentName) {
          return Boolean(
            Array.isArray(message?.attachments)
            && message.attachments.some((attachment) => (
              attachment
              && typeof attachment === "object"
              && attachmentNameMatches(attachment.name, expectedAttachmentName)
            )),
          );
        }
        const visibleText = `${message?.text || ""} ${(message?.code_blocks || [])
          .map((block) => block?.text || "")
          .join(" ")}`.replace(/\s+/g, " ").trim();
        return marker.length >= 8
          ? visibleText.includes(marker)
          : visibleText === marker;
      });
      if (visibleUserMessage) return { ok: true, confirmed_after_navigation: true };
    } catch {
      // The new document may not have received its content script yet.
    }
    if (Date.now() >= deadline) break;
    await new Promise((resolve) => {
      setTimeout(resolve, CONTENT_SCRIPT_RETRY_INTERVAL_MS);
    });
  }
  throw new ExtensionCommandError(
    "DELIVERY_UNCERTAIN",
    activationError?.message
      || "ChatGPT activation started but no sent user message could be confirmed",
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
      void ensureCortexTabGroup(context.chrome, context.cortexTab, [currentTabId]);
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
    void ensureCortexTabGroup(context.chrome, context.cortexTab, [tab.id]);
    return {
      tab_id: tab.id,
      window_id: tab.windowId,
      url: tab.url || tab.pendingUrl || "https://chatgpt.com/",
    };
  }
  if (context.quarantinePersistenceReady === false) {
    throw new ExtensionCommandError(
      "QUARANTINE_STATE_UNAVAILABLE",
      "Chrome quarantine state is unavailable; reload the extension before opening a read-only tab",
    );
  }
  const excluded = new Set();
  for (const [boundSession, tabId] of context.sessionTabs.entries()) {
    if (boundSession.startsWith("cortex-conv-")) excluded.add(tabId);
  }
  for (const tabId of writerTabPool(context)) excluded.add(tabId);
  for (const tabId of quarantinedWriterTabPool(context)) excluded.add(tabId);
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
  void ensureCortexTabGroup(context.chrome, context.cortexTab, [tab.id]);
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
    const timeoutMs = Number.isFinite(Number(command.timeout_ms))
      ? Math.max(1, Math.min(60_000, Number(command.timeout_ms)))
      : 55_000;
    const deadlineMs = Date.now() + timeoutMs - 250;
    return reserveDeliveryActivation(
      () => activateChatGPTSend(context, session, payload, { deadlineMs }),
      deadlineMs,
    );
  }
  if (action === "send_bare") {
    const timeoutMs = Number.isFinite(Number(command.timeout_ms))
      ? Math.max(1, Math.min(60_000, Number(command.timeout_ms)))
      : 55_000;
    const deadlineMs = Date.now() + timeoutMs - 250;
    return reserveDeliveryActivation(
      () => activateChatGPTSend(context, session, payload, {
        attachmentOnly: true,
        deadlineMs,
      }),
      deadlineMs,
    );
  }
  if (action === "release_session") {
    const tabId = context.sessionTabs.get(session);
    if (session.startsWith("cortex-conv-") && Number.isInteger(tabId)) {
      if (payload?.reusable === false) {
        writerTabPool(context).delete(tabId);
        quarantinedWriterTabPool(context).add(tabId);
        await persistQuarantinedWriterTabs(context);
      } else {
        rememberReusableWriterTab(context, tabId);
        try {
          await persistQuarantinedWriterTabs(context);
        } catch {
          // A stale quarantine is safe: it only prevents future auto-reuse.
        }
      }
    }
    context.sessionTabs.delete(session);
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
    await forgetClosedTab(context, tab.id);
    return { closed: true };
  }
  if (action === "capture_screenshot") {
    let tab = await boundTab(context, session);
    const expectedUrl = typeof payload?.expected_url === "string"
      ? payload.expected_url
      : "";
    if (
      expectedUrl
      && comparableChatGPTUrl(tab.url || tab.pendingUrl) !== comparableChatGPTUrl(expectedUrl)
    ) {
      throw new ExtensionCommandError(
        "SCREENSHOT_TARGET_MISMATCH",
        "The selected ChatGPT tab no longer matches the requested screenshot conversation",
      );
    }
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
      const dataUrl = await captureTabViaDebuggerExactly(context.chrome, tab);
      tab = await context.chrome.tabs.get(tab.id);
      if (
        expectedUrl
        && comparableChatGPTUrl(tab.url || tab.pendingUrl) !== comparableChatGPTUrl(expectedUrl)
      ) {
        throw new ExtensionCommandError(
          "SCREENSHOT_TARGET_MISMATCH",
          "The ChatGPT conversation changed while the private screenshot was being captured",
        );
      }
      return { data_url: dataUrl, tab_id: tab.id };
    }
    if (comparableChatGPTUrl(capture.url) !== comparableChatGPTUrl(tab.url || tab.pendingUrl)) {
      context.pendingCapture = null;
      throw new ExtensionCommandError(
        "SCREENSHOT_TARGET_MISMATCH",
        "The authorized screenshot belongs to a different ChatGPT conversation",
      );
    }
    if (capture.tab_id !== tab.id) {
      context.pendingCapture = null;
      throw new ExtensionCommandError(
        "SCREENSHOT_TARGET_MISMATCH",
        "The authorized screenshot belongs to a different ChatGPT tab",
      );
    }
    context.pendingCapture = null;
    return { data_url: capture.data_url, tab_id: capture.tab_id };
  }
  return sendToContentScript(context, session, action, payload);
}
