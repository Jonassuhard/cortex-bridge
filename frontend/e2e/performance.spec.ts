import { expect, test } from "./fixtures/app";

test("cached fixture interface becomes usable below two seconds", async ({ appPage }) => {
  await expect(appPage.getByRole("textbox", { name: "Message à envoyer" })).toBeEditable();
  const usableMs = await appPage.evaluate(() => performance.now());
  expect(usableMs).toBeLessThan(2000);
  console.log(`cached_usability_ms=${usableMs.toFixed(1)}`);
});

test("ten A/B switches stay below p95 and hard maximum", async ({ appPage }) => {
  const samples: number[] = [];
  for (let index = 0; index < 10; index += 1) {
    const title = index % 2 ? "Release checklist" : "Local site prototype";
    const started = performance.now();
    await appPage.getByRole("button", { name: new RegExp(title) }).click();
    await expect(appPage.getByRole("heading", { name: title })).toBeVisible();
    samples.push(performance.now() - started);
  }
  const sorted = [...samples].sort((a, b) => a - b);
  const p95 = sorted[Math.ceil(sorted.length * 0.95) - 1];
  expect(p95).toBeLessThan(3000);
  expect(Math.max(...samples)).toBeLessThan(10000);
  console.log(`switch_samples_ms=${samples.map((sample) => sample.toFixed(1)).join(",")} p95_ms=${p95.toFixed(1)} max_ms=${Math.max(...samples).toFixed(1)}`);
});
