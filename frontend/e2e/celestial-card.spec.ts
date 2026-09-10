import { expect, test } from "./fixtures/app";

for (const width of [375, 1440]) {
  test(`Cortex awakening and task motion respect state and reduced motion at ${width}`, async ({ appPage }, testInfo) => {
    await appPage.setViewportSize({ width, height: 900 });
    await appPage.reload();
    const card = appPage.getByLabel("Carte projet Cortex");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-active", "true");
    await expect(card).toHaveAttribute("data-busy", "false");
    await expect(card.locator("[data-astro]")).toHaveCount(4);
    await expect(card.locator(".celestial-eyes")).toHaveCSS("animation-name", "cortex-awaken");
    const moon = card.locator("[data-astro='Luna'] .celestial-motion");
    await expect(moon).toHaveCSS("animation-play-state", "paused");
    const run = { id: "celestial-run", state: "SENDING_TO_CHATGPT", text: "Test céleste", conversation_url: "http://127.0.0.1:3420/c/release-checklist", created_at: new Date().toISOString() };
    await appPage.route("**/api/chat/send", route => route.fulfill({ status: 202, json: run }));
    await appPage.route("**/api/chat/runs/*/events", route => route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify({ seq: 1, type: "status", ts: new Date().toISOString(), payload: { state: run.state } })}\n\n` }));
    await appPage.route(/\/api\/chat\/runs\/[^/]+$/, route => route.fulfill({ json: run }));
    await appPage.getByRole("textbox", { name: "Message à envoyer" }).fill("Test céleste");
    await appPage.getByRole("button", { name: "Envoyer à ChatGPT", exact: true }).click();
    await expect(card).toHaveAttribute("data-busy", "true");
    await expect(moon).toHaveCSS("animation-play-state", "running");
    const before = await moon.evaluate(el => getComputedStyle(el).transform);
    await expect.poll(() => moon.evaluate(el => getComputedStyle(el).transform)).not.toBe(before);
    await card.scrollIntoViewIfNeeded();
    const box = await card.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    await appPage.screenshot({ path: testInfo.outputPath(`celestial-${width}.png`) });
    await appPage.emulateMedia({ reducedMotion: "reduce" });
    await expect(moon).toHaveCSS("animation-name", "none");
    await expect(card.locator(".celestial-eyes")).toHaveCSS("animation-name", "none");
  });
}
