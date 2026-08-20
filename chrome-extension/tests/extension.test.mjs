import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { runInNewContext } from "node:vm";

import {
  ALLOWED_COMMANDS,
  HEARTBEAT_INTERVAL_MS,
  findOrOpenChatGPTTab,
  routeCommand,
} from "../service-worker-core.js";
import * as protocol from "../protocol.js";


const HERE = dirname(fileURLToPath(import.meta.url));
const EXTENSION_ROOT = join(HERE, "..");

test("pair envelopes attest the extension protocol generation", () => {
  assert.equal(typeof protocol.createPairMessage, "function");
  assert.deepEqual(protocol.createPairMessage("pair-token"), {
    type: "pair",
    token: "pair-token",
    protocol_version: 2,
  });
});

async function getContentScriptState(messageNodes, action = "get_state") {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");
  let listener = null;
  class FakeElement {}
  const composer = new FakeElement();
  const document = {
    body: { innerText: "" },
    title: "Regression - ChatGPT",
    querySelector(selector) {
      return selector === "#prompt-textarea" ? composer : null;
    },
    querySelectorAll(selector) {
      return selector === "[data-message-author-role]" ? messageNodes : [];
    },
  };
  const chrome = {
    runtime: {
      onMessage: {
        addListener(callback) {
          listener = callback;
        },
      },
    },
  };
  runInNewContext(source, {
    chrome,
    document,
    location: {
      href: "https://chatgpt.com/c/reasoning-status",
      origin: "https://chatgpt.com",
      pathname: "/c/reasoning-status",
    },
    Element: FakeElement,
    HTMLInputElement: class {},
    URL,
    Map,
    Promise,
    setTimeout,
    clearTimeout,
  });
  assert.equal(typeof listener, "function");
  return new Promise((resolve) => {
    listener(
      { source: "cortex-bridge-extension", action, payload: {} },
      {},
      (response) => resolve(response.result),
    );
  });
}

async function runContentScriptSend(
  text,
  {
    requiresScopedSelection = false,
    attachmentKeepsSendEnabled = false,
    focusCommitRequired = false,
    focusReplacesButton = false,
    normalizeComposerWhitespace = false,
  } = {},
) {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");
  let listener = null;
  const messageNodes = [];
  class FakeElement {
    constructor() {
      this.innerText = "";
      this.textContent = "";
      this.disabled = false;
      this.classList = [];
      this.extraInputAfterExecCommand = false;
    }

    focus() {}
    querySelector() { return null; }
    querySelectorAll() { return []; }
    getAttribute() { return null; }
    dispatchEvent() { this.extraInputAfterExecCommand = true; }
    closest() { return null; }
  }
  const composer = new FakeElement();
  const sendButton = new FakeElement();
  const replacementSendButton = new FakeElement();
  let scopedSelection = false;
  let reactCommitted = !attachmentKeepsSendEnabled && !focusCommitRequired;
  let currentSendButton = sendButton;
  sendButton.focus = () => {
    reactCommitted = true;
    if (focusReplacesButton) currentSendButton = replacementSendButton;
  };
  const clickSend = () => {
    if (!composer.extraInputAfterExecCommand && reactCommitted) {
      messageNodes.push({
        id: "user-new",
        innerText: composer.innerText,
        textContent: composer.textContent,
        classList: [],
        getAttribute(name) {
          if (name === "data-message-id") return "user-new";
          if (name === "data-message-author-role") return "user";
          return null;
        },
        querySelector() { return null; },
        querySelectorAll() { return []; },
      });
    }
    composer.innerText = "";
    composer.textContent = "";
  };
  sendButton.click = clickSend;
  replacementSendButton.click = clickSend;
  replacementSendButton.focus = () => {
    reactCommitted = true;
  };
  const document = {
    body: { innerText: "" },
    title: "Send regression - ChatGPT",
    querySelector(selector) {
      if (selector === "#prompt-textarea") return composer;
      if (selector === "button[data-testid=send-button]") {
        return attachmentKeepsSendEnabled || composer.innerText ? currentSendButton : null;
      }
      return null;
    },
    querySelectorAll(selector) {
      return selector === "[data-message-author-role]" ? messageNodes : [];
    },
    execCommand(command, _showUi, value) {
      if (command === "insertText") {
        if (requiresScopedSelection && !scopedSelection) return false;
        const renderedValue = normalizeComposerWhitespace
          ? value.replace(/\s+/g, " ").trim()
          : value;
        composer.innerText = renderedValue;
        composer.textContent = renderedValue;
      }
      return true;
    },
    createRange() {
      return {
        selectNodeContents(node) { scopedSelection = node === composer; },
        collapse() {},
      };
    },
  };
  const window = {
    getSelection() {
      return {
        removeAllRanges() {},
        addRange() {},
      };
    },
  };
  const chrome = {
    runtime: {
      onMessage: {
        addListener(callback) { listener = callback; },
      },
    },
  };
  runInNewContext(source, {
    chrome,
    document,
    window,
    location: {
      href: "https://chatgpt.com/c/send-regression",
      origin: "https://chatgpt.com",
      pathname: "/c/send-regression",
    },
    Element: FakeElement,
    HTMLTextAreaElement: class {},
    HTMLFormElement: class {},
    HTMLInputElement: class {},
    InputEvent: class {},
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    URL,
    Map,
    Promise,
    setTimeout: (callback) => {
      if (attachmentKeepsSendEnabled && composer.innerText) reactCommitted = true;
      callback();
    },
    clearTimeout,
  });
  return new Promise((resolve) => {
    listener(
      {
        source: "cortex-bridge-extension",
        action: "prepare_text",
        payload: { text },
      },
      {},
      resolve,
    );
  });
}

async function runAttachmentReadiness(label, expectedName) {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");
  let listener = null;
  class FakeElement {
    constructor(text = "") {
      this.innerText = text;
      this.textContent = text;
      this.disabled = false;
    }
    getAttribute() { return null; }
  }
  const chip = new FakeElement(label);
  const sendButton = new FakeElement();
  const document = {
    body: { innerText: "" },
    title: "Attachment regression - ChatGPT",
    querySelector(selector) {
      if (selector === "#prompt-textarea") return new FakeElement();
      if (selector === "button[data-testid=send-button]") return sendButton;
      return null;
    },
    querySelectorAll(selector) {
      return selector.includes("attachment") ? [chip] : [];
    },
  };
  const chrome = {
    runtime: {
      onMessage: {
        addListener(callback) { listener = callback; },
      },
    },
  };
  let fakeNow = 0;
  class FakeDate extends Date {
    static now() {
      fakeNow += 1_000;
      return fakeNow;
    }
  }
  runInNewContext(source, {
    chrome,
    document,
    location: {
      href: "https://chatgpt.com/c/attachment-regression",
      origin: "https://chatgpt.com",
      pathname: "/c/attachment-regression",
    },
    Element: FakeElement,
    HTMLInputElement: class {},
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    URL,
    Map,
    Promise,
    Date: FakeDate,
    setTimeout: (callback) => callback(),
    clearTimeout,
  });
  return new Promise((resolve) => {
    listener(
      {
        source: "cortex-bridge-extension",
        action: "await_attachment",
        payload: { name: expectedName },
      },
      {},
      (response) => resolve(response.result),
    );
  });
}

function chromeWithTabs(initialTabs = []) {
  const calls = { create: [], update: [], reload: [], sendMessage: [], executeScript: [] };
  const tabs = [...initialTabs];
  return {
    calls,
    api: {
      tabs: {
        async query(query) {
          return tabs.filter((tab) => tab.windowId === query.windowId);
        },
        async create(options) {
          calls.create.push(options);
          const tab = { id: 900 + calls.create.length, ...options };
          tabs.push(tab);
          return tab;
        },
        async update(tabId, options) {
          calls.update.push({ tabId, options });
          const tab = tabs.find((candidate) => candidate.id === tabId);
          if (tab && options.url) {
            tab.url = options.url;
            tab.pendingUrl = undefined;
            tab.status = "complete";
          }
          if (tab && typeof options.active === "boolean") tab.active = options.active;
          return tab;
        },
        async reload(tabId) {
          calls.reload.push(tabId);
        },
        async get(tabId) {
          const tab = tabs.find((candidate) => candidate.id === tabId);
          if (!tab) throw new Error("tab missing");
          return tab;
        },
        async sendMessage(tabId, message) {
          calls.sendMessage.push({ tabId, message });
          return { ok: true };
        },
      },
      scripting: {
        async executeScript(options) {
          calls.executeScript.push(options);
          return [{ result: { ok: true } }];
        },
      },
    },
  };
}

test("reuses a ChatGPT tab from the Cortex window", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/existing" },
    { id: 41, windowId: 8, index: 0, url: "https://chatgpt.com/c/wrong-window" },
  ]);

  const tab = await findOrOpenChatGPTTab(chrome.api, {
    id: 31,
    windowId: 7,
    index: 0,
  });

  assert.equal(tab.id, 32);
  assert.deepEqual(chrome.calls.create, []);
  assert.deepEqual(chrome.calls.update, [
    { tabId: 32, options: { active: true } },
  ]);
});

test("creates ChatGPT adjacent to Cortex without creating a window", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 2, url: "http://127.0.0.1:8420/" },
  ]);

  const tab = await findOrOpenChatGPTTab(chrome.api, {
    id: 31,
    windowId: 7,
    index: 2,
  });

  assert.equal(tab.windowId, 7);
  assert.deepEqual(chrome.calls.create, [
    {
      windowId: 7,
      index: 3,
      url: "https://chatgpt.com/",
      active: true,
    },
  ]);
});

test("routes only allowlisted structured commands", async () => {
  const chrome = chromeWithTabs();
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map(),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "read-only",
      action: "raw_evaluate",
      payload: { code: "document.cookie" },
    }),
    (error) => error.code === "COMMAND_NOT_ALLOWED",
  );
  assert.equal(ALLOWED_COMMANDS.has("raw_evaluate"), false);
});

test("gives each writer session a different ChatGPT tab", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/a" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer-a", 32]]),
  };

  const opened = await routeCommand(context, {
    session: "cortex-conv-writer-b",
    action: "open_chatgpt",
    payload: {},
  });

  assert.notEqual(opened.tab_id, 32);
  assert.equal(opened.window_id, 7);
  assert.equal(context.sessionTabs.get("cortex-conv-writer-a"), 32);
  assert.equal(context.sessionTabs.get("cortex-conv-writer-b"), opened.tab_id);
  assert.equal(chrome.calls.create.length, 1);
});

test("a new writer never takes over an unrelated personal ChatGPT tab", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/personal" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map(),
  };

  const opened = await routeCommand(context, {
    session: "cortex-conv-writer-new",
    action: "open_chatgpt",
    payload: {},
  });

  assert.notEqual(opened.tab_id, 32);
  assert.deepEqual(chrome.calls.update.filter(({ tabId }) => tabId === 32), []);
  assert.equal(chrome.calls.create.length, 1);
});

test("releasing a writer session makes its tab reusable without closing it", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/a" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer-a", 32]]),
    reusableWriterTabs: new Set(),
  };

  const released = await routeCommand(context, {
    session: "cortex-conv-writer-a",
    action: "release_session",
    payload: {},
  });
  const opened = await routeCommand(context, {
    session: "cortex-conv-writer-b",
    action: "open_chatgpt",
    payload: {},
  });

  assert.deepEqual(released, { released: true, tab_id: 32 });
  assert.equal(context.sessionTabs.has("cortex-conv-writer-a"), false);
  assert.equal(opened.tab_id, 32);
  assert.equal(context.reusableWriterTabs.size, 0);
  assert.deepEqual(chrome.calls.create, []);
});

test("an unbound writer gets a dedicated tab before attempting ChatGPT SPA selection", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/loaded" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map(),
  };

  await routeCommand(context, {
    session: "cortex-conv-writer-spa",
    action: "spa_navigate",
    payload: { url: "https://chatgpt.com/c/target" },
  });

  assert.notEqual(context.sessionTabs.get("cortex-conv-writer-spa"), 32);
  assert.equal(chrome.calls.create.length, 1);
  assert.equal(chrome.calls.create[0].url, "https://chatgpt.com/c/target");
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "spa_navigate",
  ]);
});

test("navigation does not reload a tab already at the requested conversation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    {
      id: 32,
      windowId: 7,
      index: 1,
      url: "https://chatgpt.com/c/target",
      status: "complete",
    },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer-target", 32]]),
  };

  await routeCommand(context, {
    session: "cortex-conv-writer-target",
    action: "navigate",
    payload: { url: "https://chatgpt.com/c/target" },
  });

  assert.deepEqual(chrome.calls.update, [
    { tabId: 32, options: { active: true } },
  ]);
});

test("an unbound writer still cannot send before conversation selection", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/loaded" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map(),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-writer-unselected",
      action: "send_text",
      payload: { text: "must not be sent" },
    }),
    (error) => error.code === "TAB_UNAVAILABLE",
  );
  assert.equal(context.sessionTabs.has("cortex-conv-writer-unselected"), false);
  assert.deepEqual(chrome.calls.sendMessage, []);
});

test("concurrent writer allocation cannot bind two sessions to the same tab", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map(),
  };

  const [writerA, writerB] = await Promise.all([
    routeCommand(context, {
      session: "cortex-conv-writer-concurrent-a",
      action: "open_chatgpt",
      payload: {},
    }),
    routeCommand(context, {
      session: "cortex-conv-writer-concurrent-b",
      action: "open_chatgpt",
      payload: {},
    }),
  ]);

  assert.notEqual(writerA.tab_id, writerB.tab_id);
  assert.notEqual(
    context.sessionTabs.get("cortex-conv-writer-concurrent-a"),
    context.sessionTabs.get("cortex-conv-writer-concurrent-b"),
  );
  assert.equal(chrome.calls.create.length, 2);
});

test("read-only sessions share the primary tab but never claim a writer tab", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/primary" },
    { id: 33, windowId: 7, index: 2, url: "https://chatgpt.com/c/writer" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([
      ["cortex-bridge-ui", 32],
      ["cortex-conv-writer-a", 33],
    ]),
  };

  const opened = await routeCommand(context, {
    session: "cortex-missions-read-only",
    action: "open_chatgpt",
    payload: {},
  });

  assert.equal(opened.tab_id, 32);
  assert.equal(context.sessionTabs.get("cortex-conv-writer-a"), 33);
});

test("a read-only page command automatically reuses the paired primary tab", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/primary" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-bridge-ui", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-missions-read-only",
    action: "probe",
    payload: {},
  });

  assert.deepEqual(result, undefined);
  assert.equal(context.sessionTabs.get("cortex-missions-read-only"), 32);
  assert.equal(chrome.calls.sendMessage[0].tabId, 32);
  assert.deepEqual(chrome.calls.update, []);
});

test("probe reloads an existing ChatGPT tab whose content script became stale", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  let attempts = 0;
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    attempts += 1;
    if (attempts === 1) {
      throw new Error("Could not establish connection. Receiving end does not exist.");
    }
    return {
      ok: true,
      result: { ok: true, composer_present: true, url: "https://chatgpt.com/" },
    };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-bridge-ui", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-bridge-ui",
    action: "probe",
    payload: {},
  });

  assert.equal(result.composer_present, true);
  assert.deepEqual(chrome.calls.reload, [32]);
  assert.equal(chrome.calls.sendMessage.length, 2);
});

test("a writer send reports a missing content script as safe pre-delivery unavailability", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "loading", url: "https://chatgpt.com/" },
  ]);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    throw new Error("Could not establish connection. Receiving end does not exist.");
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-writer",
      action: "send_text",
      payload: { text: "CORTEX-SAFE-RETRY" },
    }),
    (error) => error.code === "TAB_UNAVAILABLE",
  );
  assert.equal(chrome.calls.sendMessage.length, 1);
});

test("a closed preparation channel stays retryable because activation has not started", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    throw new Error("The message port closed before a response was received.");
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-writer",
      action: "send_text",
      payload: { text: "CORTEX-DO-NOT-RETRY" },
    }),
    (error) => (
      error.code === "TAB_UNAVAILABLE"
      && error.message === "The ChatGPT content script is not available yet"
    ),
  );
  assert.equal(chrome.calls.sendMessage.length, 1);
  assert.equal(chrome.calls.executeScript.length, 0);
});

test("a transient missing composer is classified before delivery activation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    return {
      ok: false,
      error: {
        code: "COMPOSER_MISSING",
        message: "ChatGPT composer not found",
      },
    };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-writer",
      action: "send_text",
      payload: { text: "CORTEX-PRE-DELIVERY-WAIT" },
    }),
    (error) => error.code === "PRE_DELIVERY_NOT_READY",
  );
  assert.equal(chrome.calls.sendMessage.length, 1);
  assert.equal(chrome.calls.executeScript.length, 0);
});

test("a writer send prepares in the isolated script then activates ChatGPT in MAIN world", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-MAIN-WORLD-ACTIVATION" },
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(chrome.calls.sendMessage.length, 1);
  assert.equal(chrome.calls.sendMessage[0].message.action, "prepare_text");
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.equal(chrome.calls.executeScript[0].world, "MAIN");
  assert.deepEqual(chrome.calls.executeScript[0].target, { tabId: 32 });
  assert.equal(typeof chrome.calls.executeScript[0].func, "function");
});

test("an ambiguous MAIN-world activation is never retried", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    throw new Error("The frame disappeared during execution");
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
    activationConfirmationTimeoutMs: 0,
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-writer",
      action: "send_text",
      payload: { text: "CORTEX-DO-NOT-RETRY-ACTIVATION" },
    }),
    (error) => error.code === "DELIVERY_UNCERTAIN",
  );
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
    "get_state",
  ]);
  assert.equal(chrome.calls.executeScript.length, 1);
});

test("a new-chat navigation confirms the click from the visible user marker", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    throw new Error("The frame was removed during navigation");
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "prepare_text") return { ok: true, result: { ok: true } };
    return {
      ok: true,
      result: {
        messages: [{ role: "user", text: "CORTEX-NAVIGATION-CONFIRMED", code_blocks: [] }],
      },
    };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-NAVIGATION-CONFIRMED" },
  });

  assert.deepEqual(result, { ok: true, confirmed_after_navigation: true });
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
    "get_state",
  ]);
});

test("navigation replaces a stale closed session tab", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-view-read-only", 999]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-view-read-only",
    action: "navigate",
    payload: { url: "https://chatgpt.com/c/recovered-view" },
  });

  assert.equal(result.tab_id, 32);
  assert.equal(context.sessionTabs.get("cortex-view-read-only"), 32);
  assert.deepEqual(chrome.calls.update.at(-1), {
    tabId: 32,
    options: { url: "https://chatgpt.com/c/recovered-view", active: true },
  });
});

test("navigation returns once Chrome accepts the target without requiring URL visibility", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, status: "complete", url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/old" },
  ]);
  let navigationStarted = false;
  chrome.api.tabs.update = async (tabId, options) => {
    chrome.calls.update.push({ tabId, options });
    if (options.url) navigationStarted = true;
    return { id: tabId, windowId: 7, status: "loading", pendingUrl: options.url };
  };
  chrome.api.tabs.get = async (tabId) => {
    if (tabId !== 32) throw new Error("tab missing");
    if (navigationStarted) throw new Error("Chrome has not exposed the target URL yet");
    return { id: 32, windowId: 7, status: "complete", url: "https://chatgpt.com/c/old" };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-navigation", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-navigation",
    action: "navigate",
    payload: { url: "https://chatgpt.com/" },
  });

  assert.equal(result.url, "https://chatgpt.com/");
  assert.deepEqual(chrome.calls.update.at(-1), {
    tabId: 32,
    options: { url: "https://chatgpt.com/", active: true },
  });
});

test("a screenshot requires a recent explicit extension-action capture", async () => {
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/screenshot-proof" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-screenshot", 32]]),
    pendingCapture: null,
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-screenshot",
      action: "capture_screenshot",
      payload: {},
    }),
    (error) => error.code === "SCREENSHOT_PERMISSION_REQUIRED",
  );
});

test("a matching action-authorized screenshot is consumed exactly once", async () => {
  const url = "https://chatgpt.com/c/screenshot-proof";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-screenshot", 32]]),
    pendingCapture: {
      data_url: "data:image/png;base64,iVBORw0KGgo=",
      tab_id: 32,
      url,
      captured_at: Date.now(),
    },
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-screenshot",
    action: "capture_screenshot",
    payload: {},
  });

  assert.equal(result.tab_id, 32);
  assert.match(result.data_url, /^data:image\/png;base64,/);
  assert.equal(context.pendingCapture, null);
});

test("a screenshot falls back to a CDP capture without any icon click", async () => {
  const url = "https://chatgpt.com/c/screenshot-fallback";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  const debuggerCalls = { attach: [], sendCommand: [], detach: [] };
  chrome.api.debugger = {
    async attach(target, version) {
      debuggerCalls.attach.push({ target, version });
    },
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      return { data: "aGVsbG8td29ybGQ=" };
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-screenshot", 32]]),
    pendingCapture: null,
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-screenshot",
    action: "capture_screenshot",
    payload: {},
  });

  assert.equal(result.tab_id, 32);
  assert.equal(result.data_url, "data:image/png;base64,aGVsbG8td29ybGQ=");
  assert.deepEqual(debuggerCalls.attach, [{ target: { tabId: 32 }, version: "1.3" }]);
  assert.deepEqual(debuggerCalls.sendCommand, [{
    target: { tabId: 32 },
    method: "Page.captureScreenshot",
    params: { format: "png" },
  }]);
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
});

test("a stale action capture is discarded before the CDP fallback runs", async () => {
  const url = "https://chatgpt.com/c/screenshot-stale";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  chrome.api.debugger = {
    async attach() {},
    async sendCommand() {
      return { data: "ZnJlc2gtY2FwdHVyZQ==" };
    },
    async detach() {},
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-screenshot", 32]]),
    pendingCapture: {
      data_url: "data:image/png;base64,c3RhbGU=",
      tab_id: 32,
      url,
      captured_at: Date.now() - 120_000,
    },
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-screenshot",
    action: "capture_screenshot",
    payload: {},
  });

  assert.equal(result.data_url, "data:image/png;base64,ZnJlc2gtY2FwdHVyZQ==");
  assert.equal(context.pendingCapture, null);
});

test("a debugger attach failure is reported as a capture failure", async () => {
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/c/screenshot-fail" },
  ]);
  chrome.api.debugger = {
    async attach() {
      throw new Error("Another debugger is already attached");
    },
    async sendCommand() {
      throw new Error("must not be reached");
    },
    async detach() {},
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-screenshot", 32]]),
    pendingCapture: null,
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-screenshot",
      action: "capture_screenshot",
      payload: {},
    }),
    (error) => error.code === "SCREENSHOT_CAPTURE_FAILED",
  );
});

async function runSurfaceGuardAction({ pathname, links = [], radios = [], action = "prepare_text", bodyText = "" }) {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");
  let listener = null;
  class FakeElement {
    constructor({ href = null, ariaLabel = null, name = "", checked = "false" } = {}) {
      this.href = href;
      this.ariaLabel = ariaLabel;
      this.innerText = name;
      this.textContent = name;
      this.checked = checked;
      this.dataset = {};
    }

    getAttribute(name) {
      if (name === "href") return this.href;
      if (name === "aria-label") return this.ariaLabel;
      if (name === "aria-checked") return this.checked;
      return null;
    }

    click() {
      this.checked = "true";
    }
  }
  const sidebarLinks = links.map((link) => new FakeElement(link));
  const radioNodes = radios.map((radio) => new FakeElement(radio));
  const document = {
    body: { innerText: bodyText },
    title: "Surface Guard - ChatGPT",
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "nav a[href^='/c/'], aside a[href^='/c/']") return sidebarLinks;
      if (selector === "[role=radiogroup] [role=radio]") return radioNodes;
      return [];
    },
  };
  const chrome = {
    runtime: {
      onMessage: {
        addListener(callback) {
          listener = callback;
        },
      },
    },
  };
  runInNewContext(source, {
    chrome,
    document,
    location: {
      href: `https://chatgpt.com${pathname}`,
      origin: "https://chatgpt.com",
      pathname,
    },
    Element: FakeElement,
    HTMLInputElement: class {},
    URL,
    Map,
    Promise,
    setTimeout,
    clearTimeout,
  });
  assert.equal(typeof listener, "function");
  return new Promise((resolve) => {
    listener(
      { source: "cortex-bridge-extension", action, payload: { text: "surface guard probe" } },
      {},
      (response) => resolve(response),
    );
  });
}

test("a Work conversation refuses any composer preparation", async () => {
  const response = await runSurfaceGuardAction({
    pathname: "/c/work-conversation",
    links: [{ href: "/c/work-conversation", ariaLabel: "Quarterly report, Work" }],
  });

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "WORK_SURFACE_REJECTED");
});

test("a classic chat conversation stays writable", async () => {
  const response = await runSurfaceGuardAction({
    pathname: "/c/classic-conversation",
    links: [{ href: "/c/classic-conversation", ariaLabel: "Weekend plans" }],
  });

  // The guard must not fire; the flow then fails later on the missing fake
  // composer, which proves it went past the surface check.
  assert.equal(response.ok, false);
  assert.equal(response.error.code, "COMPOSER_MISSING");
});

test("the Work home switches back to Chat instead of composing there", async () => {
  const chatRadio = { name: "Chat", checked: "false" };
  const response = await runSurfaceGuardAction({
    pathname: "/",
    radios: [chatRadio, { name: "Work", checked: "true" }],
  });

  // The auto-switch clicked Chat (fake click flips aria-checked), the guard
  // passed, and the flow then failed later on the missing fake composer.
  assert.equal(response.ok, false);
  assert.equal(response.error.code, "COMPOSER_MISSING");
});

test("the Work home is rejected when no Chat radio is available", async () => {
  const response = await runSurfaceGuardAction({
    pathname: "/",
    radios: [{ name: "Work", checked: "true" }],
  });

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "WORK_SURFACE_REJECTED");
});

test("usage-limit banners are classified as a rate_limit blocker", async () => {
  for (const bodyText of [
    "You've hit your usage limit. Try again later.",
    "Vous avez atteint votre limite d'utilisation. Réessayez plus tard.",
  ]) {
    const response = await runSurfaceGuardAction({
      pathname: "/c/classic-conversation",
      links: [{ href: "/c/classic-conversation", ariaLabel: "Weekend plans" }],
      action: "probe",
      bodyText,
    });

    assert.equal(response.ok, true);
    assert.equal(response.result.blocker, "rate_limit");
    assert.ok(response.result.failures.includes("rate_limit"));
  }
});

test("the surface guard is wired into every delivery-sensitive action", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");

  assert.match(source, /const surfaceMode = \(\)/);
  assert.match(source, /WORK_SURFACE_SUFFIX/);
  assert.match(source, /surface: surfaceMode\(\)/);
  const guarded = ["prepare_text", "attachment_begin", "send_bare"];
  for (const action of guarded) {
    assert.match(
      source,
      new RegExp(`async ${action}\\([\\s\\S]{0,120}?ensureClassicChatSurface\\(\\)`),
      `${action} must call ensureClassicChatSurface first`,
    );
  }
});

test("uses a 20 second WebSocket heartbeat", () => {
  assert.equal(HEARTBEAT_INTERVAL_MS, 20_000);
});

test("manifest limits hosts and requires Chrome 116", async () => {
  const manifest = JSON.parse(
    await readFile(join(EXTENSION_ROOT, "manifest.json"), "utf8"),
  );

  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.minimum_chrome_version, "116");
  assert.deepEqual(manifest.host_permissions, [
    "http://127.0.0.1:8420/*",
    "https://chatgpt.com/*",
  ]);
  assert.deepEqual(manifest.permissions, ["activeTab", "debugger", "scripting", "storage"]);
  assert.equal(JSON.stringify(manifest).includes("<all_urls>"), false);
  assert.equal(JSON.stringify(manifest).includes("cookies"), false);
  assert.equal(JSON.stringify(manifest).includes("history"), false);
});

test("extension source never creates a Chrome window or evaluates remote code", async () => {
  const files = await readdir(EXTENSION_ROOT);
  const sourceFiles = files.filter((name) => name.endsWith(".js"));
  const source = (
    await Promise.all(
      sourceFiles.map((name) => readFile(join(EXTENSION_ROOT, name), "utf8")),
    )
  ).join("\n");

  assert.equal(source.includes("chrome.windows.create"), false);
  assert.equal(source.includes("eval("), false);
  assert.equal(source.includes("new Function"), false);
});

test("the extension action records the one-shot screenshot permission", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "service-worker.js"), "utf8");

  assert.match(source, /chrome\.action\.onClicked\.addListener/);
  assert.match(source, /chrome\.tabs\.captureVisibleTab/);
  assert.match(source, /context\.pendingCapture/);
});

test("the extension action reconnects a suspended MV3 service worker safely", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "service-worker.js"), "utf8");

  assert.match(source, /chrome\.action\.onClicked\.addListener\(async \(tab\) => \{\s*connect\(\);/);
  assert.match(source, /const activeSocket = new WebSocket\(SOCKET_URL\)/);
  assert.match(source, /if \(socket !== activeSocket\) return;/);
});

test("conversation discovery is sidebar-scoped, scrolls lazily, and caps at 50", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");

  assert.equal(source.includes("nav a[href^='/c/'], aside a[href^='/c/']"), true);
  assert.equal(source.includes("parentList && parentList.closest('li')"), true);
  assert.equal(source.includes("for (let pass = 0; pass < 40"), true);
  assert.equal(source.includes("slice(0, MAX_CONVERSATIONS)"), true);
});

test("probe never reads the text of a long conversation history", async () => {
  const expensiveMessage = {
    id: "expensive-message",
    get innerText() { throw new Error("message text must not be read"); },
    get textContent() { throw new Error("message text must not be read"); },
    getAttribute(name) {
      if (name === "data-message-id") return "expensive-message";
      if (name === "data-message-author-role") return "assistant";
      return null;
    },
  };

  const result = await getContentScriptState([expensiveMessage], "probe");

  assert.equal(result.ok, true);
  assert.equal(result.composer_present, true);
});

test("light state counts messages without extracting their content", async () => {
  const expensiveMessage = {
    id: "expensive-message",
    get innerText() { throw new Error("message text must not be read"); },
    get textContent() { throw new Error("message text must not be read"); },
    getAttribute(name) {
      return name === "data-message-id" ? "expensive-message" : null;
    },
  };

  const result = await getContentScriptState([expensiveMessage], "get_light_state");

  assert.equal(result.message_count, 1);
  assert.equal(result.first_id, "expensive-message");
  assert.equal(result.last_id, "expensive-message");
});

test("prepare_text waits for React to arm the send button before activation", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");

  assert.match(source, /async prepare_text\(payload\)/);
  assert.match(
    source,
    /for \(let attempt = 0; attempt < 50 && !button; attempt \+= 1\)/,
  );
  assert.equal(
    source.includes("if (!current || !value.trim()) return { ok: true }"),
    false,
  );
  assert.match(source, /return \{ ok: true \}/);
});

test("prepare_text accepts ChatGPT whitespace normalization for long prompts", async () => {
  const response = await runContentScriptSend(
    "You are the cloud orchestrator for Cortex Bridge.\nYou analyze the global objective.\nYou produce one bounded action.",
    { normalizeComposerWhitespace: true },
  );

  assert.equal(response.ok, true);
  assert.equal(response.result.ok, true);
});

test("attachment readiness requires the transferred filename and an armed send button", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");

  assert.match(source, /async await_attachment\(payload\)/);
  assert.match(source, /payload\?\.name/);
  assert.match(source, /sendButton\(\)/);
  assert.match(source, /let readyChecks = 0/);
  assert.match(source, /readyChecks >= 4/);
  assert.equal(source.includes('"[data-testid*=\'file\']"'), false);
});

test("attachment readiness accepts ChatGPT duplicate-name suffixes", async () => {
  const result = await runAttachmentReadiness(
    "cortex-upload-proof(1).txt Document",
    "cortex-upload-proof.txt",
  );

  assert.equal(result.ok, true);
  assert.match(result.label, /cortex-upload-proof\(1\)\.txt/);
});

test("contenteditable send does not dispatch a duplicate React input event", async () => {
  const response = await runContentScriptSend("CORTEX-SEND-REGRESSION");

  assert.equal(response.ok, true);
  assert.equal(response.result?.ok, true);
});

test("contenteditable send scopes replacement to the composer when an attachment is present", async () => {
  const response = await runContentScriptSend(
    "CORTEX-ATTACHMENT-TEXT-REGRESSION",
    { requiresScopedSelection: true },
  );

  assert.equal(response.ok, true);
  assert.equal(response.result?.ok, true);
});

test("attachment send waits for React to retain the inserted text before clicking", async () => {
  const response = await runContentScriptSend(
    "CORTEX-ATTACHMENT-REACT-COMMIT",
    { attachmentKeepsSendEnabled: true },
  );

  assert.equal(response.ok, true);
  assert.equal(response.result?.ok, true);
});

test("new-chat send commits the rich editor before submitting", async () => {
  const response = await runContentScriptSend(
    "CORTEX-NEW-CHAT-FOCUS-COMMIT",
    { focusCommitRequired: true },
  );

  assert.equal(response.ok, true);
  assert.equal(response.result?.ok, true);
});

test("new-chat send reacquires the submit button after the editor commit rerenders it", async () => {
  const response = await runContentScriptSend(
    "CORTEX-NEW-CHAT-RERENDER-COMMIT",
    {
      focusCommitRequired: true,
      focusReplacesButton: true,
    },
  );

  assert.equal(response.ok, true);
  assert.equal(response.result?.ok, true);
});

test("new-chat send never invokes native form submission", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");

  assert.equal(source.includes("requestSubmit("), false);
});

test("reasoning chrome is not exposed as assistant response text", async () => {
  const reasoningNode = {
    id: "assistant-reasoning",
    innerText: "Réflexion",
    textContent: "Réflexion",
    getAttribute(name) {
      if (name === "data-message-id") return "assistant-reasoning";
      if (name === "data-message-author-role") return "assistant";
      return null;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };

  const state = await getContentScriptState([reasoningNode]);

  assert.equal(state.messages[0].text, "");
});

test("assistant markdown remains visible as response text", async () => {
  const markdown = {
    innerText: "REÇU-CORTEX",
    textContent: "REÇU-CORTEX",
    querySelectorAll() {
      return [];
    },
  };
  const responseNode = {
    id: "assistant-response",
    innerText: "Réflexion\nREÇU-CORTEX\nCopy",
    textContent: "Réflexion REÇU-CORTEX Copy",
    getAttribute(name) {
      if (name === "data-message-id") return "assistant-response";
      if (name === "data-message-author-role") return "assistant";
      return null;
    },
    querySelector(selector) {
      return selector === ".markdown" ? markdown : null;
    },
    querySelectorAll() {
      return [];
    },
  };

  const state = await getContentScriptState([responseNode]);

  assert.equal(state.messages[0].text, "REÇU-CORTEX");
});

async function runSelectModel({ label, beforeLabel, afterLabel }) {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");
  let listener = null;
  let clock = 0;
  class FakeDate extends Date {
    static now() { return clock; }
  }
  class FakeElement {
    constructor(text = "") {
      this.innerText = text;
      this.textContent = text;
    }
  }
  const TRIGGER_SELECTORS = [
    "button[data-testid*='model-switcher']",
    "button[aria-label*='model']",
    "button[aria-label*='modèle']",
  ];
  let currentTrigger = new FakeElement(beforeLabel);
  const option = new FakeElement(label);
  option.click = () => {
    // Radix re-renders the switcher after a selection: the previous trigger
    // node is detached and replaced. afterLabel === null simulates a click
    // that ChatGPT silently ignored (trigger never updates).
    if (afterLabel !== null) currentTrigger = new FakeElement(afterLabel);
  };
  const document = {
    body: { innerText: "" },
    title: "Model switch regression - ChatGPT",
    querySelector(selector) {
      return TRIGGER_SELECTORS.includes(selector) ? currentTrigger : null;
    },
    querySelectorAll(selector) {
      if (selector === "[role=menuitem], [role=option], button") return [option];
      return [];
    },
  };
  const chrome = {
    runtime: {
      onMessage: {
        addListener(callback) { listener = callback; },
      },
    },
  };
  runInNewContext(source, {
    chrome,
    document,
    location: {
      href: "https://chatgpt.com/c/model-switch-regression",
      origin: "https://chatgpt.com",
      pathname: "/c/model-switch-regression",
    },
    Element: FakeElement,
    HTMLTextAreaElement: class {},
    HTMLInputElement: class {},
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    URL,
    Map,
    Promise,
    Date: FakeDate,
    setTimeout: (callback) => { clock += 100; callback(); },
    clearTimeout,
  });
  assert.equal(typeof listener, "function");
  return new Promise((resolve) => {
    listener(
      { source: "cortex-bridge-extension", action: "select_model", payload: { label } },
      {},
      resolve,
    );
  });
}

test("select_model confirms from the rerendered Radix trigger, never a stale node", async () => {
  const response = await runSelectModel({
    label: "Instantanée 5.5",
    beforeLabel: "Pro",
    afterLabel: "Instantanée 5.5",
  });

  assert.equal(response.ok, true);
  assert.equal(response.result.selected, "Instantanée 5.5");
  assert.equal(response.result.confirmed, true);
});

test("select_model fails closed when ChatGPT silently ignores the click", async () => {
  const response = await runSelectModel({
    label: "Instantanée 5.5",
    beforeLabel: "Pro",
    afterLabel: null,
  });

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "MODEL_CONFIRM_FAILED");
});

test("select_model confirms immediately when the requested model is already active", async () => {
  const response = await runSelectModel({
    label: "Pro",
    beforeLabel: "Pro",
    afterLabel: null,
  });

  assert.equal(response.ok, true);
  assert.equal(response.result.selected, "Pro");
});
