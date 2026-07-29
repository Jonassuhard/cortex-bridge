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
