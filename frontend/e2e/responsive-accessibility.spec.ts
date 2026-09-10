import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures/app";

for (const viewport of [{ width: 375, height: 812 }, { width: 768, height: 1024 }, { width: 1440, height: 900 }]) {
  test(`@a11y responsive ${viewport.width}px`, async ({ appPage }) => {
    await appPage.setViewportSize(viewport);
    await appPage.reload();
    await expect(appPage.getByLabel("Statuts ChatGPT et exécuteur")).toBeVisible();
    const chatBox = await appPage.locator(".chat-scroll-viewport").boundingBox();
    const composerBox = await appPage.locator(".composer-shell").boundingBox();
    expect(chatBox!.y + chatBox!.height).toBeLessThanOrEqual(composerBox!.y + 1);
    for (const name of ["Envoyer à ChatGPT", "Exécuter sur ce Mac…"]) {
      const box = await appPage.getByRole("button", { name, exact: true }).boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect((await new AxeBuilder({ page: appPage }).analyze()).violations).toEqual([]);
    if (viewport.width === 375) {
      await appPage.getByRole("button", { name: "Déplier" }).evaluate((button: HTMLButtonElement) => button.click());
      await appPage.getByRole("button", { name: /Paramètres/ }).evaluate((button: HTMLButtonElement) => button.click());
      await expect(appPage.getByRole("button", { name: "Info", exact: true })).toBeAttached();
      expect((await new AxeBuilder({ page: appPage }).analyze()).violations).toEqual([]);
    }
  });
}

test("respects reduced motion", async ({ appPage }) => {
  await appPage.emulateMedia({ reducedMotion: "reduce" });
  await appPage.reload();
  const animation = await appPage.locator(".app-signal-sweep").evaluate((element) => getComputedStyle(element).animationName);
  expect(animation).toBe("none");
});

test("onboarding sections never overlap at mobile width", async ({ appPage }) => {
  await appPage.emulateMedia({ reducedMotion: "reduce" });
  await appPage.setViewportSize({ width: 375, height: 812 });
  await appPage.route("**/api/onboarding", (route) => route.fulfill({ json: {
    completed: false, ready: false, checks: [{ id: "workspace", label: "Projet", state: "missing", detail: "Choisir un projet", hint: "Paramètres" }],
  } }));
  await appPage.reload();
  await expect(appPage.getByRole("dialog", { name: "Bienvenue dans Cortex Bridge" })).toBeVisible();
  const steps = await appPage.locator(".onboarding-steps").boundingBox();
  const checks = await appPage.locator(".onboarding-checks").boundingBox();
  expect(checks!.y).toBeGreaterThanOrEqual(steps!.y + steps!.height);
});
