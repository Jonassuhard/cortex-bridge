(() => {
  const MAX_CONVERSATIONS = 50;
  const MAX_TRANSFER_BYTES = 25 * 1024 * 1024;
  const transfers = new Map();

  const queryFirst = (selectors, root = document) => {
    for (const selector of selectors) {
      const found = root.querySelector(selector);
      if (found) return found;
    }
    return null;
  };

  const visible = (node) => {
    if (!(node instanceof Element)) return false;
    const style = getComputedStyle(node);
    return style.display !== "none" && style.visibility !== "hidden";
  };

  const composer = () => queryFirst([
    "#prompt-textarea",
    "textarea[data-testid=prompt-textarea]",
    "div[contenteditable=true][data-testid=prompt-textarea]",
    "form div[contenteditable=true]",
  ]);

  const sendButton = () => queryFirst([
    "button[data-testid=send-button]",
    "button[aria-label*='Send']",
    "button[aria-label*='Envoyer']",
  ]);

  const stopButton = () => queryFirst([
    "button[data-testid=stop-button]",
    "button[aria-label*='Stop']",
    "button[aria-label*='Arrêter']",
  ]);

  const blocker = () => {
    const path = location.pathname.toLowerCase();
    const body = (document.body?.innerText || "").slice(0, 12_000).toLowerCase();
    if (
      path.startsWith("/auth/")
      || queryFirst(["a[href*='/auth/login']", "button[data-testid=login-button]"])
      || (/log in|sign in|se connecter/.test(body) && !composer())
    ) return "login";
    if (/captcha|verify you are human|vérifiez que vous êtes humain|cloudflare/.test(body)) {
      return "captcha";
    }
    if (/rate limit|too many requests|limite de requêtes/.test(body)) return "rate_limit";
    return null;
  };

  const conversationId = () => location.pathname.match(/\/c\/([^/?#]+)/)?.[1] || null;

  const messages = () => Array.from(
    document.querySelectorAll("[data-message-author-role]"),
  ).map((node, index) => ({
    id: node.getAttribute("data-message-id") || node.id || `dom-${index}`,
    role: node.getAttribute("data-message-author-role") || "assistant",
    text: node.innerText || node.textContent || "",
    code_blocks: Array.from(node.querySelectorAll("pre code")).map((code) => ({
      lang: Array.from(code.classList).find((name) => name.startsWith("language-"))?.slice(9) || "",
      text: code.textContent || "",
    })),
  }));

  const currentState = () => {
    const items = messages();
    return {
      url: location.href,
      conversation_id: conversationId(),
      title: document.title.replace(/\s*[-–—]\s*ChatGPT\s*$/i, "").trim() || "ChatGPT",
      blocker: blocker(),
      composer_present: Boolean(composer()),
      send_button_present: Boolean(sendButton()),
      stop_button_present: Boolean(stopButton()),
      streaming: Boolean(stopButton()),
      messages: items,
    };
  };

  const operations = {
    probe() {
      const state = currentState();
      const failures = [];
      if (state.blocker) failures.push(state.blocker);
      if (!state.composer_present && !state.blocker) failures.push("composer-missing");
      return {
        ok: failures.length === 0,
        url: state.url,
        title: state.title,
        blocker: state.blocker,
        composer_present: state.composer_present,
        send_button_present: state.send_button_present,
        failures,
        warnings: [],
      };
    },
    get_state() {
      return currentState();
    },
    get_light_state() {
      const state = currentState();
      return {
        url: state.url,
        conversation_id: state.conversation_id,
        title: state.title,
        message_count: state.messages.length,
        first_id: state.messages[0]?.id || null,
        last_id: state.messages.at(-1)?.id || null,
        streaming: state.streaming,
        composer_present: state.composer_present,
      };
    },
    spa_navigate(payload) {
      const requested = new URL(payload.url, location.origin);
      if (requested.origin !== "https://chatgpt.com") return { handled: false };
      const link = Array.from(document.querySelectorAll("a[href]"))
        .find((node) => new URL(node.href, location.origin).pathname === requested.pathname);
      if (!link) return { handled: false };
      link.click();
      return { handled: true };
    },
    async list_conversations() {
      const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
      const sidebarSelector = "nav a[href^='/c/'], aside a[href^='/c/']";
      const seen = new Map();
      const collect = () => {
        for (const link of document.querySelectorAll(sidebarSelector)) {
          const href = link.getAttribute("href") || "";
          const identity = href.match(/\/c\/([^/?#]+)/)?.[1];
          if (!identity || seen.has(identity)) continue;
          const row = link.closest("li, [data-testid*='conversation'], [class*='group']")
            || link.parentElement
            || link;
          const lines = (link.innerText || link.textContent || "")
            .split(/\n+/)
            .map(normalize)
            .filter(Boolean);
          const title = normalize(link.getAttribute("title")) || lines[0] || "Conversation";
          const timeNode = row.querySelector?.("time");
          const timestamp = normalize(timeNode?.getAttribute("datetime") || timeNode?.textContent);
          const rowLabels = `${normalize(row.getAttribute?.("aria-label"))} ${normalize(row.textContent)}`;
          const unreadNode = Array.from(row.querySelectorAll?.("[aria-label], [data-testid], span") || [])
            .find((node) => (
              /^\d+$/.test(normalize(node.textContent))
              && /unread|non lu|new|nouveau/i.test(
                `${node.getAttribute("aria-label") || ""} ${node.getAttribute("data-testid") || ""}`,
              )
            ));
          const parentList = link.closest("ul");
          const projectRow = parentList && parentList.closest('li');
          const projectLink = projectRow?.querySelector?.("a[href*='/project'], a[href^='/g/']");
          const projectTitleNode = projectRow?.querySelector?.(":scope > button, :scope > a, :scope > div");
          const projectTitle = projectRow ? normalize(projectTitleNode?.textContent) || null : null;
          const projectHref = projectLink?.getAttribute("href") || "";
          const projectId = projectHref.match(/\/(?:g|project)\/([^/?#]+)/)?.[1] || null;
          seen.set(identity, {
            url: `https://chatgpt.com${href}`,
            identity,
            title,
            preview: lines.find((line, index) => index > 0 && line !== timestamp) || title,
            timestamp,
            unread: unreadNode ? Number(normalize(unreadNode.textContent)) : 0,
            pinned: /pinned|épingl|epingle/i.test(rowLabels),
            project: Boolean(projectRow),
            project_id: projectId,
            project_title: projectTitle,
            archived: false,
            message_count: null,
          });
        }
      };
      const first = document.querySelector(sidebarSelector);
      const container = first?.closest("[class*='overflow'], nav, aside") || null;
      collect();
      let unchanged = 0;
      let previousSize = seen.size;
      for (let pass = 0; pass < 40 && container && seen.size < MAX_CONVERSATIONS; pass += 1) {
        const previousTop = container.scrollTop;
        container.scrollTop = Math.min(
          container.scrollHeight,
          container.scrollTop + Math.max(320, container.clientHeight * 0.8),
        );
        await new Promise((resolve) => setTimeout(resolve, 160));
        collect();
        if (seen.size === previousSize && container.scrollTop === previousTop) unchanged += 1;
        else unchanged = 0;
        previousSize = seen.size;
        if (unchanged >= 3 || container.scrollTop + container.clientHeight >= container.scrollHeight - 4) break;
      }
      if (container) container.scrollTop = 0;
      return Array.from(seen.values()).slice(0, MAX_CONVERSATIONS);
    },
    async send_text(payload) {
      const target = composer();
      if (!target) throw Object.assign(new Error("ChatGPT composer not found"), { code: "COMPOSER_MISSING" });
      const userIdsBefore = new Set(
        messages().filter((message) => message.role === "user").map((message) => message.id),
      );
      const marker = String(payload.text || "").trim().slice(0, 80);
      target.focus();
      if (target instanceof HTMLTextAreaElement) {
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
        setter?.call(target, payload.text);
      } else {
        document.execCommand("selectAll", false);
        document.execCommand("insertText", false, payload.text);
      }
      target.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: payload.text }));

      let button = null;
      for (let attempt = 0; attempt < 50 && !button; attempt += 1) {
        const candidate = sendButton();
        if (candidate && !candidate.disabled && visible(candidate)) button = candidate;
        else await new Promise((resolve) => setTimeout(resolve, 100));
      }
      if (!button) {
        throw Object.assign(new Error("ChatGPT send button is unavailable"), { code: "SEND_REJECTED" });
      }
      button.click();

      for (let attempt = 0; attempt < 50; attempt += 1) {
        const current = composer();
        const value = current instanceof HTMLTextAreaElement
          ? current.value
          : current?.innerText || current?.textContent || "";
        if (!current || !value.trim()) return { ok: true };
        const visibleUserMessage = messages().find((message) => (
          message.role === "user"
          && !userIdsBefore.has(message.id)
          && (!marker || message.text.includes(marker))
        ));
        if (visibleUserMessage) return { ok: true };
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      throw Object.assign(
        new Error("ChatGPT composer did not clear after send"),
        { code: "DELIVERY_UNCERTAIN" },
      );
    },
    press_stop() {
      const button = stopButton();
      if (button) button.click();
      return { stopped: Boolean(button) };
    },
    attachment_begin(payload) {
      if (!payload.transfer_id || payload.size < 0 || payload.size > MAX_TRANSFER_BYTES) {
        throw Object.assign(new Error("Attachment exceeds the 25 MiB bridge limit"), { code: "ATTACHMENT_TOO_LARGE" });
      }
      transfers.set(payload.transfer_id, { ...payload, chunks: [] });
      return { accepted: true };
    },
    attachment_chunk(payload) {
      const transfer = transfers.get(payload.transfer_id);
      if (!transfer || typeof payload.data !== "string") {
        throw Object.assign(new Error("Unknown attachment transfer"), { code: "ATTACHMENT_TRANSFER_INVALID" });
      }
      transfer.chunks.push(payload.data);
      return { accepted: true, chunks: transfer.chunks.length };
    },
    attachment_commit(payload) {
      const transfer = transfers.get(payload.transfer_id);
      if (!transfer) {
        throw Object.assign(new Error("Unknown attachment transfer"), { code: "ATTACHMENT_TRANSFER_INVALID" });
      }
      const binary = atob(transfer.chunks.join(""));
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      const file = new File([bytes], transfer.name, { type: transfer.mime || "application/octet-stream" });
      const input = document.querySelector("form input[type=file]");
      if (!(input instanceof HTMLInputElement)) {
        transfers.delete(payload.transfer_id);
        throw Object.assign(new Error("ChatGPT file input not found"), { code: "ATTACHMENT_INPUT_MISSING" });
      }
      const data = new DataTransfer();
      data.items.add(file);
      input.files = data.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      transfers.delete(payload.transfer_id);
      return { attached: true, name: transfer.name };
    },
    async await_attachment() {
      const deadline = Date.now() + 60_000;
      while (Date.now() < deadline) {
        const chip = queryFirst([
          "[data-testid*='attachment']",
          "[data-testid*='file']",
          "form [class*='attachment']",
        ]);
        const progress = queryFirst(["[role=progressbar]", "[aria-busy=true]"]);
        if (chip && !progress) return { ok: true };
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      return { ok: false, error: "Attachment did not become ready" };
    },
    send_bare() {
      const button = sendButton();
      if (!button || button.disabled) return { ok: false, error: "Send button unavailable" };
      button.click();
      return { ok: true };
    },
    list_models() {
      const trigger = queryFirst([
        "button[data-testid*='model-switcher']",
        "button[aria-label*='model']",
        "button[aria-label*='modèle']",
      ]);
      return {
        selected: trigger?.innerText?.trim() || null,
        models: [],
      };
    },
    select_model(payload) {
      const label = String(payload.label || "").trim();
      if (!label) throw Object.assign(new Error("Model label is required"), { code: "MODEL_REQUIRED" });
      const option = Array.from(document.querySelectorAll("[role=menuitem], [role=option], button"))
        .find((node) => visible(node) && node.textContent?.trim() === label);
      if (!option) throw Object.assign(new Error(`ChatGPT model not found: ${label}`), { code: "MODEL_NOT_FOUND" });
      option.click();
      return { selected: label };
    },
  };

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.source !== "cortex-bridge-extension" || !(message.action in operations)) {
      return false;
    }
    Promise.resolve()
      .then(() => operations[message.action](message.payload || {}))
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({
        ok: false,
        error: {
          code: error?.code || "CHATGPT_COMMAND_FAILED",
          message: error instanceof Error ? error.message : "ChatGPT command failed",
        },
      }));
    return true;
  });
})();
