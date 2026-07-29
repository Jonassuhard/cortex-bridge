import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures/app";

for (const viewport of [{ width: 375, height: 812 }, { width: 768, height: 1024 }, { width: 1440, height: 900 }]) {
  test(`@a11y responsive ${viewport.width}px`, async ({ appPage }) => {
    await appPage.setViewportSize(viewport);
    await appPage.reload();
    await expect(appPage.getByLabel("Statuts ChatGPT et exécuteur")).toBeVisible();
    expect((await new AxeBuilder({ page: appPage }).analyze()).violations).toEqual([]);
    if (viewport.width === 375) {
      await appPage.getByRole("button", { name: "Déplier" }).evaluate((button: HTMLButtonElement) => button.click());
      await appPage.locator(".settings-entry").evaluate((button: HTMLButtonElement) => button.click());
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
