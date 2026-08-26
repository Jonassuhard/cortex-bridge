(() => {
  const MAX_CONVERSATIONS = 50;
  const MAX_TRANSFER_BYTES = 25 * 1024 * 1024;
  const TRANSFER_IDLE_TTL_MS = 60_000;
  const PRIVACY_MASK_TTL_MS = 15_000;
  const transfers = new Map();
  let activePrivacyMask = null;
  let privacyMaskSerial = 0;

  const privacyMaskTargets = () => {
    const selectors = [
      "nav",
      "aside",
      "[data-testid*='sidebar']",
      "[data-testid*='account']",
      "[data-testid*='avatar']",
      "[data-testid*='profile']",
      "[class*='sidebar']",
      "[role='menu']",
      "header button[aria-label*='profile' i]",
      "header button[aria-label*='profil' i]",
      "header button[aria-label*='account' i]",
      "header button[aria-label*='compte' i]",
    ];
    if (location.pathname === "/") {
      selectors.push(
        "main h1",
        "[role='main'] h1",
        "main ul",
        "[role='main'] ul",
      );
    }
    const viewportWidth = Number(window.innerWidth) || 0;
    const viewportHeight = Number(window.innerHeight) || 0;
    const candidates = Array.from(document.querySelectorAll(selectors.join(", ")))
      .filter((target) => {
        if (!(target instanceof Element)) return false;
        const style = getComputedStyle(target);
        if (style.display === "none" || style.visibility === "hidden") return false;
        const rect = target.getBoundingClientRect?.();
        return Boolean(
          rect
          && rect.width > 0
          && rect.height > 0
          && rect.right > 0
          && rect.bottom > 0
          && rect.left < viewportWidth
          && rect.top < viewportHeight
        );
      });
    return candidates.filter((target, index) => !candidates.some((parent, parentIndex) => (
      parentIndex < index && parent.contains?.(target)
    )));
  };

  const removePrivacyMask = (token, { force = false } = {}) => {
    const mask = activePrivacyMask;
    if (!mask || mask.token !== token) return false;
    if (!force && mask.references > 1) {
      mask.references -= 1;
      return true;
    }
    clearTimeout(mask.expiryTimer);
    mask.root.remove();
    activePrivacyMask = null;
    return true;
  };

  const refreshPrivacyMaskExpiry = (mask) => {
    clearTimeout(mask.expiryTimer);
    mask.expiryTimer = setTimeout(() => {
      removePrivacyMask(mask.token, { force: true });
    }, PRIVACY_MASK_TTL_MS);
  };

  const nextPaint = () => new Promise((resolve) => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(fallbackTimer);
      resolve();
    };
    const fallbackTimer = setTimeout(finish, 100);
    try {
      requestAnimationFrame(() => requestAnimationFrame(finish));
    } catch {
      finish();
    }
  });

  const beginPrivacyMask = async () => {
    if (activePrivacyMask?.root?.isConnected) {
      activePrivacyMask.references += 1;
      refreshPrivacyMaskExpiry(activePrivacyMask);
      return {
        confirmed: true,
        token: activePrivacyMask.token,
        masked_zones: activePrivacyMask.maskedZones,
      };
    }
    if (activePrivacyMask) {
      removePrivacyMask(activePrivacyMask.token, { force: true });
    }

    const targets = privacyMaskTargets();
    if (targets.length === 0) {
      throw Object.assign(
        new Error("No visible ChatGPT identity or navigation zone could be masked"),
        { code: "SCREENSHOT_PRIVACY_MASK_FAILED" },
      );
    }

    privacyMaskSerial += 1;
    const token = `mask-${privacyMaskSerial}`;
    const root = document.createElement("div");
    root.setAttribute("data-cortex-private-capture-mask", token);
    Object.assign(root.style, {
      position: "fixed",
      inset: "0",
      pointerEvents: "none",
      zIndex: "2147483647",
    });
    for (const target of targets) {
      const rect = target.getBoundingClientRect();
      const left = Math.max(0, rect.left);
      const top = Math.max(0, rect.top);
      const right = Math.min(Number(window.innerWidth) || rect.right, rect.right);
      const bottom = Math.min(Number(window.innerHeight) || rect.bottom, rect.bottom);
      if (right <= left || bottom <= top) continue;
      const shield = document.createElement("div");
      shield.setAttribute("aria-hidden", "true");
      shield.setAttribute("data-cortex-private-zone", "masked");
      Object.assign(shield.style, {
        position: "fixed",
        left: `${left}px`,
        top: `${top}px`,
        width: `${right - left}px`,
        height: `${bottom - top}px`,
        backgroundColor: "rgb(15, 23, 42)",
        backdropFilter: "blur(24px)",
        opacity: "1",
        pointerEvents: "none",
      });
      root.appendChild(shield);
    }
    if (root.children.length === 0) {
      throw Object.assign(
        new Error("ChatGPT private zones had no maskable viewport bounds"),
        { code: "SCREENSHOT_PRIVACY_MASK_FAILED" },
      );
    }

    const mask = {
      token,
      root,
      references: 1,
      maskedZones: root.children.length,
      expiryTimer: null,
    };
    document.documentElement.appendChild(root);
    activePrivacyMask = mask;
    refreshPrivacyMaskExpiry(mask);
    await nextPaint();
    const confirmed = root.isConnected && Array.from(root.children).every((shield) => (
      shield.isConnected
      && shield.style.backgroundColor === "rgb(15, 23, 42)"
      && shield.style.opacity === "1"
    ));
    if (!confirmed) {
      removePrivacyMask(token, { force: true });
      throw Object.assign(
        new Error("ChatGPT private-zone mask could not be visually confirmed"),
        { code: "SCREENSHOT_PRIVACY_MASK_FAILED" },
      );
    }
    return { confirmed: true, token, masked_zones: mask.maskedZones };
  };

  const discardTransfer = (transferId, expectedTransfer = null) => {
    const transfer = transfers.get(transferId);
    if (!transfer || (expectedTransfer && transfer !== expectedTransfer)) return false;
    transfers.delete(transferId);
    if (transfer.expiryTimer !== null) clearTimeout(transfer.expiryTimer);
    transfer.expiryTimer = null;
    transfer.chunks.length = 0;
    transfer.encodedCharacters = 0;
    return true;
  };

  const refreshTransferExpiry = (transferId, transfer) => {
    if (transfer.expiryTimer !== null) clearTimeout(transfer.expiryTimer);
    transfer.expiryTimer = setTimeout(() => {
      discardTransfer(transferId, transfer);
    }, TRANSFER_IDLE_TTL_MS);
  };

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

  const normalizeAttachmentText = (value) => String(value || "")
    .replace(/\s+/g, " ")
    .trim();

  const fileTileClass = (node) => normalizeAttachmentText(
    node?.getAttribute?.("class"),
  );

  const isFileTileLike = (node) => fileTileClass(node).includes("file-tile");

  const isFileTile = (node) => fileTileClass(node)
    .split(" ")
    .some((token) => token === "file-tile" || token === "group/file-tile");

  const fileTileName = (node) => {
    if (!isFileTileLike(node)) return null;
    if (!isFileTile(node)) return "";
    if (node?.getAttribute?.("role") !== "group") return "";
    return normalizeAttachmentText(node?.getAttribute?.("aria-label"));
  };

  const attachmentLabelMatches = (
    rawLabel,
    rawExpectedName,
    { exact = false } = {},
  ) => {
    const label = normalizeAttachmentText(rawLabel);
    const expectedName = normalizeAttachmentText(rawExpectedName);
    if (!expectedName) return true;
    const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (
      exact ? label === expectedName : new RegExp(
        `(?:^|\\s)${escape(expectedName)}(?:\\s|$)`,
      ).test(label)
    ) {
      return true;
    }
    const dot = expectedName.lastIndexOf(".");
    const stem = dot > 0 ? expectedName.slice(0, dot) : expectedName;
    const extension = dot > 0 ? expectedName.slice(dot) : "";
    // ChatGPT may disambiguate an already-known upload as name(1).ext or
    // name(YYYYMMDD-HHMMSS).ext. Accept only those closed forms.
    return new RegExp(
      `${exact ? "^" : "(?:^|\\s)"}${escape(stem)}\\((?:[0-9]+|[0-9]{8}-[0-9]{6})\\)${escape(extension)}${exact ? "$" : "(?:\\s|$)"}`,
    ).test(label);
  };

  const composerAttachmentCandidates = () => Array.from(document.querySelectorAll([
    "form [data-testid*='attachment']",
    "form [data-testid*='file-chip']",
    "form [data-testid*='file-thumbnail']",
    "form [class*='attachment']",
    "form [class*='file-chip']",
    "form [role='group'][class*='file-tile'][aria-label]",
    "form [data-filename]",
    "form [data-file-name]",
    "form [data-attachment-name]",
    "form button[aria-label*='file']",
    "form button[aria-label*='fichier']",
  ].join(", ")));

  const attachmentNodeLabel = (node) => {
    const explicitFileTileName = fileTileName(node);
    if (explicitFileTileName !== null) return explicitFileTileName;
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

  const findComposerAttachment = (expectedName) => composerAttachmentCandidates()
    .find((candidate) => attachmentLabelMatches(
      attachmentNodeLabel(candidate),
      expectedName,
      { exact: isFileTileLike(candidate) },
    )) || null;

  const composerHasExplicitAttachment = () => composerAttachmentCandidates()
    .some((candidate) => {
      const tileName = fileTileName(candidate);
      if (tileName !== null) return Boolean(tileName);
      return [
        candidate?.getAttribute?.("data-filename"),
        candidate?.getAttribute?.("data-file-name"),
        candidate?.getAttribute?.("data-attachment-name"),
      ].some((value) => normalizeAttachmentText(value));
    });

  const messageAttachmentScope = (node) => {
    const turn = node?.closest?.(
      "article[data-testid^='conversation-turn-'], [data-testid^='conversation-turn-']",
    );
    if (!turn) return node;
    const authoredMessages = Array.from(
      turn.querySelectorAll?.("[data-message-author-role]") || [],
    );
    return authoredMessages.length === 1 && authoredMessages[0] === node
      ? turn
      : node;
  };

  const messageAttachments = (node) => {
    const seen = new Set();
    const scope = messageAttachmentScope(node);
    return Array.from(scope.querySelectorAll([
      "[data-testid*='attachment']",
      "[data-testid*='file-chip']",
      "[data-testid*='file-thumbnail']",
      "[class*='attachment']",
      "[class*='file-chip']",
      "[class*='message-image'] img[alt]",
      "[role='group'][class*='file-tile'][aria-label]",
      "[data-filename]",
      "[data-file-name]",
      "[data-attachment-name]",
      "a[download]",
    ].join(", "))).map((candidate) => {
      const nestedName = candidate.querySelector?.([
        "[data-testid*='file-name']",
        "[data-testid*='filename']",
        "[data-filename]",
        "[data-file-name]",
      ].join(", "));
      const explicitFileTileName = fileTileName(candidate);
      const rawName = explicitFileTileName !== null
        ? explicitFileTileName
        : [
          candidate.getAttribute?.("download"),
          candidate.getAttribute?.("data-filename"),
          candidate.getAttribute?.("data-file-name"),
          candidate.getAttribute?.("data-attachment-name"),
          nestedName?.getAttribute?.("data-filename"),
          nestedName?.getAttribute?.("data-file-name"),
          nestedName?.innerText,
          nestedName?.textContent,
          String(candidate.innerText || "").split(/\r?\n/).find(Boolean),
          String(candidate.textContent || "").split(/\r?\n/).find(Boolean),
          candidate.getAttribute?.("title"),
          candidate.getAttribute?.("aria-label"),
          candidate.getAttribute?.("alt"),
        ].find((value) => String(value || "").trim());
      const name = String(rawName || "").replace(/\s+/g, " ").trim();
      const key = name.toLowerCase();
      if (!name || seen.has(key)) return null;
      seen.add(key);
      return { name };
    }).filter(Boolean);
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
    if (/rate limit|too many requests|limite de requêtes|usage limit|limite d'utilisation|limite d’utilisation|you've hit|vous avez atteint/.test(body)) return "rate_limit";
    return null;
  };

  const conversationId = () => location.pathname.match(/\/c\/([^/?#]+)/)?.[1] || null;

  const WORK_SURFACE_SUFFIX = /,\s*work\s*$/i;

  // ChatGPT now offers two surfaces behind the same /c/<id> URL scheme:
  // classic Chat and Work. They can only be told apart in the DOM: a sidebar
  // conversation link carries a ", Work" suffix in its accessible name, and
  // the home page exposes a Chat/Work radiogroup. Cortex Bridge is restricted
  // to classic Chat and must never compose on a Work surface.
  const surfaceMode = () => {
    const id = conversationId();
    if (id) {
      const selfLink = Array.from(
        document.querySelectorAll("nav a[href^='/c/'], aside a[href^='/c/']"),
      ).find((node) => (node.getAttribute("href") || "").includes(`/c/${id}`));
      if (!selfLink) return "unknown";
      const label = `${
        selfLink.getAttribute("aria-label") || ""
      } ${selfLink.getAttribute("title") || ""}`;
      return WORK_SURFACE_SUFFIX.test(label.trim()) ? "work" : "chat";
    }
    const radios = Array.from(
      document.querySelectorAll("[role=radiogroup] [role=radio]"),
    );
    if (radios.length > 0) {
      const checked = radios.find((node) => (
        node.getAttribute("aria-checked") === "true"
        || node.dataset?.state === "checked"
      ));
      const name = (checked?.innerText || checked?.textContent || "")
        .trim()
        .toLowerCase();
      if (name === "work") return "work";
      if (name === "chat") return "chat";
    }
    return "unknown";
  };

  const ensureClassicChatSurface = async () => {
    const mode = surfaceMode();
    if (mode !== "work") return mode;
    if (!conversationId()) {
      // A brand-new chat may simply sit on the Work home: switch back to Chat.
      const chatRadio = Array.from(
        document.querySelectorAll("[role=radiogroup] [role=radio]"),
      ).find((node) => (
        (node.innerText || node.textContent || "").trim().toLowerCase() === "chat"
      ));
      if (chatRadio) {
        chatRadio.click();
        const deadline = Date.now() + 5_000;
        while (Date.now() < deadline) {
          if (
            chatRadio.getAttribute("aria-checked") === "true"
            || chatRadio.dataset?.state === "checked"
          ) {
            return "chat";
          }
          await new Promise((resolve) => setTimeout(resolve, 100));
        }
      }
    }
    throw Object.assign(
      new Error(
        "Cortex Bridge only operates on classic ChatGPT chats, never on Work surfaces",
      ),
      { code: "WORK_SURFACE_REJECTED" },
    );
  };


  const messages = () => Array.from(
    document.querySelectorAll("[data-message-author-role]"),
  ).map((node, index) => {
    const role = node.getAttribute("data-message-author-role") || "assistant";
    const content = role === "assistant"
      ? queryFirst(["[data-message-content]", ".markdown", "[class*='markdown']"], node)
      : queryFirst([
        "[data-message-content]",
        "[data-testid='user-message']",
        ".user-message-bubble-color",
        "[class*='user-message-bubble']",
      ], node) || node;
    return {
      id: node.getAttribute("data-message-id") || node.id || `dom-${index}`,
      role,
      text: content?.innerText || content?.textContent || "",
      code_blocks: Array.from(node.querySelectorAll("pre code")).map((code) => ({
        lang: Array.from(code.classList).find((name) => name.startsWith("language-"))?.slice(9) || "",
        text: code.textContent || "",
      })),
      attachments: messageAttachments(node),
    };
  });

  const pageShellState = () => ({
      url: location.href,
      conversation_id: conversationId(),
      title: document.title.replace(/\s*[-–—]\s*ChatGPT\s*$/i, "").trim() || "ChatGPT",
      blocker: blocker(),
      surface: surfaceMode(),
      composer_present: Boolean(composer()),
      send_button_present: Boolean(sendButton()),
      stop_button_present: Boolean(stopButton()),
      streaming: Boolean(stopButton()),
  });

  const currentState = () => ({
    ...pageShellState(),
    messages: messages(),
  });

  const modelSwitchTrigger = () => queryFirst([
    "button[data-testid*='model-switcher']",
    "button[aria-label*='model']",
    "button[aria-label*='modèle']",
  ]);

  const operations = {
    async privacy_mask_begin() {
      return beginPrivacyMask();
    },
    privacy_mask_restore(payload) {
      const token = String(payload?.token || "");
      if (!token) {
        throw Object.assign(
          new Error("A private capture mask token is required"),
          { code: "SCREENSHOT_PRIVACY_RESTORE_FAILED" },
        );
      }
      if (!activePrivacyMask) {
        throw Object.assign(
          new Error("The private capture mask is no longer active in this document"),
          { code: "SCREENSHOT_PRIVACY_RESTORE_FAILED" },
        );
      }
      if (activePrivacyMask.token !== token || !removePrivacyMask(token)) {
        throw Object.assign(
          new Error("The private capture mask token does not match the active mask"),
          { code: "SCREENSHOT_PRIVACY_RESTORE_FAILED" },
        );
      }
      return { restored: true, token, removed: true };
    },
    probe() {
      const state = pageShellState();
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
      const state = pageShellState();
      const messageNodes = document.querySelectorAll("[data-message-author-role]");
      const first = messageNodes[0] || null;
      const last = messageNodes[messageNodes.length - 1] || null;
      return {
        url: state.url,
        conversation_id: state.conversation_id,
        title: state.title,
        message_count: messageNodes.length,
        first_id: first?.getAttribute("data-message-id") || first?.id || null,
        last_id: last?.getAttribute("data-message-id") || last?.id || null,
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
    async prepare_text(payload) {
      await ensureClassicChatSurface();
      const target = composer();
      if (!target) throw Object.assign(new Error("ChatGPT composer not found"), { code: "COMPOSER_MISSING" });
      const normalizeComposerText = (value) => String(value || "").replace(/\s+/g, " ").trim();
      const marker = normalizeComposerText(payload.text).slice(0, 80);
      target.focus();
      if (target instanceof HTMLTextAreaElement) {
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
        setter?.call(target, payload.text);
        target.dispatchEvent(new InputEvent("input", {
          bubbles: true,
          inputType: "insertText",
          data: payload.text,
        }));
      } else {
        const range = document.createRange();
        range.selectNodeContents(target);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
        document.execCommand("insertText", false, payload.text);
      }

      let inputConfirmed = false;
      let inputStableChecks = 0;
      for (let attempt = 0; attempt < 40; attempt += 1) {
        const current = composer();
        const currentText = normalizeComposerText(current?.innerText || current?.textContent);
        if (!marker || currentText.includes(marker)) {
          inputStableChecks += 1;
          if (inputStableChecks >= 6) {
            inputConfirmed = true;
            break;
          }
        } else inputStableChecks = 0;
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      if (!inputConfirmed) {
        throw Object.assign(
          new Error("ChatGPT composer did not retain the requested text"),
          { code: "COMPOSER_INPUT_FAILED" },
        );
      }

      let button = null;
      for (let attempt = 0; attempt < 50 && !button; attempt += 1) {
        const candidate = sendButton();
        if (candidate && !candidate.disabled && visible(candidate)) button = candidate;
        else await new Promise((resolve) => setTimeout(resolve, 100));
      }
      if (!button) {
        throw Object.assign(new Error("ChatGPT send button is unavailable"), { code: "SEND_REJECTED" });
      }
      // ChatGPT's ProseMirror editor commits its pending state on focus loss.
      // A form submission fired while the editor stays focused can therefore
      // be ignored on a brand-new chat even though the button looks enabled.
      button.focus({ preventScroll: true });
      // The focus transition may rerender the composer controls. Never submit
      // a detached React node: reacquire both elements after the commit.
      await Promise.resolve();
      const committedTarget = composer();
      const committedButton = sendButton();
      if (
        !committedTarget
        || !committedButton
        || committedButton.disabled
        || !visible(committedButton)
      ) {
        throw Object.assign(
          new Error("ChatGPT send control changed before submission"),
          { code: "SEND_REJECTED" },
        );
      }
      return {
        ok: true,
        user_message_ids: messages()
          .filter((message) => message.role === "user")
          .map((message) => message.id),
      };
    },
    press_stop() {
      const button = stopButton();
      if (button) button.click();
      return { stopped: Boolean(button) };
    },
    async attachment_begin(payload) {
      await ensureClassicChatSurface();
      if (
        !payload.transfer_id
        || !Number.isSafeInteger(payload.size)
        || payload.size < 0
        || payload.size > MAX_TRANSFER_BYTES
      ) {
        throw Object.assign(new Error("Attachment exceeds the 25 MiB bridge limit"), { code: "ATTACHMENT_TOO_LARGE" });
      }
      discardTransfer(payload.transfer_id);
      const target = composer();
      const form = target?.closest?.("form");
      const input = form?.querySelector?.("input[type=file]");
      const draft = normalizeAttachmentText(
        target instanceof HTMLTextAreaElement
          ? target.value
          : target?.innerText || target?.textContent,
      );
      if (
        !target
        || !form
        || !(input instanceof HTMLInputElement)
        || draft
        || composerHasExplicitAttachment()
      ) {
        throw Object.assign(
          new Error("ChatGPT composer is not clean and stable for an attachment"),
          { code: "PRE_DELIVERY_NOT_READY" },
        );
      }
      const transfer = {
        ...payload,
        chunks: [],
        encodedCharacters: 0,
        nextIndex: 0,
        expiryTimer: null,
        composer: target,
        form,
        input,
        url: location.href,
      };
      transfers.set(payload.transfer_id, transfer);
      refreshTransferExpiry(payload.transfer_id, transfer);
      return { accepted: true };
    },
    attachment_chunk(payload) {
      const transfer = transfers.get(payload.transfer_id);
      if (!transfer || typeof payload.data !== "string") {
        if (transfer) discardTransfer(payload.transfer_id, transfer);
        throw Object.assign(new Error("Unknown attachment transfer"), { code: "ATTACHMENT_TRANSFER_INVALID" });
      }
      const encodedLimit = 4 * Math.ceil(transfer.size / 3);
      const encodedCharacters = transfer.encodedCharacters + payload.data.length;
      if (
        !Number.isSafeInteger(payload.index)
        || payload.index !== transfer.nextIndex
        || encodedCharacters > encodedLimit
      ) {
        discardTransfer(payload.transfer_id, transfer);
        throw Object.assign(
          new Error("Attachment transfer exceeds its declared byte budget"),
          { code: "ATTACHMENT_TRANSFER_INVALID" },
        );
      }
      transfer.chunks.push(payload.data);
      transfer.encodedCharacters = encodedCharacters;
      transfer.nextIndex += 1;
      refreshTransferExpiry(payload.transfer_id, transfer);
      return { accepted: true, chunks: transfer.chunks.length };
    },
    attachment_commit(payload) {
      const transfer = transfers.get(payload.transfer_id);
      if (!transfer) {
        throw Object.assign(new Error("Unknown attachment transfer"), { code: "ATTACHMENT_TRANSFER_INVALID" });
      }
      const currentComposer = composer();
      const currentForm = currentComposer?.closest?.("form");
      const currentInput = currentForm?.querySelector?.("input[type=file]");
      if (
        currentComposer !== transfer.composer
        || currentForm !== transfer.form
        || currentInput !== transfer.input
        || transfer.url !== location.href
        || transfer.composer.isConnected === false
        || transfer.form.isConnected === false
        || transfer.input.isConnected === false
      ) {
        discardTransfer(payload.transfer_id, transfer);
        throw Object.assign(
          new Error("ChatGPT composer changed before the attachment was committed"),
          { code: "PRE_DELIVERY_NOT_READY" },
        );
      }
      let binary;
      try {
        binary = atob(transfer.chunks.join(""));
      } catch {
        discardTransfer(payload.transfer_id, transfer);
        throw Object.assign(
          new Error("Attachment transfer is not valid base64"),
          { code: "ATTACHMENT_TRANSFER_INVALID" },
        );
      }
      if (binary.length !== transfer.size || binary.length > MAX_TRANSFER_BYTES) {
        discardTransfer(payload.transfer_id, transfer);
        throw Object.assign(
          new Error("Attachment transfer does not match its declared size"),
          { code: "ATTACHMENT_TRANSFER_INVALID" },
        );
      }
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      const file = new File([bytes], transfer.name, { type: transfer.mime || "application/octet-stream" });
      const data = new DataTransfer();
      data.items.add(file);
      transfer.input.files = data.files;
      transfer.input.dispatchEvent(new Event("change", { bubbles: true }));
      discardTransfer(payload.transfer_id, transfer);
      return { attached: true, name: transfer.name };
    },
    async await_attachment(payload) {
      const expectedName = String(payload?.name || "").trim();
      const deadline = Date.now() + 60_000;
      let readyChecks = 0;
      while (Date.now() < deadline) {
        const chip = findComposerAttachment(expectedName);
        const progress = queryFirst([
          "form [role=progressbar]",
          "form [aria-busy=true]",
        ]);
        const button = sendButton();
        if (chip && !progress && button && !button.disabled && visible(button)) {
          readyChecks += 1;
          if (readyChecks >= 4) {
            return {
              ok: true,
              label: attachmentNodeLabel(chip) || expectedName,
            };
          }
        } else readyChecks = 0;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      return { ok: false, error: "Attachment did not become ready" };
    },
    async send_bare(payload) {
      await ensureClassicChatSurface();
      const expectedName = String(payload?.name || "").trim();
      if (!expectedName) {
        throw Object.assign(
          new Error("An expected attachment filename is required"),
          { code: "SEND_REJECTED" },
        );
      }
      let readyChecks = 0;
      for (let attempt = 0; attempt < 20; attempt += 1) {
        const chip = findComposerAttachment(expectedName);
        const progress = queryFirst([
          "form [role=progressbar]",
          "form [aria-busy=true]",
        ]);
        const button = sendButton();
        if (chip && !progress && button && !button.disabled && visible(button)) {
          readyChecks += 1;
          if (readyChecks >= 3) {
            return {
              ok: true,
              user_message_ids: messages()
                .filter((message) => message.role === "user")
                .map((message) => message.id),
            };
          }
        } else readyChecks = 0;
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      throw Object.assign(
        new Error("The expected attachment is not ready to send"),
        { code: "SEND_REJECTED" },
      );
    },
    list_models() {
      const trigger = modelSwitchTrigger();
      return {
        selected: trigger?.innerText?.trim() || null,
        models: [],
      };
    },
    async select_model(payload) {
      const label = String(payload.label || "").trim();
      if (!label) throw Object.assign(new Error("Model label is required"), { code: "MODEL_REQUIRED" });
      const option = Array.from(document.querySelectorAll("[role=menuitem], [role=option], button"))
        .find((node) => visible(node) && node.textContent?.trim() === label);
      if (!option) throw Object.assign(new Error(`ChatGPT model not found: ${label}`), { code: "MODEL_NOT_FOUND" });
      const normalize = (value) => String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
      const expected = normalize(label);
      const before = normalize(
        modelSwitchTrigger()?.innerText || modelSwitchTrigger()?.textContent,
      );
      option.click();
      // Radix re-renders the switcher after a selection: any node captured
      // before the click may be detached. Confirm only from a freshly
      // reacquired trigger whose label moved toward the requested model —
      // never from a stale node (historical model-switch confirmation bug).
      const matches = (current) => Boolean(current)
        && (current === expected || current.includes(expected) || expected.includes(current));
      const deadline = Date.now() + 5_000;
      while (Date.now() < deadline) {
        const trigger = modelSwitchTrigger();
        const current = normalize(trigger?.innerText || trigger?.textContent);
        if (matches(current) && (expected === before || current !== before)) {
          return { selected: label, confirmed: true };
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      throw Object.assign(
        new Error(`ChatGPT model switch could not be confirmed: ${label}`),
        { code: "MODEL_CONFIRM_FAILED" },
      );
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
