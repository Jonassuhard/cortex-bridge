import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  ALLOWED_COMMANDS,
  HEARTBEAT_INTERVAL_MS,
  findOrOpenChatGPTTab,
  routeCommand,
} from "../service-worker-core.js";


const HERE = dirname(fileURLToPath(import.meta.url));
const EXTENSION_ROOT = join(HERE, "..");

function chromeWithTabs(initialTabs = []) {
  const calls = { create: [], update: [], sendMessage: [] };
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
          return tabs.find((tab) => tab.id === tabId);
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

test("conversation discovery is sidebar-scoped, scrolls lazily, and caps at 50", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");

  assert.equal(source.includes("nav a[href^='/c/'], aside a[href^='/c/']"), true);
  assert.equal(source.includes("parentList && parentList.closest('li')"), true);
  assert.equal(source.includes("for (let pass = 0; pass < 40"), true);
  assert.equal(source.includes("slice(0, MAX_CONVERSATIONS)"), true);
});

test("send_text waits for React to arm the send button and confirms delivery", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");

  assert.match(source, /async send_text\(payload\)/);
  assert.match(source, /const userIdsBefore = new Set/);
  assert.match(
    source,
    /for \(let attempt = 0; attempt < 50 && !button; attempt \+= 1\)/,
  );
  assert.match(source, /visibleUserMessage/);
  assert.match(source, /composer did not clear after send/);
});
