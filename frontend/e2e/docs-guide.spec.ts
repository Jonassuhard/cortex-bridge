import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/app";

const enabled = process.env.CORTEX_DOCS_GUIDE === "1";
const outputRoot = fileURLToPath(new URL("../../docs/screenshots/v0.5.0/", import.meta.url));
const allViewports = [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
] as const;
const requestedWidth = Number(process.env.CORTEX_DOCS_VIEWPORT || 0);
const viewports = requestedWidth ? allViewports.filter(({ width }) => width === requestedWidth) : allViewports;

async function capture(page: Page, width: number, name: string) {
  const directory = `${outputRoot}/${width}`;
  await mkdir(directory, { recursive: true });
  await page.locator("nextjs-portal").evaluateAll((portals) => {
    for (const portal of portals) (portal as HTMLElement).style.display = "none";
  });
  await page.screenshot({
    path: `${directory}/${name}.png`,
    fullPage: true,
    animations: "disabled",
    caret: "hide",
  });
}

async function expandNavigation(page: Page) {
  const expand = page.getByRole("button", { name: "Déplier" });
  if (await expand.count()) await expand.evaluate((button: HTMLButtonElement) => button.click());
}

test("generate the synthetic v0.5 visual guide", async ({ appPage }) => {
  test.skip(!enabled, "Set CORTEX_DOCS_GUIDE=1 to regenerate committed guide media.");
  test.setTimeout(420_000);

  let showOnboarding = true;
  let holdResearch = false;
  await appPage.route("**/api/conversations/snapshot?*", async (route) => {
    if (holdResearch && decodeURIComponent(route.request().url()).includes("/c/research")) {
      await new Promise((resolve) => setTimeout(resolve, 11_000));
      await route.abort("timedout").catch(() => undefined);
      return;
    }
    await route.fallback();
  });

  await appPage.route("**/api/onboarding", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(showOnboarding ? {
        completed: false,
        ready: true,
        checks: [
          { id: "profile", label: "Profil de démonstration", state: "ok", detail: "Session synthétique prête", hint: "" },
          { id: "workspace", label: "Espace synthétique", state: "ok", detail: "Accès local limité", hint: "" },
          { id: "executor", label: "Exécuteur déterministe", state: "ok", detail: "Lecture seule par défaut", hint: "" },
        ],
      } : { completed: true, ready: true, checks: [] }),
    });
  });
  await appPage.route("**/api/settings", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        language: "fr", theme: "dark", planner_model: "ChatGPT — démonstration", primary_executor: "deterministic",
        fallback_executor: "deterministic", approval_policy: "workspace-write-with-approvals", access_profile: "workspace",
        default_workspace: "Espace synthétique", max_iterations: 10, max_duration_minutes: 10, ollama_context: 8192,
        auto_continue: false, browser_research: false, network_access: false, never_delete_files: true,
        persist_conversation_history: false, response_stability_seconds: 2, chat_timeout_seconds: 10,
        browser_transport: "playwright", browser_profile_root: "Profil synthétique",
      }),
    });
  });
  await appPage.route("**/api/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ollama_up: false, ollama_status: "unavailable", endpoint: "local", storage_path: "Espace synthétique",
        volume_mounted: true, storage_status: "OK", primary: { name: "deterministic", state: "ready" },
        executor_available: true, executor_kind: "deterministic", executor_model_used: null,
        runtime_mode: "fixture", release_eligible: false,
      }),
    });
  });
  await appPage.route("**/api/transport/stop-everything", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  const reset = async () => {
    await appPage.goto("/");
    await expect(appPage.getByRole("heading", { name: "Release checklist" })).toBeVisible();
  };

  for (const viewport of viewports) {
    await appPage.setViewportSize(viewport);
    await appPage.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" });

    showOnboarding = true;
    await appPage.reload();
    await expect(appPage.getByRole("dialog", { name: "Bienvenue dans Cortex Bridge" })).toBeVisible();
    await capture(appPage, viewport.width, "01-onboarding");
    await appPage.getByRole("button", { name: "Fermer l'assistant" }).click();
    showOnboarding = false;

    await reset();
    await expandNavigation(appPage);
    await expect(appPage.getByRole("heading", { name: "Épinglées" })).toBeVisible();
    await expect(appPage.getByRole("heading", { name: "Atlas" })).toBeVisible();
    await expect(appPage.getByRole("heading", { name: "Récentes" })).toBeVisible();
    await capture(appPage, viewport.width, "02-navigation");

    await reset();
    const composer = appPage.getByRole("textbox", { name: "Message à envoyer" });
    await composer.fill("Résumer les preuves synthétiques.");
    await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();
    await expect(appPage.getByText(/En attente locale|Envoi à ChatGPT/)).toBeVisible();
    await capture(appPage, viewport.width, "03-cycle-envoi");

    await reset();
    await composer.fill("Inspecter les fichiers de démonstration.");
    await appPage.getByRole("button", { name: "Exécuter…" }).click();
    await expect(appPage.getByRole("dialog", { name: "Vérifier l’exécution locale" })).toBeVisible();
    await capture(appPage, viewport.width, "04-preflight");
    await appPage.getByRole("button", { name: "Démarrer en lecture seule" }).click();
    await expect(appPage.getByText("Cortex Bridge").last()).toBeVisible();
    await capture(appPage, viewport.width, "05-execution");

    await reset();
    await composer.fill("Message synthétique A");
    await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();
    await appPage.getByRole("button", { name: /Local site prototype/ }).evaluate((button: HTMLButtonElement) => button.click());
    await composer.fill("Message synthétique B");
    await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();
    await expandNavigation(appPage);
    await capture(appPage, viewport.width, "06-deux-conversations");

    await reset();
    await appPage.locator('input[type="file"]').setInputFiles({
      name: "preuve-synthetique.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("preuve synthétique"),
    });
    await expect(appPage.getByText("preuve-synthetique.txt")).toBeVisible();
    await capture(appPage, viewport.width, "07-piece-jointe");

    await reset();
    holdResearch = true;
    await appPage.getByRole("button", { name: /Research/ }).evaluate((button: HTMLButtonElement) => button.click());
    await expect(appPage.getByRole("button", { name: "Recharger la conversation" })).toBeVisible({ timeout: 12_000 });
    await capture(appPage, viewport.width, "08-timeout");
    holdResearch = false;
    await appPage.getByRole("button", { name: "Recharger la conversation" }).click();
    await expect(appPage.locator(".message-assistant")).toBeVisible();
    await capture(appPage, viewport.width, "09-rechargement");

    await reset();
    await expandNavigation(appPage);
    await appPage.locator(".settings-entry").evaluate((button: HTMLButtonElement) => button.click());
    await expect(appPage.getByRole("dialog", { name: "Paramètres Cortex Bridge" })).toBeVisible();
    await appPage.locator(".settings-tabs button").nth(7).evaluate((button: HTMLButtonElement) => button.click());
    await expect(appPage.locator(".bridge-diagram")).toBeVisible();
    await capture(appPage, viewport.width, "10-info-diagramme");

    await reset();
    await appPage.getByRole("button", { name: /Détails du bridge/ }).click();
    await appPage.getByRole("button", { name: "Stop everything" }).evaluate((button: HTMLButtonElement) => button.click());
    await expect(appPage.getByText("STOP EVERYTHING actif", { exact: true })).toBeVisible();
    await capture(appPage, viewport.width, "11-arret-diagnostic");
  }
});
