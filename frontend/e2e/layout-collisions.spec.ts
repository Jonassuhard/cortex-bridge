import { expect, test } from "./fixtures/app";
import type { Page } from "@playwright/test";

async function settleLayout(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(document.getAnimations().filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime)).map((animation) => animation.finished.catch(() => undefined)));
  });
}

// Removing shrink protection or reserving too little room must fail this test.
async function collisions(page: Page, selectors: string[]) {
  return page.evaluate((groups) => {
    const failures: string[] = [];
    const visible = (el: Element) => {
      const box = el.getBoundingClientRect();
      return box.width > 0 && box.height > 0 && box.right > 0 && box.left < innerWidth && getComputedStyle(el).visibility !== "hidden";
    };
    for (const selector of groups) for (const parent of document.querySelectorAll(selector)) {
      if (!visible(parent)) continue;
      const bounds = parent.getBoundingClientRect();
      const children = [...parent.children].filter(visible);
      for (const [i, child] of children.entries()) {
        const a = child.getBoundingClientRect();
        if (a.left < bounds.left - 1 || a.right > bounds.right + 1) failures.push(`${selector}: ${child.tagName} outside parent`);
        for (const other of children.slice(i + 1)) {
          const b = other.getBoundingClientRect();
          if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) failures.push(`${selector}: ${child.tagName} overlaps ${other.tagName}`);
        }
      }
    }
    return failures;
  }, selectors);
}

async function clippedLabels(page: Page, selector: string) {
  return page.locator(selector).evaluateAll((elements) => elements.filter((el) => {
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0 && box.right > 0 && box.left < innerWidth && el.scrollWidth > el.clientWidth + 1;
  }).map((el) => el.textContent));
}

for (const width of [375, 768, 1024, 1440]) {
  test(`text and icons have reserved space at ${width}px`, async ({ appPage }, testInfo) => {
    await appPage.setViewportSize({ width, height: 1000 });
    await appPage.reload();
    await expect(appPage.getByRole("heading", { name: "Release checklist" })).toBeVisible();
    await settleLayout(appPage);
    const groups = [".conversation-toolbar", ".toolbar-left", ".conversation-title-block > div", ".status-rail", ".status-pill", ".composer-right-actions", ".composer-right-actions > button"];
    expect(await collisions(appPage, groups)).toEqual([]);
    expect(await clippedLabels(appPage, ".conversation-title-block h1, .conversation-title-block p")).toEqual([]);
    await appPage.getByRole("button", { name: /Afficher les détails techniques/ }).click();
    await settleLayout(appPage);
    expect(await collisions(appPage, [...groups, ".pipeline-head", ".pipeline-component"])).toEqual([]);
    expect(await clippedLabels(appPage, ".conversation-title-block h1, .conversation-title-block p")).toEqual([]);
    await appPage.screenshot({ path: testInfo.outputPath(`layout-inspector-${width}.png`), animations: "disabled" });
    // Reload closes overlays and restores the viewport's default navigation state.
    await appPage.reload();
    if (width === 375) await appPage.getByRole("button", { name: "Afficher les conversations", exact: true }).click();
    await expect(appPage.locator(".sidebar-brand-row")).toBeVisible();
    await settleLayout(appPage);
    expect((await appPage.locator(".sidebar-brand-row").boundingBox())!.x).toBeGreaterThanOrEqual(0);
    expect(await collisions(appPage, [".sidebar-brand-row", ".sidebar-brand-actions", ".sidebar-action", ".settings-entry", ".history-entry", ".conversation-title-line"])).toEqual([]);
    expect(await clippedLabels(appPage, ".settings-entry-copy small, .history-entry-copy small")).toEqual([]);
    const icons = appPage.locator(".sidebar-brand-actions button svg");
    for (const icon of await icons.all()) expect((await icon.boundingBox())!.width).toBeGreaterThanOrEqual(16);
    await appPage.screenshot({ path: testInfo.outputPath(`layout-navigation-${width}.png`), animations: "disabled" });
  });
}
