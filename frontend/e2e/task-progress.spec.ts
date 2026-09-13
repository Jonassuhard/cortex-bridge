import { expect, test } from "./fixtures/app";

for (const width of [375, 1440]) {
  test(`message progress is visible and honest at ${width}px`, async ({ appPage }, testInfo) => {
    await appPage.setViewportSize({ width, height: 900 });
    const run = {
      id: "fixture-run", state: "SENDING_TO_CHATGPT", text: "Message synthétique",
      conversation_url: "http://127.0.0.1:3420/c/release-checklist", created_at: new Date().toISOString(),
    };
    await appPage.route("**/api/chat/send", (route) => route.fulfill({ status: 202, json: run }));
    await appPage.route("**/api/chat/runs/*/events", (route) => route.fulfill({
      contentType: "text/event-stream", body: `data: ${JSON.stringify({ seq: 1, type: "status", ts: new Date().toISOString(), payload: { state: "SENDING_TO_CHATGPT" } })}\n\n`,
    }));
    await appPage.route(/\/api\/chat\/runs\/[^/]+$/, (route) => route.fulfill({ json: run }));
    await appPage.reload();
    await appPage.getByRole("textbox", { name: "Message à envoyer" }).fill("Message synthétique");
    await appPage.getByRole("button", { name: "Envoyer à ChatGPT", exact: true }).click();
    const progress = appPage.getByLabel("Suivi du message");
    await expect(progress.getByRole("progressbar")).toBeVisible();
    await expect(progress.getByRole("progressbar")).not.toHaveAttribute("value");
    await expect(appPage.getByRole("button", { name: "Arrêter la réponse" })).toBeVisible();
    const box = await progress.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    await appPage.screenshot({ path: testInfo.outputPath(`progress-${width}.png`) });
    await appPage.emulateMedia({ reducedMotion: "reduce" });
    await expect(progress.locator(".task-spinner")).toHaveCSS("animation-name", "none");
  });
}
