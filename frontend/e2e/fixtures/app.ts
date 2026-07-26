import { expect, test as base, type Page } from "@playwright/test";

const localOrigin = "http://127.0.0.1:3420";
const localApiOrigin = "http://127.0.0.1:8420";
const allowedOrigins = new Set([localOrigin, localApiOrigin]);
const fixedTime = "2026-07-26T08:00:00.000Z";

export const appFixtureData = {
  account: { name: "Demo User" },
  project: { id: "atlas", title: "Atlas" },
  workspace: "/tmp/cortex-demo-workspace",
  conversations: [
    {
      identity: "release-checklist",
      url: `${localOrigin}/c/release-checklist`,
      title: "Release checklist",
      preview: "Release checklist",
      timestamp: fixedTime,
      pinned: true,
      project: false,
      project_id: null,
      project_title: null,
      archived: false,
      unread: 0,
      message_count: 2,
      status: "idle",
      sync_state: "live",
      sync_error: null,
    },
    {
      identity: "local-site-prototype",
      url: `${localOrigin}/c/local-site-prototype`,
      title: "Local site prototype",
      preview: "Local site prototype",
      timestamp: fixedTime,
      pinned: false,
      project: true,
      project_id: "atlas",
      project_title: "Atlas",
      archived: false,
      unread: 0,
      message_count: 2,
      status: "idle",
      sync_state: "live",
      sync_error: null,
    },
    {
      identity: "research",
      url: `${localOrigin}/c/research`,
      title: "Research",
      preview: "Research",
      timestamp: fixedTime,
      pinned: false,
      project: false,
      project_id: null,
      project_title: null,
      archived: false,
      unread: 0,
      message_count: 2,
      status: "idle",
      sync_state: "live",
      sync_error: null,
    },
  ],
} as const;

function conversationSnapshot(conversationUrl: string) {
  const conversation = appFixtureData.conversations.find(({ url }) => url === conversationUrl)
    ?? appFixtureData.conversations[0];

  return {
    url: conversation.url,
    conversation_id: conversation.identity,
    title: conversation.title,
    blocker: null,
    composer_present: true,
    send_button_present: true,
    stop_button_present: false,
    streaming: false,
    model_label: null,
    messages: [
      {
        id: `${conversation.identity}-user`,
        role: "user",
        text: conversation.title,
        created_at: fixedTime,
        delivery: "received",
      },
      {
        id: `${conversation.identity}-assistant`,
        role: "assistant",
        text: conversation.title,
        created_at: fixedTime,
        delivery: "received",
      },
    ],
  };
}

function apiResponse(pathname: string, searchParams: URLSearchParams, method: string): unknown {
  if (method === "GET" && pathname === "/api/account") return appFixtureData.account;
  if (method === "GET" && pathname === "/api/conversations") return appFixtureData.conversations;
  if (method === "GET" && pathname === "/api/conversations/snapshot") {
    if (searchParams.get("light") === "1") {
      return { message_count: 2, last_id: "fixture-assistant", streaming: false };
    }
    return conversationSnapshot(searchParams.get("url") ?? appFixtureData.conversations[0].url);
  }
  if (method === "GET" && pathname === "/api/status") {
    return {
      ollama_up: false,
      ollama_status: "unavailable",
      endpoint: `${localOrigin}/ollama`,
      storage_path: appFixtureData.workspace,
      volume_mounted: true,
      storage_status: "OK",
      primary: { name: "deterministic", state: "ready" },
      executor_available: true,
      executor_kind: "deterministic",
      executor_model_used: null,
      runtime_mode: "fixture",
      release_eligible: false,
    };
  }
  if (method === "GET" && pathname === "/api/transport/status") {
    return { experimental_warning: "", opt_in_accepted: true, global_stop: false };
  }
  if (method === "GET" && pathname === "/api/transport/capabilities") {
    return { upload_file: true, take_screenshot: true };
  }
  if (method === "GET" && pathname === "/api/pipeline/status") {
    return {
      overall: "idle",
      updated_at: fixedTime,
      active_mission_id: null,
      active_mission_state: null,
      queue_pending: 0,
      runtime_execution: {
        task_id: null,
        executor_kind: "deterministic",
        executor_model_used: null,
        runtime_mode: "fixture",
        release_eligible: false,
        state: "idle",
        active: false,
        observed_at: fixedTime,
      },
      latency: { transport_ms: 10, local_model_ms: null, total_iteration_ms: null },
      components: [],
      events: [],
    };
  }
  if (method === "GET" && pathname === "/api/missions") return [];
  if (method === "GET" && pathname === "/api/models/ollama") return { models: [] };
  if (method === "GET" && pathname === "/api/models/chatgpt") return { models: [] };
  if (method === "GET" && pathname === "/api/settings") {
    return {
      language: "fr",
      theme: "dark",
      planner_model: "unavailable",
      primary_executor: "deterministic",
      fallback_executor: "deterministic",
      approval_policy: "workspace-write-with-approvals",
      access_profile: "workspace",
      default_workspace: appFixtureData.workspace,
      max_iterations: 10,
      max_duration_minutes: 10,
      ollama_context: 8192,
      auto_continue: false,
      browser_research: false,
      network_access: false,
      never_delete_files: true,
      persist_conversation_history: false,
      response_stability_seconds: 2,
      chat_timeout_seconds: 10,
      browser_transport: "playwright",
      browser_profile_root: appFixtureData.workspace,
    };
  }
  if (method === "GET" && pathname === "/api/onboarding") {
    return { completed: true, ready: true, checks: [] };
  }

  return { detail: `Unhandled local fixture route: ${method} ${pathname}` };
}

export async function installAppFixtureRoutes(page: Page): Promise<void> {
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!allowedOrigins.has(url.origin)) {
      await route.abort("blockedbyclient");
      return;
    }
    if (!url.pathname.startsWith("/api/")) {
      await route.continue();
      return;
    }

    const body = apiResponse(url.pathname, url.searchParams, request.method());
    const unhandled = typeof body === "object" && body !== null && "detail" in body;
    await route.fulfill({
      status: unhandled ? 404 : 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export const test = base.extend<{ appPage: Page }>({
  appPage: async ({ page }, provide) => {
    await installAppFixtureRoutes(page);
    await page.goto("/");
    await provide(page);
  },
});

export { expect };
