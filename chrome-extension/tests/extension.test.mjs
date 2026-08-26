import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { runInNewContext } from "node:vm";

import {
  ALLOWED_COMMANDS,
  CORTEX_GROUP_COLOR,
  CORTEX_GROUP_TITLE,
  HEARTBEAT_INTERVAL_MS,
  captureTabViaDebuggerExactly,
  ensureCortexTabGroup,
  findOrOpenChatGPTTab,
  restoreQuarantinedWriterTabs,
  routeCommand,
  withPrivateCaptureMask,
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

async function runContentPrivacyMaskActions(
  actions,
  {
    includePrivateZone = true,
    includeHomeSuggestions = false,
    paintFrameAvailable = true,
    pathname = "/c/private-capture",
  } = {},
) {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");
  let listener = null;
  class FakeElement {
    constructor(tagName = "div", rect = null) {
      this.tagName = tagName.toUpperCase();
      this.rect = rect;
      this.children = [];
      this.parentNode = null;
      this.isConnected = false;
      this.style = {};
      this.dataset = {};
      this.attributes = new Map();
      this.innerText = "";
      this.textContent = "";
    }

    appendChild(child) {
      child.parentNode = this;
      child.isConnected = true;
      this.children.push(child);
      return child;
    }

    remove() {
      if (this.parentNode) {
        this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
      }
      this.parentNode = null;
      this.isConnected = false;
    }

    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    getBoundingClientRect() {
      return this.rect || {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
        width: 0,
        height: 0,
      };
    }
    getClientRects() { return this.rect ? [this.rect] : []; }
    querySelector() { return null; }
    querySelectorAll() { return []; }
  }

  const documentElement = new FakeElement("html");
  documentElement.isConnected = true;
  const body = new FakeElement("body");
  body.isConnected = true;
  const privateZone = new FakeElement("nav", {
    left: 0,
    top: 0,
    right: 280,
    bottom: 800,
    width: 280,
    height: 800,
  });
  privateZone.isConnected = true;
  const homeSuggestions = new FakeElement("ul", {
    left: 360,
    top: 520,
    right: 1080,
    bottom: 760,
    width: 720,
    height: 240,
  });
  homeSuggestions.isConnected = true;
  const document = {
    body,
    documentElement,
    title: "Private capture - ChatGPT",
    createElement(tagName) { return new FakeElement(tagName); },
    querySelector() { return null; },
    querySelectorAll(selector) {
      const matches = [];
      if (includePrivateZone && selector.includes("nav")) matches.push(privateZone);
      if (includeHomeSuggestions && selector.includes("main ul")) {
        matches.push(homeSuggestions);
      }
      return matches;
    },
  };
  const chrome = {
    runtime: {
      onMessage: {
        addListener(callback) { listener = callback; },
      },
    },
  };
  let now = 0;
  let nextTimerId = 1;
  const timers = new Map();
  const testSetTimeout = (callback, delay = 0) => {
    const timerId = nextTimerId;
    nextTimerId += 1;
    timers.set(timerId, { callback, dueAt: now + Number(delay) });
    if (!paintFrameAvailable && Number(delay) <= 250) {
      queueMicrotask(() => {
        if (!timers.has(timerId)) return;
        timers.delete(timerId);
        callback();
      });
    }
    return timerId;
  };
  const testClearTimeout = (timerId) => timers.delete(timerId);
  const advanceTime = (milliseconds) => {
    now += milliseconds;
    for (const [timerId, timer] of [...timers.entries()]) {
      if (timer.dueAt > now) continue;
      timers.delete(timerId);
      timer.callback();
    }
  };
  runInNewContext(source, {
    chrome,
    document,
    window: { innerWidth: 1440, innerHeight: 800 },
    location: {
      href: "https://chatgpt.com/c/private-capture",
      origin: "https://chatgpt.com",
      pathname,
    },
    Element: FakeElement,
    HTMLInputElement: class {},
    URL,
    Map,
    Promise,
    Date,
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    requestAnimationFrame: (callback) => {
      if (paintFrameAvailable) callback();
    },
    setTimeout: testSetTimeout,
    clearTimeout: testClearTimeout,
  });
  assert.equal(typeof listener, "function");

  const responses = [];
  for (const { action, payload = {}, advance_ms: advanceMs = 0 } of actions) {
    advanceTime(advanceMs);
    const response = new Promise((resolve) => {
      const accepted = listener(
        { source: "cortex-bridge-extension", action, payload },
        {},
        resolve,
      );
      if (accepted !== true) resolve({ accepted: false });
    });
    responses.push(await Promise.race([
      response,
      new Promise((resolve) => {
        globalThis.setTimeout(() => resolve({ timed_out: true }), 50);
      }),
    ]));
  }
  responses.debug = { documentElement, advanceTime };
  return responses;
}

test("the content script installs an opaque private-zone mask and restores it", async () => {
  const responses = await runContentPrivacyMaskActions([
    { action: "privacy_mask_begin" },
    { action: "privacy_mask_restore", payload: { token: "mask-1" } },
  ]);

  assert.equal(responses[0].ok, true);
  assert.equal(responses[0].result.confirmed, true);
  assert.equal(responses[0].result.token, "mask-1");
  assert.equal(responses[0].result.masked_zones, 1);
  assert.equal(responses[1].ok, true);
  assert.equal(responses[1].result.restored, true);
  assert.equal(responses.debug.documentElement.children.length, 0);
});

test("the content script refuses capture when no private-zone mask can be confirmed", async () => {
  const responses = await runContentPrivacyMaskActions(
    [{ action: "privacy_mask_begin" }],
    { includePrivateZone: false },
  );

  assert.equal(responses[0].ok, false);
  assert.equal(responses[0].error.code, "SCREENSHOT_PRIVACY_MASK_FAILED");
  assert.equal(responses.debug.documentElement.children.length, 0);
});

test("a private-zone mask self-restores if the service worker disappears", async () => {
  const responses = await runContentPrivacyMaskActions([
    { action: "privacy_mask_begin" },
    { action: "probe", advance_ms: 15_001 },
  ]);

  assert.equal(responses[0].ok, true);
  assert.equal(responses.debug.documentElement.children.length, 0);
});

test("a background ChatGPT tab confirms its mask without a paint-frame callback", async () => {
  const responses = await runContentPrivacyMaskActions(
    [{ action: "privacy_mask_begin" }],
    { paintFrameAvailable: false },
  );

  assert.equal(responses[0].timed_out, undefined);
  assert.equal(responses[0].ok, true);
  assert.equal(responses[0].result.confirmed, true);
});

test("the private mask covers personalized home suggestions", async () => {
  const responses = await runContentPrivacyMaskActions(
    [{ action: "privacy_mask_begin" }],
    {
      includePrivateZone: false,
      includeHomeSuggestions: true,
      pathname: "/",
    },
  );

  assert.equal(responses[0].ok, true);
  assert.equal(responses[0].result.confirmed, true);
  assert.equal(responses[0].result.masked_zones, 1);
});

async function runContentAttachmentActions(
  actions,
  {
    foreignInputFirst = false,
    remountBeforeCommit = false,
    composerText = "",
    existingAttachment = false,
  } = {},
) {
  const source = await readFile(join(EXTENSION_ROOT, "chatgpt-content.js"), "utf8");
  let listener = null;
  class FakeElement {
    constructor() {
      this.innerText = "";
      this.textContent = "";
      this.disabled = false;
    }

    getAttribute() { return null; }
    querySelector() { return null; }
    querySelectorAll() { return []; }
  }
  class FakeInput extends FakeElement {
    constructor() {
      super();
      this.files = [];
      this.changes = 0;
      this.isConnected = true;
    }

    dispatchEvent() { this.changes += 1; }
  }
  class FakeFile {
    constructor(parts, name, options = {}) {
      this.name = name;
      this.type = options.type || "";
      this.size = parts.reduce((total, part) => total + part.byteLength, 0);
    }
  }
  class FakeDataTransfer {
    constructor() {
      this.files = [];
      this.items = { add: (file) => this.files.push(file) };
    }
  }

  const composer = new FakeElement();
  composer.innerText = composerText;
  composer.textContent = composerText;
  composer.isConnected = true;
  const input = new FakeInput();
  const replacementInput = new FakeInput();
  const foreignInput = new FakeInput();
  const makeForm = (formInput) => ({
    isConnected: true,
    querySelector(selector) {
      return selector === "input[type=file]" ? formInput : null;
    },
  });
  const initialForm = makeForm(input);
  const replacementForm = makeForm(replacementInput);
  let activeForm = initialForm;
  composer.closest = (selector) => (selector === "form" ? activeForm : null);
  const existingTile = {
    innerText: "existing.txt",
    textContent: "existing.txt",
    getAttribute(name) {
      if (name === "class") return "group/file-tile rounded-xl";
      if (name === "role") return "group";
      if (name === "aria-label") return "existing.txt";
      return null;
    },
  };
  const document = {
    body: { innerText: "" },
    title: "Attachment boundary - ChatGPT",
    querySelector(selector) {
      if (selector === "#prompt-textarea") return composer;
      if (selector === "form input[type=file]") {
        return foreignInputFirst ? foreignInput : activeForm.querySelector("input[type=file]");
      }
      return null;
    },
    querySelectorAll(selector) {
      if (existingAttachment && selector.includes("file-tile")) return [existingTile];
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
  let now = 0;
  let nextTimerId = 1;
  const timers = new Map();
  const testSetTimeout = (callback, delay = 0) => {
    const timerId = nextTimerId;
    nextTimerId += 1;
    timers.set(timerId, { callback, dueAt: now + Number(delay) });
    return timerId;
  };
  const testClearTimeout = (timerId) => timers.delete(timerId);
  const advanceTime = (milliseconds) => {
    now += milliseconds;
    while (true) {
      const due = Array.from(timers.entries())
        .filter(([, timer]) => timer.dueAt <= now)
        .sort((left, right) => left[1].dueAt - right[1].dueAt)[0];
      if (!due) return;
      timers.delete(due[0]);
      due[1].callback();
    }
  };
  runInNewContext(source, {
    chrome,
    document,
    location: {
      href: "https://chatgpt.com/c/attachment-boundary",
      origin: "https://chatgpt.com",
      pathname: "/c/attachment-boundary",
    },
    Element: FakeElement,
    HTMLTextAreaElement: class {},
    HTMLInputElement: FakeInput,
    File: FakeFile,
    DataTransfer: FakeDataTransfer,
    Event: class {},
    URL,
    Map,
    Promise,
    Uint8Array,
    atob,
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    setTimeout: testSetTimeout,
    clearTimeout: testClearTimeout,
  });
  assert.equal(typeof listener, "function");

  const responses = [];
  for (const { action, payload, advance_ms: advanceMs = 0 } of actions) {
    advanceTime(advanceMs);
    if (remountBeforeCommit && action === "attachment_commit") {
      activeForm = replacementForm;
      initialForm.isConnected = false;
      input.isConnected = false;
    }
    responses.push(await new Promise((resolve) => {
      listener(
        { source: "cortex-bridge-extension", action, payload },
        {},
        resolve,
      );
    }));
  }
  responses.debug = {
    composerInput: input,
    replacementInput,
    foreignInput,
  };
  return responses;
}

test("attachment begin accepts exactly 25 MiB and refuses the next byte", async () => {
  const limit = 25 * 1024 * 1024;
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "exact-limit",
        name: "exact.bin",
        mime: "application/octet-stream",
        size: limit,
      },
    },
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "over-limit",
        name: "over.bin",
        mime: "application/octet-stream",
        size: limit + 1,
      },
    },
  ]);

  assert.equal(responses[0].ok, true);
  assert.equal(responses[0].result.accepted, true);
  assert.equal(responses[1].ok, false);
  assert.equal(responses[1].error.code, "ATTACHMENT_TOO_LARGE");
});

test("attachment chunks cannot exceed the declared byte budget", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "declared-three-bytes",
        name: "bounded.bin",
        mime: "application/octet-stream",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "declared-three-bytes",
        index: 0,
        data: Buffer.from([1, 2, 3, 4]).toString("base64"),
      },
    },
  ]);

  assert.equal(responses[0].ok, true);
  assert.equal(responses[1].ok, false);
  assert.equal(responses[1].error.code, "ATTACHMENT_TRANSFER_INVALID");
});

test("attachment commit rejects an incomplete declared transfer", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "declared-three-received-two",
        name: "incomplete.bin",
        mime: "application/octet-stream",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "declared-three-received-two",
        index: 0,
        data: Buffer.from([1, 2]).toString("base64"),
      },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "declared-three-received-two" },
    },
  ]);

  assert.equal(responses[0].ok, true);
  assert.equal(responses[1].ok, true);
  assert.equal(responses[2].ok, false);
  assert.equal(responses[2].error.code, "ATTACHMENT_TRANSFER_INVALID");
});

test("an abandoned attachment transfer expires after one minute of inactivity", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "abandoned-transfer",
        name: "abandoned.bin",
        mime: "application/octet-stream",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "abandoned-transfer",
        index: 0,
        data: Buffer.from([1, 2, 3]).toString("base64"),
      },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "abandoned-transfer" },
      advance_ms: 60_001,
    },
  ]);

  assert.equal(responses[0].ok, true);
  assert.equal(responses[1].ok, true);
  assert.equal(responses[2].ok, false);
  assert.equal(responses[2].error.code, "ATTACHMENT_TRANSFER_INVALID");
});

test("each accepted attachment chunk refreshes the inactivity deadline", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "active-transfer",
        name: "active.bin",
        mime: "application/octet-stream",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "active-transfer",
        index: 0,
        data: Buffer.from([1, 2, 3]).toString("base64"),
      },
      advance_ms: 40_000,
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "active-transfer" },
      advance_ms: 40_000,
    },
  ]);

  assert.equal(responses[0].ok, true);
  assert.equal(responses[1].ok, true);
  assert.equal(responses[2].ok, true);
  assert.equal(responses[2].result.attached, true);
});

test("attachment commit targets only the file input owned by the active composer form", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "composer-form-transfer",
        name: "composer.txt",
        mime: "text/plain",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "composer-form-transfer",
        index: 0,
        data: Buffer.from([1, 2, 3]).toString("base64"),
      },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "composer-form-transfer" },
    },
  ], { foreignInputFirst: true });

  assert.equal(responses[2].ok, true);
  assert.equal(responses.debug.composerInput.files.length, 1);
  assert.equal(responses.debug.composerInput.changes, 1);
  assert.equal(responses.debug.foreignInput.files.length, 0);
  assert.equal(responses.debug.foreignInput.changes, 0);
});

test("attachment commit refuses a remounted composer without dispatching", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "remounted-transfer",
        name: "remounted.txt",
        mime: "text/plain",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "remounted-transfer",
        index: 0,
        data: Buffer.from([1, 2, 3]).toString("base64"),
      },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "remounted-transfer" },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "remounted-transfer" },
    },
  ], { remountBeforeCommit: true });

  assert.equal(responses[2].ok, false);
  assert.equal(responses[2].error.code, "PRE_DELIVERY_NOT_READY");
  assert.equal(responses[3].ok, false);
  assert.equal(responses[3].error.code, "ATTACHMENT_TRANSFER_INVALID");
  assert.equal(responses.debug.composerInput.changes, 0);
  assert.equal(responses.debug.replacementInput.changes, 0);
});

test("attachment begin refuses a restored draft or an existing composer attachment", async () => {
  for (const options of [
    { composerText: "restored stale draft" },
    { existingAttachment: true },
  ]) {
    const responses = await runContentAttachmentActions([
      {
        action: "attachment_begin",
        payload: {
          transfer_id: "dirty-composer-transfer",
          name: "dirty.txt",
          mime: "text/plain",
          size: 3,
        },
      },
      {
        action: "attachment_commit",
        payload: { transfer_id: "dirty-composer-transfer" },
      },
    ], options);

    assert.equal(responses[0].ok, false);
    assert.equal(responses[0].error.code, "PRE_DELIVERY_NOT_READY");
    assert.equal(responses[1].ok, false);
    assert.equal(responses[1].error.code, "ATTACHMENT_TRANSFER_INVALID");
  }
});

test("a clean attachment transfer dispatches exactly once and cannot be replayed", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "single-dispatch-transfer",
        name: "single.txt",
        mime: "text/plain",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "single-dispatch-transfer",
        index: 0,
        data: Buffer.from([1, 2, 3]).toString("base64"),
      },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "single-dispatch-transfer" },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "single-dispatch-transfer" },
    },
  ]);

  assert.equal(responses[2].ok, true);
  assert.equal(responses[3].ok, false);
  assert.equal(responses[3].error.code, "ATTACHMENT_TRANSFER_INVALID");
  assert.equal(responses.debug.composerInput.changes, 1);
});

test("a malformed attachment chunk deterministically aborts its transfer", async () => {
  const responses = await runContentAttachmentActions([
    {
      action: "attachment_begin",
      payload: {
        transfer_id: "malformed-transfer",
        name: "malformed.bin",
        mime: "application/octet-stream",
        size: 3,
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "malformed-transfer",
        index: 0,
        data: Buffer.from([1, 2, 3]).toString("base64"),
      },
    },
    {
      action: "attachment_chunk",
      payload: {
        transfer_id: "malformed-transfer",
        index: 1,
        data: null,
      },
    },
    {
      action: "attachment_commit",
      payload: { transfer_id: "malformed-transfer" },
    },
  ]);

  assert.equal(responses[2].ok, false);
  assert.equal(responses[2].error.code, "ATTACHMENT_TRANSFER_INVALID");
  assert.equal(responses[3].ok, false);
  assert.equal(responses[3].error.code, "ATTACHMENT_TRANSFER_INVALID");
});

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

async function runAttachmentReadiness(
  label,
  expectedName,
  {
    attachmentClass = null,
    attachmentRole = null,
    attachmentAriaLabel = null,
  } = {},
) {
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
  chip.getAttribute = (name) => ({
    class: attachmentClass,
    role: attachmentRole,
    "aria-label": attachmentAriaLabel,
  })[name] ?? null;
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
  const calls = {
    create: [],
    update: [],
    windowsUpdate: [],
    reload: [],
    sendMessage: [],
    executeScript: [],
    debuggerAttach: [],
    debuggerSendCommand: [],
    debuggerDetach: [],
  };
  const tabs = [...initialTabs];
  return {
    calls,
    api: {
      windows: {
        async update(windowId, options) {
          calls.windowsUpdate.push({ windowId, options });
          return { id: windowId, ...options };
        },
      },
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
          return [{
            result: {
              ok: true,
              activation_started: false,
              point: { x: 412.5, y: 703.25 },
            },
          }];
        },
      },
    },
  };
}

function installTrustedInputDebugger(chrome) {
  chrome.api.debugger = {
    async attach(target, version) {
      chrome.calls.debuggerAttach.push({ target, version });
    },
    async sendCommand(target, method, params) {
      chrome.calls.debuggerSendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return { result: { value: { ok: true } } };
      }
      return {};
    },
    async detach(target) {
      chrome.calls.debuggerDetach.push(target);
    },
  };
}

function installReleaseFailureDebugger(chrome) {
  chrome.api.debugger = {
    async attach(target, version) {
      chrome.calls.debuggerAttach.push({ target, version });
    },
    async sendCommand(target, method, params) {
      chrome.calls.debuggerSendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return { result: { value: { ok: true } } };
      }
      if (params.type === "mouseReleased") {
        throw new Error("Target navigated during release");
      }
      return {};
    },
    async detach(target) {
      chrome.calls.debuggerDetach.push(target);
    },
  };
}

async function runMainWorldActivation(
  func,
  {
    commitAfterFocus = true,
    clickChangesComposer = true,
    clickRemovesAttachment = false,
    focusRemovesAttachment = false,
    composerText = "CORTEX-FRENCH-ATTACHMENT-SEND",
    attachmentLabel = "cortex-upload-proof.txt",
    attachmentClass = null,
    attachmentRole = null,
    attachmentAriaLabel = null,
    activationOptions = {},
    outsideSendRect = null,
  } = {},
) {
  let committed = false;
  let commitPending = false;
  let clickCount = 0;
  let attachmentPresent = true;
  class FakeButton {
    constructor(label, rect = { left: 392.5, top: 693.25, width: 40, height: 20 }) {
      this.label = label;
      this.rect = rect;
      this.disabled = false;
    }

    getAttribute(name) {
      return name === "aria-label" ? this.label : null;
    }

    getClientRects() { return [{}]; }

    getBoundingClientRect() {
      return this.rect;
    }

    focus() {
      if (commitAfterFocus) commitPending = true;
    }

    click() {
      clickCount += 1;
      if (committed && clickChangesComposer) {
        composer.innerText = "";
        composer.textContent = "";
      }
      if (committed && clickRemovesAttachment) attachmentPresent = false;
    }
  }
  const send = new FakeButton("Envoyer le prompt");
  const outsideSend = outsideSendRect
    ? new FakeButton("Envoyer le prompt", outsideSendRect)
    : null;
  const attachment = {
    innerText: attachmentLabel,
    textContent: attachmentLabel,
    getAttribute(name) {
      return ({
        class: attachmentClass,
        role: attachmentRole,
        "aria-label": attachmentAriaLabel,
      })[name] ?? null;
    },
  };
  const form = {
    querySelector(selector) {
      if (
        selector === "button[data-testid=send-button]"
        || selector === "button[aria-label='Envoyer le prompt']"
        || selector === "button[aria-label*=\"Envoyer\"]"
        || selector === "button[aria-label*='Envoyer']"
      ) return send;
      return null;
    },
    querySelectorAll(selector) {
      if (selector.includes("attachment")) return attachmentPresent ? [attachment] : [];
      return [];
    },
  };
  const composer = {
    innerText: composerText,
    textContent: composerText,
    closest(selector) {
      return selector === "form" ? form : null;
    },
  };
  const document = {
    querySelector(selector) {
      if (
        selector === "#prompt-textarea"
        || selector === "textarea[data-testid=prompt-textarea]"
        || selector === "div[contenteditable=true][data-testid=prompt-textarea]"
        || selector === "form div[contenteditable=true]"
      ) return composer;
      if (
        selector === "button[data-testid=send-button]"
        || selector === "button[aria-label='Envoyer le prompt']"
        || selector === "button[aria-label*=\"Envoyer\"]"
        || selector === "button[aria-label*='Envoyer']"
      ) return outsideSend || send;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-message-author-role]") return [];
      if (selector.includes("attachment")) return attachmentPresent ? [attachment] : [];
      return [];
    },
  };
  composer.focus = () => {
    document.activeElement = composer;
  };
  const result = await runInNewContext(
    `(${func.toString()})(${JSON.stringify(activationOptions)})`,
    {
    document,
    location: { href: "https://chatgpt.com/c/french-attachment" },
    HTMLButtonElement: FakeButton,
    Promise,
    setTimeout: (callback) => {
      if (commitPending) {
        committed = true;
        if (focusRemovesAttachment) attachmentPresent = false;
      }
      callback();
    },
    clearTimeout,
    },
  );
  return { result, composer, clickCount, send, outsideSend };
}

function evaluateTrustedInputRevalidation(
  expression,
  {
    origin = "https://chatgpt.com",
    pathname = "/c/trusted-send",
    hitSend = true,
    attachmentLabel = "cortex-upload-proof.txt",
    attachmentClass = null,
    attachmentRole = null,
    attachmentAriaLabel = null,
    composerText = "",
  } = {},
) {
  class FakeButton {
    constructor() {
      this.disabled = false;
    }

    getClientRects() { return [{}]; }

    getBoundingClientRect() {
      return { left: 390, top: 690, width: 40, height: 20 };
    }

    contains(node) { return node === this; }
  }
  const send = new FakeButton();
  const attachment = {
    innerText: attachmentLabel,
    textContent: attachmentLabel,
    getAttribute(name) {
      return ({
        class: attachmentClass,
        role: attachmentRole,
        "aria-label": attachmentAriaLabel,
        "data-filename": attachmentClass ? null : attachmentLabel,
      })[name] ?? null;
    },
  };
  const form = {
    querySelector(selector) {
      return selector.includes("send-button") || selector.includes("Send") || selector.includes("Envoyer")
        ? send
        : null;
    },
    querySelectorAll(selector) {
      if (attachmentClass?.includes("file-tile")) {
        return selector.includes("[role='group'][class*='file-tile'][aria-label]")
          ? [attachment]
          : [];
      }
      return selector.includes("attachment") || selector.includes("file-")
        ? [attachment]
        : [];
    },
  };
  const composer = {
    innerText: composerText,
    textContent: composerText,
    closest(selector) {
      return selector === "form" ? form : null;
    },
  };
  const document = {
    querySelector(selector) {
      return selector.includes("prompt-textarea") ? composer : null;
    },
    elementFromPoint() {
      return hitSend ? send : { overlay: true };
    },
  };
  return runInNewContext(expression, {
    document,
    location: { origin, pathname },
    HTMLButtonElement: FakeButton,
  });
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

test("releasing an uncertain writer quarantines its dirty tab from every session class", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/" },
  ]);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-dirty", 32]]),
    reusableWriterTabs: new Set(),
  };
  const sessionStorage = {};
  chrome.api.storage = {
    session: {
      async get(key) {
        return { [key]: sessionStorage[key] };
      },
      async set(values) {
        Object.assign(sessionStorage, values);
      },
    },
    local: {
      async get(key) {
        return { [key]: sessionStorage[key] };
      },
      async set(values) {
        Object.assign(sessionStorage, values);
      },
    },
  };

  await routeCommand(context, {
    session: "cortex-conv-dirty",
    action: "release_session",
    payload: { reusable: false },
  });
  const restartedContext = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map(),
    reusableWriterTabs: new Set(),
    quarantinedWriterTabs: new Set(),
  };
  await restoreQuarantinedWriterTabs(restartedContext);
  const opened = [];
  for (const session of [
    "cortex-conv-clean",
    "cortex-view-read-only",
    "cortex-missions-read-only",
    "cortex-screenshot-read-only",
  ]) {
    opened.push(await routeCommand(restartedContext, {
      session,
      action: "open_chatgpt",
      payload: {},
    }));
  }

  assert.equal(opened.every((entry) => entry.tab_id !== 32), true);
  assert.equal(restartedContext.reusableWriterTabs.size, 0);
  assert.equal(restartedContext.quarantinedWriterTabs.has(32), true);
  assert.deepEqual(chrome.calls.update.filter(({ tabId }) => tabId === 32), []);
  assert.equal(chrome.calls.create.length >= 1, true);
});

test("an uncertain writer release is refused when its quarantine cannot be persisted", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/" },
  ]);
  chrome.api.storage = {
    session: {
      async set() { throw new Error("session storage unavailable"); },
    },
    local: {
      async set() { throw new Error("local storage unavailable"); },
    },
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-dirty", 32]]),
    reusableWriterTabs: new Set(),
    quarantinedWriterTabs: new Set(),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-dirty",
      action: "release_session",
      payload: { reusable: false },
    }),
    (error) => error.code === "QUARANTINE_PERSIST_FAILED",
  );

  assert.equal(context.sessionTabs.get("cortex-conv-dirty"), 32);
  assert.equal(context.quarantinedWriterTabs.has(32), true);
});

test("read-only allocation fails closed when durable quarantine cannot be restored", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, url: "https://chatgpt.com/" },
  ]);
  chrome.api.storage = {
    session: {
      async get() { return { quarantinedWriterTabIds: [] }; },
    },
    local: {
      async get() { throw new Error("durable storage unavailable"); },
    },
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map(),
    reusableWriterTabs: new Set(),
    quarantinedWriterTabs: new Set(),
  };

  await restoreQuarantinedWriterTabs(context);
  await assert.rejects(
    routeCommand(context, {
      session: "cortex-view-read-only",
      action: "open_chatgpt",
      payload: {},
    }),
    (error) => error.code === "QUARANTINE_STATE_UNAVAILABLE",
  );
  assert.deepEqual(chrome.calls.update, []);
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
  installTrustedInputDebugger(chrome);
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

test("concurrent writer sends serialize activation and refocus each exact tab", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
    { id: 33, windowId: 7, index: 2, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installTrustedInputDebugger(chrome);
  let releaseFirstPreparation;
  const firstPreparation = new Promise((resolve) => {
    releaseFirstPreparation = resolve;
  });
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (tabId === 32 && message.action === "prepare_text") {
      await firstPreparation;
    }
    return { ok: true };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([
      ["cortex-conv-writer-a", 32],
      ["cortex-conv-writer-b", 33],
    ]),
  };

  const writerA = routeCommand(context, {
    session: "cortex-conv-writer-a",
    action: "send_text",
    payload: { text: "CORTEX-CONCURRENT-SEND-A" },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const writerB = routeCommand(context, {
    session: "cortex-conv-writer-b",
    action: "send_text",
    payload: { text: "CORTEX-CONCURRENT-SEND-B" },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const preparationsBeforeRelease = chrome.calls.sendMessage.filter(
    (call) => call.message.action === "prepare_text",
  ).length;
  releaseFirstPreparation();
  await Promise.all([writerA, writerB]);

  assert.equal(preparationsBeforeRelease, 1);
  assert.deepEqual(
    chrome.calls.sendMessage
      .filter((call) => call.message.action === "prepare_text")
      .map((call) => call.tabId),
    [32, 33],
  );
  assert.deepEqual(
    chrome.calls.update
      .filter((call) => call.options.active === true)
      .map((call) => call.tabId),
    [32, 32, 33, 33],
  );
});

test("an expired delivery command is refused before composer preparation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installTrustedInputDebugger(chrome);
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-expired", 32]]),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-expired",
      action: "send_text",
      payload: { text: "CORTEX-EXPIRED-SEND" },
      timeout_ms: 1,
    }),
    (error) => error.code === "PRE_DELIVERY_NOT_READY",
  );

  assert.equal(chrome.calls.sendMessage.length, 0);
  assert.equal(chrome.calls.debuggerAttach.length, 0);
});

test("a pre-delivery failure releases the next writer activation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
    { id: 33, windowId: 7, index: 2, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installTrustedInputDebugger(chrome);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (tabId === 32) {
      return {
        ok: false,
        error: { code: "COMPOSER_MISSING", message: "synthetic stale composer" },
      };
    }
    return { ok: true };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([
      ["cortex-conv-failing", 32],
      ["cortex-conv-following", 33],
    ]),
  };

  const results = await Promise.allSettled([
    routeCommand(context, {
      session: "cortex-conv-failing",
      action: "send_text",
      payload: { text: "CORTEX-PRE-DELIVERY-FAILURE" },
    }),
    routeCommand(context, {
      session: "cortex-conv-following",
      action: "send_text",
      payload: { text: "CORTEX-FOLLOWING-SEND" },
    }),
  ]);

  assert.equal(results[0].status, "rejected");
  assert.equal(results[0].reason.code, "PRE_DELIVERY_NOT_READY");
  assert.equal(results[1].status, "fulfilled");
  assert.deepEqual(results[1].value, { ok: true });
  assert.deepEqual(
    chrome.calls.sendMessage.map((call) => call.tabId),
    [32, 33],
  );
});

test("a trusted send dispatches exactly one CDP mouse click then detaches", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{
      result: {
        ok: true,
        activation_started: false,
        point: { x: 412.5, y: 703.25 },
      },
    }];
  };
  const debuggerCalls = { attach: [], sendCommand: [], detach: [] };
  chrome.api.debugger = {
    async attach(target, version) {
      debuggerCalls.attach.push({ target, version });
    },
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return { result: { value: { ok: true } } };
      }
      return {};
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-TRUSTED-SEND" },
  });

  assert.deepEqual(result, { ok: true });
  assert.deepEqual(debuggerCalls.attach, [{ target: { tabId: 32 }, version: "1.3" }]);
  assert.equal(debuggerCalls.sendCommand[0].method, "Runtime.evaluate");
  assert.equal(debuggerCalls.sendCommand[0].params.returnByValue, true);
  assert.deepEqual(
    debuggerCalls.sendCommand.map((call) => call.params.type || call.method),
    ["Runtime.evaluate", "mouseMoved", "Runtime.evaluate", "mousePressed", "mouseReleased"],
  );
  const moved = debuggerCalls.sendCommand.find((call) => call.params.type === "mouseMoved");
  const pressed = debuggerCalls.sendCommand.find((call) => call.params.type === "mousePressed");
  const released = debuggerCalls.sendCommand.find((call) => call.params.type === "mouseReleased");
  assert.deepEqual(
    [moved.params.buttons, pressed.params.buttons, released.params.buttons],
    [0, 1, 0],
  );
  assert.deepEqual(
    [moved.params.button, pressed.params.button, released.params.button],
    ["none", "left", "left"],
  );
  assert.deepEqual(
    [moved.params.x, moved.params.y, pressed.params.x, pressed.params.y],
    [412.5, 703.25, 412.5, 703.25],
  );
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
});

test("a long composer reflow refreshes the trusted point before mousePressed", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  const refreshedPoints = [
    { x: 420, y: 710 },
    { x: 425, y: 715 },
    { x: 430, y: 720 },
    { x: 435, y: 725 },
    { x: 440, y: 730 },
    { x: 440, y: 730 },
  ];
  const debuggerCalls = [];
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(target, method, params) {
      debuggerCalls.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return { result: { value: { ok: true, point: refreshedPoints.shift() } } };
      }
      return {};
    },
    async detach() {},
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-LONG-CONTRACT-REFLOW" },
  });

  assert.deepEqual(result, { ok: true });
  assert.deepEqual(
    debuggerCalls.map((call) => call.params.type || call.method),
    [
      "Runtime.evaluate",
      "mouseMoved",
      "Runtime.evaluate",
      "mouseMoved",
      "Runtime.evaluate",
      "mouseMoved",
      "Runtime.evaluate",
      "mouseMoved",
      "Runtime.evaluate",
      "mouseMoved",
      "Runtime.evaluate",
      "mousePressed",
      "mouseReleased",
    ],
  );
  assert.deepEqual(
    debuggerCalls
      .filter((call) => call.params.type === "mouseMoved")
      .map((call) => [call.params.x, call.params.y]),
    [[420, 710], [425, 715], [430, 720], [435, 725], [440, 730]],
  );
  const pressed = debuggerCalls.find((call) => call.params.type === "mousePressed");
  assert.deepEqual([pressed.params.x, pressed.params.y], [440, 730]);
});

test("a debugger attach failure is rejected before any delivery input", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  const debuggerCalls = { attach: 0, sendCommand: 0, detach: 0 };
  chrome.api.debugger = {
    async attach() {
      debuggerCalls.attach += 1;
      throw new Error("Another debugger is already attached");
    },
    async sendCommand() {
      debuggerCalls.sendCommand += 1;
    },
    async detach() {
      debuggerCalls.detach += 1;
    },
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
      payload: { text: "CORTEX-ATTACH-FAILS-SAFELY" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.deepEqual(debuggerCalls, { attach: 1, sendCommand: 0, detach: 0 });
  assert.equal(chrome.calls.executeScript.length, 1);
});

test("a failure after mousePressed is uncertain, detached, and never replayed", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "get_state") {
      return { ok: true, result: { messages: [] } };
    }
    return {
      ok: true,
      result: { ok: true, user_message_ids: ["user-before"] },
    };
  };
  const debuggerCalls = { attach: [], sendCommand: [], detach: [] };
  chrome.api.debugger = {
    async attach(target, version) {
      debuggerCalls.attach.push({ target, version });
    },
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return { result: { value: { ok: true } } };
      }
      if (params.type === "mouseReleased") {
        throw new Error("Target closed during release");
      }
      return {};
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
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
      payload: { text: "CORTEX-NO-REPLAY-AFTER-PRESS" },
    }),
    (error) => error.code === "DELIVERY_UNCERTAIN",
  );
  assert.equal(debuggerCalls.attach.length, 1);
  assert.deepEqual(
    debuggerCalls.sendCommand.map((call) => call.params.type || call.method),
    ["Runtime.evaluate", "mouseMoved", "Runtime.evaluate", "mousePressed", "mouseReleased"],
  );
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
    "get_state",
  ]);
});

test("a release-channel failure can prove delivery without replaying the click", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "prepare_text") {
      return {
        ok: true,
        result: { ok: true, user_message_ids: ["user-before"] },
      };
    }
    return {
      ok: true,
      result: {
        messages: [{
          id: "user-after",
          role: "user",
          text: "CORTEX-PROVED-AFTER-RELEASE-FAILURE",
          code_blocks: [],
        }],
      },
    };
  };
  const debuggerCalls = { attach: [], sendCommand: [], detach: [] };
  chrome.api.debugger = {
    async attach(target, version) {
      debuggerCalls.attach.push({ target, version });
    },
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return { result: { value: { ok: true } } };
      }
      if (params.type === "mouseReleased") {
        throw new Error("Target navigated during release");
      }
      return {};
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-PROVED-AFTER-RELEASE-FAILURE" },
  });

  assert.deepEqual(result, { ok: true, confirmed_after_navigation: true });
  assert.deepEqual(
    debuggerCalls.sendCommand.map((call) => call.params.type || call.method),
    ["Runtime.evaluate", "mouseMoved", "Runtime.evaluate", "mousePressed", "mouseReleased"],
  );
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
    "get_state",
  ]);
});

test("trusted input revalidation refuses a point covered by another element", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  const debuggerCalls = { sendCommand: [], detach: [] };
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return {
          result: {
            value: evaluateTrustedInputRevalidation(params.expression, { hitSend: false }),
          },
        };
      }
      return {};
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
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
      payload: { text: "CORTEX-HIT-TEST" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.deepEqual(
    debuggerCalls.sendCommand.map((call) => call.method),
    ["Runtime.evaluate"],
  );
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
});

test("trusted input revalidation reacquires a transiently replaced send control", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{
      result: {
        ok: true,
        point: { x: 410, y: 700 },
        url: "https://chatgpt.com/c/trusted-send",
      },
    }];
  };
  const debuggerCalls = { sendCommand: [], detach: [] };
  let evaluations = 0;
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        evaluations += 1;
        if (evaluations === 1 || evaluations === 3) {
          return {
            result: {
              value: { ok: false, error: "send control changed before trusted input" },
            },
          };
        }
        return {
          result: {
            value: { ok: true, point: { x: 412, y: 702 } },
          },
        };
      }
      return {};
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-TRANSIENT-SEND-CONTROL" },
    timeout_ms: 5_000,
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(evaluations >= 4, true);
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
});

test("trusted input retry refuses a composer changed before trusted input", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{
      result: {
        ok: true,
        point: { x: 410, y: 700 },
        url: "https://chatgpt.com/c/trusted-send",
        composer_text: "EXPECTED CORTEX REPORT",
      },
    }];
  };
  const debuggerCalls = { sendCommand: [], detach: [] };
  let evaluations = 0;
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        evaluations += 1;
        if (evaluations === 1) {
          return {
            result: {
              value: { ok: false, error: "send control changed before trusted input" },
            },
          };
        }
        return {
          result: {
            value: evaluateTrustedInputRevalidation(params.expression, {
              composerText: "REPLACED USER DRAFT",
            }),
          },
        };
      }
      return {};
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
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
      payload: { text: "EXPECTED CORTEX REPORT" },
      timeout_ms: 5_000,
    }),
    (error) => error.code === "SEND_REJECTED"
      && error.message === "composer changed before trusted input",
  );
  assert.equal(evaluations, 2);
  assert.deepEqual(
    debuggerCalls.sendCommand.map((call) => call.method),
    ["Runtime.evaluate", "Runtime.evaluate"],
  );
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
});

test("trusted input revalidation refuses a conversation changed before mousePressed", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{
      result: {
        ok: true,
        point: { x: 410, y: 700 },
        url: "https://chatgpt.com/c/trusted-send",
      },
    }];
  };
  const debuggerCalls = { sendCommand: [], detach: [] };
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return {
          result: {
            value: evaluateTrustedInputRevalidation(params.expression, {
              pathname: "/c/different-conversation",
            }),
          },
        };
      }
      return {};
    },
    async detach(target) {
      debuggerCalls.detach.push(target);
    },
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
      payload: { text: "CORTEX-URL-REVALIDATION" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.deepEqual(
    debuggerCalls.sendCommand.map((call) => call.method),
    ["Runtime.evaluate"],
  );
  assert.deepEqual(debuggerCalls.detach, [{ tabId: 32 }]);
});

test("trusted input revalidation recognizes an exact file-tile aria-label", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{
      result: {
        ok: true,
        point: { x: 410, y: 700 },
        url: "https://chatgpt.com/c/trusted-send",
        attachment_label: "cortex-upload-proof.txt",
      },
    }];
  };
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(_target, method, params) {
      if (method === "Runtime.evaluate") {
        return {
          result: {
            value: evaluateTrustedInputRevalidation(params.expression, {
              attachmentLabel: "visible message text must not become a filename",
              attachmentClass: "group/file-tile rounded-xl",
              attachmentRole: "group",
              attachmentAriaLabel: "cortex-upload-proof.txt",
            }),
          },
        };
      }
      return {};
    },
    async detach() {},
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-FILE-TILE-REVALIDATION" },
  });

  assert.deepEqual(result, { ok: true });
});

test("text with a file refuses any non-native activation before debugger input", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  const debuggerCalls = [];
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(target, method, params) {
      debuggerCalls.push({ target, method, params });
      if (method === "Runtime.evaluate") {
        return {
          result: {
            value: evaluateTrustedInputRevalidation(params.expression, {
              attachmentLabel: "different-file.txt",
            }),
          },
        };
      }
      return {};
    },
    async detach() {},
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
      payload: {
        text: "CORTEX-FILE-NAME-REVALIDATION",
        name: "cortex-upload-proof.txt",
      },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.deepEqual(chrome.calls.executeScript[0].args, [{
    expectedAttachmentName: "cortex-upload-proof.txt",
  }]);
  assert.deepEqual(debuggerCalls, []);
});

test("MAIN-world preparation scopes the send control to the composer form", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/trusted-send" },
  ]);
  installTrustedInputDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      outsideSendRect: { left: 10, top: 20, width: 20, height: 20 },
      activationOptions: options.args?.[0],
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-FORM-SCOPED-SEND" },
  });

  assert.deepEqual(result, { ok: true });
  const press = chrome.calls.debuggerSendCommand.find(
    (call) => call.params.type === "mousePressed",
  );
  assert.equal(press.params.x, 412.5);
  assert.equal(press.params.y, 703.25);
  assert.equal(chrome.activation.clickCount, 0);
});

test("the exact ChatGPT file-tile is handed to the verified native activation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/french-attachment" },
  ]);
  installTrustedInputDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      activationOptions: options.args?.[0],
      attachmentLabel: "visible message text must not become a filename",
      attachmentClass: "group/file-tile rounded-xl",
      attachmentRole: "group",
      attachmentAriaLabel: "cortex-upload-proof(20260824-015544).txt",
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: {
      text: "CORTEX-FRENCH-ATTACHMENT-SEND",
      name: "cortex-upload-proof.txt",
      native_activation: true,
    },
  });

  assert.deepEqual(result, {
    ok: true,
    native_activation: true,
    url: "https://chatgpt.com/c/french-attachment",
    attachment_name: "cortex-upload-proof.txt",
    before_user_message_ids: [],
  });
  assert.equal(chrome.activation.clickCount, 0);
  assert.deepEqual(chrome.calls.debuggerSendCommand, []);
  assert.deepEqual(chrome.calls.windowsUpdate, [{ windowId: 7, options: { focused: true } }]);
  assert.deepEqual(chrome.calls.update, [{ tabId: 32, options: { active: true } }]);
  assert.deepEqual(chrome.calls.debuggerDetach, []);
  assert.equal(
    chrome.activation.result.attachment_label,
    "cortex-upload-proof(20260824-015544).txt",
  );
});

test("MAIN-world file-tile validation rejects prefix, extension and suffix collisions", async () => {
  const invalidTiles = [
    { attachmentAriaLabel: "prefix-cortex-upload-proof.txt" },
    { attachmentAriaLabel: "cortex-upload-proof.txt.backup" },
    { attachmentAriaLabel: "cortex-upload-proof.txt uploaded" },
    { attachmentAriaLabel: "cortex-upload-proof (1).txt" },
    {
      attachmentAriaLabel: "cortex-upload-proof.txt",
      attachmentClass: "not-file-tile",
    },
  ];
  for (const {
    attachmentAriaLabel,
    attachmentClass = "group/file-tile rounded-xl",
  } of invalidTiles) {
    const chrome = chromeWithTabs([
      { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
      { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/file-tile" },
    ]);
    chrome.api.tabs.sendMessage = async (tabId, message) => {
      chrome.calls.sendMessage.push({ tabId, message });
      return {
        ok: true,
        result: { ok: true, user_message_ids: ["user-before"] },
      };
    };
    chrome.api.scripting.executeScript = async (options) => {
      chrome.calls.executeScript.push(options);
      const activation = await runMainWorldActivation(options.func, {
        composerText: "",
        attachmentLabel: "cortex-upload-proof.txt",
        attachmentClass,
        attachmentRole: "group",
        attachmentAriaLabel,
        activationOptions: options.args?.[0],
      });
      chrome.activation = activation;
      return [{ result: activation.result }];
    };
    const context = {
      chrome: chrome.api,
      cortexTab: { id: 31, windowId: 7, index: 0 },
      sessionTabs: new Map([["cortex-conv-file-tile", 32]]),
      activationConfirmationTimeoutMs: 0,
    };

    await assert.rejects(
      routeCommand(context, {
        session: "cortex-conv-file-tile",
        action: "send_bare",
        payload: {
          name: "cortex-upload-proof.txt",
          native_activation: true,
        },
      }),
      (error) => error.code === "SEND_REJECTED",
      attachmentAriaLabel,
    );
    assert.equal(chrome.activation.clickCount, 0);
  }
});

test("MAIN-world preparation never invokes an untrusted DOM click", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/french-attachment" },
  ]);
  installTrustedInputDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      clickChangesComposer: false,
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-FRENCH-ATTACHMENT-SEND" },
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(chrome.activation.clickCount, 0);
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(
    chrome.calls.debuggerSendCommand.map((call) => call.params.type || call.method),
    ["Runtime.evaluate", "mouseMoved", "Runtime.evaluate", "mousePressed", "mouseReleased"],
  );
});

test("a focus-driven React rerender cannot consume the trusted send activation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/french-attachment" },
  ]);
  installTrustedInputDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      clickChangesComposer: false,
      focusRemovesAttachment: true,
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-writer", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-FRENCH-ATTACHMENT-SEND" },
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(chrome.activation.clickCount, 0);
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(
    chrome.calls.debuggerSendCommand.map((call) => call.params.type || call.method),
    ["Runtime.evaluate", "mouseMoved", "Runtime.evaluate", "mousePressed", "mouseReleased"],
  );
});

test("an attachment-only send validates the named chip then requests native activation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/file-only" },
  ]);
  installTrustedInputDebugger(chrome);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    return {
      ok: true,
      result: { ok: true, user_message_ids: ["user-before"] },
    };
  };
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      composerText: "",
      clickRemovesAttachment: true,
      attachmentLabel: "cortex-upload-proof.txt Document",
      activationOptions: options.args?.[0],
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-file-only", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-file-only",
    action: "send_bare",
    payload: { name: "cortex-upload-proof.txt", native_activation: true },
  });

  assert.deepEqual(result, {
    ok: true,
    native_activation: true,
    url: "https://chatgpt.com/c/french-attachment",
    attachment_name: "cortex-upload-proof.txt",
    before_user_message_ids: ["user-before"],
  });
  assert.equal(chrome.calls.sendMessage.length, 1);
  assert.equal(chrome.calls.sendMessage[0].message.action, "send_bare");
  assert.deepEqual(chrome.calls.sendMessage[0].message.payload, {
    name: "cortex-upload-proof.txt",
    native_activation: true,
  });
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.equal(chrome.calls.executeScript[0].world, "MAIN");
  assert.deepEqual(chrome.calls.executeScript[0].args, [{
    expectedAttachmentName: "cortex-upload-proof.txt",
  }]);
  assert.equal(chrome.activation.clickCount, 0);
  assert.deepEqual(chrome.calls.debuggerSendCommand, []);
  assert.deepEqual(chrome.calls.debuggerDetach, []);
  assert.deepEqual(chrome.calls.update, [{ tabId: 32, options: { active: true } }]);
});

test("an attachment-only send refuses a different chip before any click", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/file-only" },
  ]);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    return {
      ok: true,
      result: { ok: true, user_message_ids: ["user-before"] },
    };
  };
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      composerText: "",
      attachmentLabel: "different-file.txt",
      activationOptions: options.args?.[0],
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-file-only", 32]]),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-file-only",
      action: "send_bare",
      payload: { name: "cortex-upload-proof.txt" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.equal(chrome.activation.clickCount, 0);
});

test("an attachment-only send rejects a filename prefix collision before any click", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/file-only" },
  ]);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    return {
      ok: true,
      result: { ok: true, user_message_ids: ["user-before"] },
    };
  };
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      composerText: "",
      attachmentLabel: "cortex-upload-proof.txt.backup",
      activationOptions: options.args?.[0],
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-file-only", 32]]),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-file-only",
      action: "send_bare",
      payload: { name: "cortex-upload-proof.txt" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.equal(chrome.activation.clickCount, 0);
});

test("an attachment-only native preparation activates the tab exactly once", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/c/file-only" },
  ]);
  installTrustedInputDebugger(chrome);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    return {
      ok: true,
      result: { ok: true, user_message_ids: ["user-before"] },
    };
  };
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    const activation = await runMainWorldActivation(options.func, {
      composerText: "",
      clickChangesComposer: false,
      attachmentLabel: "cortex-upload-proof.txt",
      activationOptions: options.args?.[0],
    });
    chrome.activation = activation;
    return [{ result: activation.result }];
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-file-only", 32]]),
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-file-only",
    action: "send_bare",
    payload: { name: "cortex-upload-proof.txt", native_activation: true },
  });

  assert.equal(result.native_activation, true);
  assert.equal(result.attachment_name, "cortex-upload-proof.txt");
  assert.equal(chrome.activation.clickCount, 0);
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "send_bare",
  ]);
  assert.deepEqual(chrome.calls.debuggerSendCommand, []);
  assert.deepEqual(chrome.calls.update, [{ tabId: 32, options: { active: true } }]);
});

test("native attachment preparation returns the exact pre-send user baseline", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installReleaseFailureDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "send_bare") {
      return {
        ok: true,
        result: { ok: true, user_message_ids: ["old-exact"] },
      };
    }
    return {
      ok: true,
      result: {
        messages: [
          {
            id: "old-exact",
            role: "user",
            text: "",
            code_blocks: [],
            attachments: [{ name: "cortex-upload-proof.txt" }],
          },
          {
            id: "new-wrong",
            role: "user",
            text: "",
            code_blocks: [],
            attachments: [{ name: "cortex-upload-proof.txt.backup" }],
          },
        ],
      },
    };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-file-only", 32]]),
    activationConfirmationTimeoutMs: 0,
  };

  const result = await routeCommand(context, {
    session: "cortex-conv-file-only",
    action: "send_bare",
    payload: { name: "cortex-upload-proof.txt", native_activation: true },
  });
  assert.equal(result.native_activation, true);
  assert.deepEqual(result.before_user_message_ids, ["old-exact"]);
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "send_bare",
  ]);
  assert.deepEqual(chrome.calls.debuggerSendCommand, []);
});

test("attachment preparation without a native request never reaches debugger input", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installReleaseFailureDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "send_bare") {
      return {
        ok: true,
        result: { ok: true, user_message_ids: ["user-before"] },
      };
    }
    return {
      ok: true,
      result: {
        messages: [{
          id: "user-after",
          role: "user",
          text: "",
          code_blocks: [],
          attachments: [{ name: "cortex-upload-proof(1).txt" }],
        }],
      },
    };
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([["cortex-conv-file-only", 32]]),
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-file-only",
      action: "send_bare",
      payload: { name: "cortex-upload-proof.txt" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "send_bare",
  ]);
  assert.deepEqual(chrome.calls.debuggerSendCommand, []);
});

test("post-activation attachment proof is case, diacritic and ASCII-suffix strict", async () => {
  const confirmAttachment = async (actualName, expectedName = "cortex-upload-proof.txt") => {
    const chrome = chromeWithTabs([
      { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
      { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
    ]);
    chrome.api.scripting.executeScript = async (options) => {
      chrome.calls.executeScript.push(options);
      return [{
        result: {
          activation_started: true,
          error: "synthetic lost activation response",
        },
      }];
    };
    chrome.api.tabs.sendMessage = async (tabId, message) => {
      chrome.calls.sendMessage.push({ tabId, message });
      if (message.action === "send_bare") {
        return {
          ok: true,
          result: { ok: true, user_message_ids: ["user-before"] },
        };
      }
      return {
        ok: true,
        result: {
          messages: [{
            id: "user-after",
            role: "user",
            text: "",
            code_blocks: [],
            attachments: [{ name: actualName }],
          }],
        },
      };
    };
    const context = {
      chrome: chrome.api,
      cortexTab: { id: 31, windowId: 7, index: 0 },
      sessionTabs: new Map([["cortex-conv-file-proof", 32]]),
      activationConfirmationTimeoutMs: 0,
    };
    return routeCommand(context, {
      session: "cortex-conv-file-proof",
      action: "send_bare",
      payload: { name: expectedName },
    });
  };

  assert.deepEqual(
    await confirmAttachment("cortex-upload-proof(20260824-015544).txt"),
    { ok: true, confirmed_after_navigation: true },
  );
  for (const [actualName, expectedName] of [
    ["Cortex-upload-proof.txt", "cortex-upload-proof.txt"],
    ["resume.txt", "résumé.txt"],
    ["cortex-upload-proof(١).txt", "cortex-upload-proof.txt"],
    ["cortex-upload-proof (1).txt", "cortex-upload-proof.txt"],
    ["folder/cortex-upload-proof.txt", "cortex-upload-proof.txt"],
  ]) {
    await assert.rejects(
      confirmAttachment(actualName, expectedName),
      (error) => error.code === "DELIVERY_UNCERTAIN",
      `${actualName} must not prove ${expectedName}`,
    );
  }
});

test("a lost MAIN-world preflight is rejected before delivery", async () => {
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
    (error) => error.code === "SEND_REJECTED",
  );
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
  ]);
  assert.equal(chrome.calls.executeScript.length, 1);
});

test("an empty MAIN-world preflight result is rejected before delivery", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [];
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
      payload: { text: "CORTEX-EMPTY-PREFLIGHT" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
  ]);
});

test("a missing MAIN-world preflight receiver is rejected before delivery", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    throw new Error("Could not establish connection. Receiving end does not exist.");
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
      payload: { text: "CORTEX-MISSING-RECEIVER-NO-REPLAY" },
    }),
    (error) => error.code === "SEND_REJECTED",
  );
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
  ]);
});

test("a new-chat navigation confirms the click from the visible user marker", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installReleaseFailureDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
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

test("a new-chat navigation confirms a new short exact user message", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installReleaseFailureDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "prepare_text") {
      return {
        ok: true,
        result: { ok: true, user_message_ids: ["short-before"] },
      };
    }
    return {
      ok: true,
      result: {
        messages: [
          { id: "short-before", role: "user", text: "ok", code_blocks: [] },
          { id: "short-after", role: "user", text: "ok", code_blocks: [] },
        ],
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
    payload: { text: "ok" },
  });

  assert.deepEqual(result, { ok: true, confirmed_after_navigation: true });
  assert.equal(chrome.calls.executeScript.length, 1);
  assert.deepEqual(chrome.calls.sendMessage.map((call) => call.message.action), [
    "prepare_text",
    "get_state",
  ]);
});

test("a stale short user message cannot confirm a new-chat navigation", async () => {
  const chrome = chromeWithTabs([
    { id: 31, windowId: 7, index: 0, url: "http://127.0.0.1:8420/" },
    { id: 32, windowId: 7, index: 1, status: "complete", url: "https://chatgpt.com/" },
  ]);
  installReleaseFailureDebugger(chrome);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "prepare_text") {
      return {
        ok: true,
        result: { ok: true, user_message_ids: ["short-before"] },
      };
    }
    return {
      ok: true,
      result: {
        messages: [
          { id: "short-before", role: "user", text: "ok", code_blocks: [] },
        ],
      },
    };
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
      payload: { text: "ok" },
    }),
    (error) => error.code === "DELIVERY_UNCERTAIN",
  );
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

test("an action-authorized screenshot must belong to the exact bound tab", async () => {
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
      tab_id: 99,
      url,
      captured_at: Date.now(),
    },
  };

  await assert.rejects(
    routeCommand(context, {
      session: "cortex-conv-screenshot",
      action: "capture_screenshot",
      payload: {},
    }),
    (error) => error.code === "SCREENSHOT_TARGET_MISMATCH",
  );
  assert.equal(context.pendingCapture, null);
});

test("a screenshot refuses a selected tab that no longer matches its expected URL", async () => {
  const actualUrl = "https://chatgpt.com/c/screenshot-other";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url: actualUrl },
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
      payload: { expected_url: "https://chatgpt.com/c/screenshot-proof" },
    }),
    (error) => error.code === "SCREENSHOT_TARGET_MISMATCH",
  );
});

test("a screenshot is discarded when its ChatGPT route changes during capture", async () => {
  const expectedUrl = "https://chatgpt.com/c/screenshot-during-capture";
  const tab = { id: 32, windowId: 7, index: 1, url: expectedUrl };
  const chrome = chromeWithTabs([tab]);
  const privacyEvents = [];
  chrome.api.tabs.sendMessage = async (_tabId, message) => {
    privacyEvents.push(message.action);
    if (message.action === "privacy_mask_begin") {
      return {
        ok: true,
        result: { confirmed: true, token: "private-capture-route", masked_zones: 1 },
      };
    }
    return { ok: true, result: { restored: true } };
  };
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(_target, method) {
      if (method === "Page.captureScreenshot") {
        tab.url = "https://chatgpt.com/c/screenshot-navigated-away";
        return { data: "aGVsbG8td29ybGQ=" };
      }
      return {};
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
      payload: { expected_url: expectedUrl },
    }),
    (error) => error.code === "SCREENSHOT_TARGET_MISMATCH",
  );
  assert.deepEqual(privacyEvents, ["privacy_mask_begin", "privacy_mask_restore"]);
});

test("a screenshot falls back to a CDP capture without any icon click", async () => {
  const url = "https://chatgpt.com/c/screenshot-fallback";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  const privacyEvents = [];
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    privacyEvents.push(message.action);
    if (message.action === "privacy_mask_begin") {
      return {
        ok: true,
        result: { confirmed: true, token: "private-capture-1", masked_zones: 1 },
      };
    }
    if (message.action === "privacy_mask_restore") {
      assert.equal(message.payload.token, "private-capture-1");
      return { ok: true, result: { restored: true } };
    }
    throw new Error(`unexpected content action: ${message.action}`);
  };
  const debuggerCalls = { attach: [], sendCommand: [], detach: [] };
  chrome.api.debugger = {
    async attach(target, version) {
      debuggerCalls.attach.push({ target, version });
    },
    async sendCommand(target, method, params) {
      debuggerCalls.sendCommand.push({ target, method, params });
      privacyEvents.push("capture");
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
  assert.deepEqual(privacyEvents, [
    "privacy_mask_begin",
    "capture",
    "privacy_mask_restore",
  ]);
});

test("a private CDP capture restores the page mask when capture fails", async () => {
  const url = "https://chatgpt.com/c/screenshot-capture-error";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  const privacyEvents = [];
  chrome.api.tabs.sendMessage = async (_tabId, message) => {
    privacyEvents.push(message.action);
    if (message.action === "privacy_mask_begin") {
      return {
        ok: true,
        result: { confirmed: true, token: "private-capture-error", masked_zones: 1 },
      };
    }
    if (message.action === "privacy_mask_restore") {
      return { ok: true, result: { restored: true } };
    }
    throw new Error(`unexpected content action: ${message.action}`);
  };
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(_target, method) {
      assert.equal(method, "Page.captureScreenshot");
      privacyEvents.push("capture");
      throw new Error("synthetic capture failure");
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
  assert.deepEqual(privacyEvents, [
    "privacy_mask_begin",
    "capture",
    "privacy_mask_restore",
  ]);
});

test("a private capture discards pixels if exact mask restoration cannot be attested", async () => {
  const url = "https://chatgpt.com/c/screenshot-content-disappears";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  const privacyEvents = [];
  chrome.api.tabs.sendMessage = async (_tabId, message) => {
    privacyEvents.push(message.action);
    if (message.action === "privacy_mask_begin") {
      return {
        ok: true,
        result: {
          confirmed: true,
          token: "private-capture-disappears",
          masked_zones: 1,
        },
      };
    }
    throw new Error("Could not establish connection. Receiving end does not exist.");
  };
  chrome.api.scripting.executeScript = async (options) => {
    privacyEvents.push("forced_restore");
    assert.deepEqual(options.target, { tabId: 32 });
    assert.deepEqual(options.args, [{ token: "private-capture-disappears" }]);
    return [{ result: { restored: true } }];
  };
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(_target, method) {
      assert.equal(method, "Page.captureScreenshot");
      privacyEvents.push("capture");
      return { data: "cHJpdmF0ZS1jYXB0dXJl" };
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
    (error) => error.code === "SCREENSHOT_PRIVACY_RESTORE_FAILED",
  );
  assert.equal(context.pendingCapture, null);
  assert.deepEqual(privacyEvents, [
    "privacy_mask_begin",
    "capture",
    "privacy_mask_restore",
    "forced_restore",
  ]);
});

test("private capture cycles on one tab are serialized across restoration failure", async () => {
  const tab = { id: 32, windowId: 7, url: "https://chatgpt.com/c/private-race" };
  let activeMask = null;
  let restoreCalls = 0;
  let releaseA;
  let releaseB;
  const captureAReady = new Promise((resolve) => { releaseA = resolve; });
  const captureBReady = new Promise((resolve) => { releaseB = resolve; });
  let aStarted;
  let bStarted;
  const sawA = new Promise((resolve) => { aStarted = resolve; });
  const sawB = new Promise((resolve) => { bStarted = resolve; });
  const chromeApi = {
    tabs: {
      async sendMessage(_tabId, message) {
        if (message.action === "privacy_mask_begin") {
          if (!activeMask?.connected) {
            activeMask = { token: `mask-${Date.now()}-${Math.random()}`, references: 0, connected: true };
          }
          activeMask.references += 1;
          return {
            ok: true,
            result: { confirmed: true, token: activeMask.token, masked_zones: 1 },
          };
        }
        restoreCalls += 1;
        if (restoreCalls === 1) throw new Error("first restore channel vanished");
        if (activeMask.references > 1) activeMask.references -= 1;
        else activeMask = null;
        return { ok: true, result: { restored: true } };
      },
    },
    scripting: {
      async executeScript() {
        if (activeMask) activeMask.connected = false;
        return [{ result: { restored: true } }];
      },
    },
  };

  const captureA = withPrivateCaptureMask(chromeApi, tab, async () => {
    aStarted();
    await captureAReady;
    return activeMask?.connected ? "A_MASKED" : "A_UNMASKED";
  });
  await sawA;
  const captureB = withPrivateCaptureMask(chromeApi, tab, async () => {
    bStarted();
    await captureBReady;
    return activeMask?.connected ? "B_MASKED" : "B_UNMASKED";
  });
  await Promise.resolve();
  releaseA();
  await assert.rejects(
    captureA,
    (error) => error.code === "SCREENSHOT_PRIVACY_RESTORE_FAILED",
  );
  await sawB;
  releaseB();
  assert.equal(await captureB, "B_MASKED");
});

test("toolbar capture targets the exact tab through Chrome debugger", async () => {
  const tab = { id: 32, windowId: 7, url: "https://chatgpt.com/c/visible-a" };
  const debuggerCalls = [];
  const chromeApi = {
    tabs: {
      async sendMessage(_tabId, message) {
        if (message.action === "privacy_mask_begin") {
          return {
            ok: true,
            result: { confirmed: true, token: "visible-mask", masked_zones: 1 },
          };
        }
        return { ok: true, result: { restored: true } };
      },
    },
    debugger: {
      async attach(target) { debuggerCalls.push(["attach", target]); },
      async sendCommand(target, method) {
        debuggerCalls.push([method, target]);
        return { data: "ZXhhY3QtdGFi" };
      },
      async detach(target) { debuggerCalls.push(["detach", target]); },
    },
  };

  const result = await captureTabViaDebuggerExactly(chromeApi, tab);

  assert.equal(result, "data:image/png;base64,ZXhhY3QtdGFi");
  assert.deepEqual(debuggerCalls, [
    ["attach", { tabId: 32 }],
    ["Page.captureScreenshot", { tabId: 32 }],
    ["detach", { tabId: 32 }],
  ]);
});

test("a failed privacy mask prevents every CDP capture attempt", async () => {
  const url = "https://chatgpt.com/c/screenshot-mask-error";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  const privacyEvents = [];
  chrome.api.tabs.sendMessage = async (_tabId, message) => {
    privacyEvents.push(message.action);
    return {
      ok: false,
      error: {
        code: "SCREENSHOT_PRIVACY_MASK_FAILED",
        message: "Synthetic mask refusal",
      },
    };
  };
  let debuggerCaptureCount = 0;
  chrome.api.debugger = {
    async attach() {},
    async sendCommand(_target, method) {
      if (method === "Page.captureScreenshot") debuggerCaptureCount += 1;
      throw new Error("capture must not start");
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
    (error) => error.code === "SCREENSHOT_PRIVACY_MASK_FAILED",
  );
  assert.deepEqual(privacyEvents, ["privacy_mask_begin"]);
  assert.equal(debuggerCaptureCount, 0);
});

test("trusted send and screenshot serialize their debugger session on one tab", async () => {
  const url = "https://chatgpt.com/c/shared-debugger";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, status: "complete", url },
  ]);
  chrome.api.scripting.executeScript = async (options) => {
    chrome.calls.executeScript.push(options);
    return [{ result: { ok: true, point: { x: 410, y: 700 } } }];
  };
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "privacy_mask_begin") {
      return {
        ok: true,
        result: { confirmed: true, token: "serialized-mask", masked_zones: 1 },
      };
    }
    if (message.action === "privacy_mask_restore") {
      return { ok: true, result: { restored: true } };
    }
    return { ok: true };
  };
  let releasePress;
  const pressHeld = new Promise((resolve) => {
    releasePress = resolve;
  });
  let pressStarted;
  const sawPress = new Promise((resolve) => {
    pressStarted = resolve;
  });
  const calls = { attach: [], detach: [], active: 0, maxActive: 0 };
  chrome.api.debugger = {
    async attach(target, version) {
      calls.attach.push({ target, version });
      calls.active += 1;
      calls.maxActive = Math.max(calls.maxActive, calls.active);
    },
    async sendCommand(_target, method, params) {
      if (method === "Runtime.evaluate") {
        return { result: { value: { ok: true } } };
      }
      if (method === "Input.dispatchMouseEvent" && params.type === "mousePressed") {
        pressStarted();
        await pressHeld;
        return {};
      }
      if (method === "Page.captureScreenshot") {
        return { data: "c2VyaWFsaXplZC1jYXB0dXJl" };
      }
      return {};
    },
    async detach(target) {
      calls.detach.push(target);
      calls.active -= 1;
    },
  };
  const context = {
    chrome: chrome.api,
    cortexTab: { id: 31, windowId: 7, index: 0 },
    sessionTabs: new Map([
      ["cortex-conv-writer", 32],
      ["cortex-conv-screenshot", 32],
    ]),
    pendingCapture: null,
  };

  const sendPromise = routeCommand(context, {
    session: "cortex-conv-writer",
    action: "send_text",
    payload: { text: "CORTEX-SERIALIZED-DEBUGGER" },
  });
  await sawPress;
  const capturePromise = routeCommand(context, {
    session: "cortex-conv-screenshot",
    action: "capture_screenshot",
    payload: {},
  });
  await Promise.resolve();
  await Promise.resolve();
  const attachCountWhilePressHeld = calls.attach.length;
  releasePress();
  assert.equal(attachCountWhilePressHeld, 1);

  const [send, capture] = await Promise.all([sendPromise, capturePromise]);
  assert.deepEqual(send, { ok: true });
  assert.equal(capture.data_url, "data:image/png;base64,c2VyaWFsaXplZC1jYXB0dXJl");
  assert.equal(calls.attach.length, 2);
  assert.equal(calls.detach.length, 2);
  assert.equal(calls.maxActive, 1);
});

test("a stale action capture is discarded before the CDP fallback runs", async () => {
  const url = "https://chatgpt.com/c/screenshot-stale";
  const chrome = chromeWithTabs([
    { id: 32, windowId: 7, index: 1, url },
  ]);
  chrome.api.tabs.sendMessage = async (tabId, message) => {
    chrome.calls.sendMessage.push({ tabId, message });
    if (message.action === "privacy_mask_begin") {
      return {
        ok: true,
        result: { confirmed: true, token: "stale-mask", masked_zones: 1 },
      };
    }
    if (message.action === "privacy_mask_restore") {
      return { ok: true, result: { restored: true } };
    }
    return { ok: true };
  };
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
  assert.deepEqual(manifest.permissions, ["activeTab", "debugger", "scripting", "storage", "tabGroups"]);
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

test("the extension action records only an exact-tab private screenshot", async () => {
  const source = await readFile(join(EXTENSION_ROOT, "service-worker.js"), "utf8");

  assert.match(source, /chrome\.action\.onClicked\.addListener/);
  assert.match(source, /captureTabViaDebuggerExactly\(chrome, tab\)/);
  assert.equal(source.includes("chrome.tabs.captureVisibleTab"), false);
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
  assert.match(source, /user_message_ids: messages\(\)/);
});

test("prepare_text accepts ChatGPT whitespace normalization for long prompts", async () => {
  const response = await runContentScriptSend(
    "You are the cloud orchestrator for Cortex Bridge.\nYou analyze the global objective.\nYou produce one bounded action.",
    { normalizeComposerWhitespace: true },
  );

  assert.equal(response.ok, true);
  assert.equal(response.result.ok, true);
  assert.equal(response.result.user_message_ids.length, 0);
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

test("attachment readiness accepts ChatGPT timestamped duplicate-name suffixes", async () => {
  const result = await runAttachmentReadiness(
    "cortex-upload-proof(20260824-015544).txt Document",
    "cortex-upload-proof.txt",
  );

  assert.equal(result.ok, true);
  assert.match(result.label, /cortex-upload-proof\(20260824-015544\)\.txt/);
});

test("attachment readiness derives an exact file-tile name only from aria-label", async () => {
  const result = await runAttachmentReadiness(
    "visible message text must not become a filename",
    "cortex-upload-proof.txt",
    {
      attachmentClass: "group/file-tile rounded-xl",
      attachmentRole: "group",
      attachmentAriaLabel: "cortex-upload-proof.txt",
    },
  );

  assert.equal(result.ok, true);
  assert.equal(result.label, "cortex-upload-proof.txt");
});

test("attachment readiness preserves the exact filename case", async () => {
  const result = await runAttachmentReadiness(
    "visible message text must not become a filename",
    "CORTEX-QA-FILE.txt",
    {
      attachmentClass: "group/file-tile rounded-xl",
      attachmentRole: "group",
      attachmentAriaLabel: "CORTEX-QA-FILE.txt",
    },
  );

  assert.equal(result.ok, true);
  assert.equal(result.label, "CORTEX-QA-FILE.txt");
});

test("attachment readiness refuses a file-tile without both role and aria-label", async () => {
  for (const attributes of [
    {
      attachmentClass: "group/file-tile rounded-xl",
      attachmentRole: null,
      attachmentAriaLabel: "cortex-upload-proof.txt",
    },
    {
      attachmentClass: "group/file-tile rounded-xl",
      attachmentRole: "group",
      attachmentAriaLabel: null,
    },
    {
      attachmentClass: "not-file-tile",
      attachmentRole: "group",
      attachmentAriaLabel: "cortex-upload-proof.txt",
    },
  ]) {
    const result = await runAttachmentReadiness(
      "cortex-upload-proof.txt",
      "cortex-upload-proof.txt",
      attributes,
    );
    assert.equal(result.ok, false);
  }
});

test("attachment readiness rejects file-tile name collisions", async () => {
  const invalidAriaLabels = [
    "prefix-cortex-upload-proof.txt",
    "cortex-upload-proof.txt.backup",
    "cortex-upload-proof.txt uploaded",
    "Cortex-upload-proof.txt",
    "córtex-upload-proof.txt",
    "cortex-upload-proof(١).txt",
    "cortex-upload-proof (1).txt",
  ];
  for (const attachmentAriaLabel of invalidAriaLabels) {
    const result = await runAttachmentReadiness(
      "cortex-upload-proof.txt",
      "cortex-upload-proof.txt",
      {
        attachmentClass: "group/file-tile rounded-xl",
        attachmentRole: "group",
        attachmentAriaLabel,
      },
    );
    assert.equal(result.ok, false, attachmentAriaLabel);
  }
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

test("user messages expose named attachments only from explicit file containers", async () => {
  const explicitFile = {
    innerText: "cortex-upload-proof.txt Document",
    textContent: "cortex-upload-proof.txt Document",
    getAttribute(name) {
      if (name === "data-filename") return "cortex-upload-proof.txt";
      if (name === "data-testid") return "file-attachment";
      return null;
    },
  };
  const userMessage = {
    id: "user-with-file",
    innerText: "cortex-upload-proof.txt Document",
    textContent: "cortex-upload-proof.txt Document",
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-file";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === "pre code") return [];
      if (selector.includes("data-testid")) return [explicitFile];
      return [];
    },
  };

  const state = await getContentScriptState([userMessage]);

  assert.deepEqual(Array.from(
    state.messages[0].attachments,
    (attachment) => ({ name: String(attachment.name) }),
  ), [
    { name: "cortex-upload-proof.txt" },
  ]);
});

test("user messages retain a filename from ChatGPT's explicit attachment class", async () => {
  const explicitFile = {
    innerText: "cortex-upload-proof.txt\nDocument",
    textContent: "cortex-upload-proof.txt Document",
    getAttribute() { return null; },
    querySelector() { return null; },
  };
  const userMessage = {
    id: "user-with-class-file",
    innerText: "cortex-upload-proof.txt\nDocument",
    textContent: "cortex-upload-proof.txt Document",
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-class-file";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === "pre code") return [];
      if (selector.includes("[class*='attachment']")) return [explicitFile];
      return [];
    },
  };

  const state = await getContentScriptState([userMessage]);

  assert.deepEqual(Array.from(
    state.messages[0].attachments,
    (attachment) => ({ name: String(attachment.name) }),
  ), [
    { name: "cortex-upload-proof.txt" },
  ]);
});

test("user messages take a file-tile filename only from its explicit aria-label", async () => {
  const explicitFile = {
    innerText: "visible message text must not become a filename",
    textContent: "visible message text must not become a filename",
    getAttribute(name) {
      if (name === "role") return "group";
      if (name === "class") return "group/file-tile rounded-xl";
      if (name === "aria-label") return "cortex-upload-proof(20260824-100339).txt";
      return null;
    },
    querySelector() { return null; },
  };
  const userMessage = {
    id: "user-with-file-tile",
    innerText: "cortex-upload-proof(20260824-100339).txt\nDocument\nSynthetic QA marker",
    textContent: "cortex-upload-proof(20260824-100339).txt Document Synthetic QA marker",
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-file-tile";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === "pre code") return [];
      if (selector.includes("file-tile")) return [explicitFile];
      return [];
    },
  };

  const state = await getContentScriptState([userMessage]);

  assert.deepEqual(Array.from(
    state.messages[0].attachments,
    (attachment) => ({ name: String(attachment.name) }),
  ), [
    { name: "cortex-upload-proof(20260824-100339).txt" },
  ]);
});

test("user message text excludes sibling file-tile metadata", async () => {
  const prompt = "Synthetic QA attachment marker";
  const messageBubble = {
    innerText: prompt,
    textContent: prompt,
  };
  const explicitFile = {
    innerText: "cortex-upload-proof(20260825-175044).txt\nDocument",
    textContent: "cortex-upload-proof(20260825-175044).txt Document",
    getAttribute(name) {
      if (name === "role") return "group";
      if (name === "class") return "group/file-tile rounded-xl";
      if (name === "aria-label") return "cortex-upload-proof(20260825-175044).txt";
      return null;
    },
    querySelector() { return null; },
  };
  const userMessage = {
    id: "user-with-file-tile-and-prompt",
    innerText: `${explicitFile.innerText}\n${prompt}`,
    textContent: `${explicitFile.textContent} ${prompt}`,
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-file-tile-and-prompt";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    querySelector(selector) {
      if (selector === ".user-message-bubble-color") return messageBubble;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "pre code") return [];
      if (selector.includes("file-tile")) return [explicitFile];
      return [];
    },
  };

  const state = await getContentScriptState([userMessage]);

  assert.equal(state.messages[0].text, prompt);
  assert.deepEqual(Array.from(
    state.messages[0].attachments,
    (attachment) => ({ name: String(attachment.name) }),
  ), [
    { name: "cortex-upload-proof(20260825-175044).txt" },
  ]);
});

test("sent user images expose their exact filename from the message image alt", async () => {
  const prompt = "Synthetic screenshot marker";
  const messageBubble = {
    innerText: prompt,
    textContent: prompt,
  };
  const sentImage = {
    innerText: "",
    textContent: "",
    getAttribute(name) {
      if (name === "alt") return "cortex-screenshot-proof.png";
      return null;
    },
    querySelector() { return null; },
  };
  const userMessage = {
    id: "user-with-sent-image",
    innerText: prompt,
    textContent: prompt,
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-sent-image";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    querySelector(selector) {
      if (selector === ".user-message-bubble-color") return messageBubble;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "pre code") return [];
      if (selector.includes("message-image")) return [sentImage];
      return [];
    },
  };

  const state = await getContentScriptState([userMessage]);

  assert.equal(state.messages[0].text, prompt);
  assert.deepEqual(Array.from(
    state.messages[0].attachments,
    (attachment) => ({ name: String(attachment.name) }),
  ), [
    { name: "cortex-screenshot-proof.png" },
  ]);
});

test("user messages include an exact file-tile sibling from their single conversation turn", async () => {
  const explicitFile = {
    innerText: "visible message text must not become a filename",
    textContent: "visible message text must not become a filename",
    getAttribute(name) {
      if (name === "role") return "group";
      if (name === "class") return "group/file-tile rounded-xl";
      if (name === "aria-label") return "cortex-upload-proof(20260824-192812).txt";
      return null;
    },
    querySelector() { return null; },
  };
  let userMessage;
  const turn = {
    querySelectorAll(selector) {
      if (selector === "[data-message-author-role]") return [userMessage];
      if (selector.includes("file-tile")) return [explicitFile];
      return [];
    },
  };
  userMessage = {
    id: "user-with-sibling-file-tile",
    innerText: "Synthetic QA marker",
    textContent: "Synthetic QA marker",
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-sibling-file-tile";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    closest(selector) {
      return selector.includes("conversation-turn-") ? turn : null;
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };

  const state = await getContentScriptState([userMessage]);

  assert.deepEqual(Array.from(
    state.messages[0].attachments,
    (attachment) => ({ name: String(attachment.name) }),
  ), [
    { name: "cortex-upload-proof(20260824-192812).txt" },
  ]);
});

test("user message text that looks like a filename is not an attachment", async () => {
  const userMessage = {
    id: "user-with-filename-text",
    innerText: "cortex-upload-proof.txt",
    textContent: "cortex-upload-proof.txt",
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-filename-text";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };

  const state = await getContentScriptState([userMessage]);

  assert.deepEqual(Array.from(state.messages[0].attachments), []);
});

test("file-tile-like message nodes without strict role and aria-label are refused", async () => {
  const invalidTiles = [
    {
      innerText: "cortex-upload-proof.txt",
      textContent: "cortex-upload-proof.txt",
      getAttribute(name) {
        if (name === "class") return "group/file-tile rounded-xl";
        if (name === "aria-label") return "cortex-upload-proof.txt";
        return null;
      },
      querySelector() { return null; },
    },
    {
      innerText: "cortex-upload-proof.txt",
      textContent: "cortex-upload-proof.txt",
      getAttribute(name) {
        if (name === "class") return "group/file-tile rounded-xl";
        if (name === "role") return "group";
        return null;
      },
      querySelector() { return null; },
    },
    {
      innerText: "cortex-upload-proof.txt",
      textContent: "cortex-upload-proof.txt",
      getAttribute(name) {
        if (name === "class") return "not-file-tile";
        if (name === "role") return "group";
        if (name === "aria-label") return "cortex-upload-proof.txt";
        return null;
      },
      querySelector() { return null; },
    },
  ];
  const userMessage = {
    id: "user-with-invalid-file-tiles",
    innerText: "cortex-upload-proof.txt",
    textContent: "cortex-upload-proof.txt",
    getAttribute(name) {
      if (name === "data-message-id") return "user-with-invalid-file-tiles";
      if (name === "data-message-author-role") return "user";
      return null;
    },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === "pre code") return [];
      if (selector.includes("file-tile")) return invalidTiles;
      return [];
    },
  };

  const state = await getContentScriptState([userMessage]);

  assert.deepEqual(Array.from(state.messages[0].attachments), []);
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

function fakeChromeWithTabs(tabs) {
  const calls = { group: [], groupUpdate: [], groupQuery: [] };
  const chrome = {
    tabs: {
      async get(id) {
        const tab = tabs.find((candidate) => candidate.id === id);
        if (!tab) throw new Error("No tab with id: " + id);
        return tab;
      },
      async group(options) {
        calls.group.push(options);
        const groupId = options.groupId ?? 501;
        for (const id of [options.tabIds].flat()) {
          const tab = tabs.find((candidate) => candidate.id === id);
          if (tab) tab.groupId = groupId;
        }
        return groupId;
      },
    },
    tabGroups: {
      async query(info) {
        calls.groupQuery.push(info);
        return [];
      },
      async update(groupId, props) {
        calls.groupUpdate.push({ groupId, props });
      },
    },
  };
  return { chrome, calls };
}

test("ensureCortexTabGroup groups the console and ChatGPT tabs under one named group", async () => {
  const tabs = [
    { id: 10, windowId: 1, groupId: -1 },
    { id: 11, windowId: 1, groupId: -1 },
  ];
  const { chrome, calls } = fakeChromeWithTabs(tabs);

  const groupId = await ensureCortexTabGroup(chrome, { id: 10, windowId: 1 }, [11]);

  assert.equal(groupId, 501);
  assert.equal(calls.group.length, 1);
  assert.deepEqual([calls.group[0].tabIds].flat().sort(), [10, 11]);
  assert.equal(calls.groupUpdate.length, 1);
  assert.equal(calls.groupUpdate[0].props.title, CORTEX_GROUP_TITLE);
  assert.equal(calls.groupUpdate[0].props.color, CORTEX_GROUP_COLOR);
  assert.equal(calls.groupUpdate[0].props.collapsed, false);
});

test("ensureCortexTabGroup reuses the group of an already grouped tab", async () => {
  const tabs = [
    { id: 10, windowId: 1, groupId: 77 },
    { id: 12, windowId: 1, groupId: -1 },
  ];
  const { chrome, calls } = fakeChromeWithTabs(tabs);

  const groupId = await ensureCortexTabGroup(chrome, { id: 10, windowId: 1 }, [12]);

  assert.equal(groupId, 77);
  assert.equal(calls.group[0].groupId, 77);
  assert.equal(calls.groupQuery.length, 0);
});

test("ensureCortexTabGroup never breaks a command when tabs vanish or APIs are missing", async () => {
  const tabs = [{ id: 10, windowId: 1, groupId: -1 }];
  const { chrome } = fakeChromeWithTabs(tabs);

  // onglet ChatGPT fermé entre-temps : seul l'onglet console est groupé
  const groupId = await ensureCortexTabGroup(chrome, { id: 10, windowId: 1 }, [999]);
  assert.equal(groupId, 501);

  // API tabGroups absente : no-op silencieux
  const partial = { tabs: chrome.tabs };
  assert.equal(await ensureCortexTabGroup(partial, { id: 10, windowId: 1 }, []), null);

  // sans onglet console valide ni onglet cible : no-op
  assert.equal(await ensureCortexTabGroup(chrome, null, []), null);
});
