import { readFile } from "node:fs/promises";
import { expect, test } from "./fixtures/app";

test("requests a fixture diagnostic download without claiming that a file was written", async ({ appPage }, testInfo) => {
  await appPage.getByRole("button", { name: "Paramètres" }).click();
  await appPage.getByRole("button", { name: "Diagnostics" }).click();

  const [download] = await Promise.all([
    appPage.waitForEvent("download"),
    appPage.getByRole("button", { name: "Exporter le rapport" }).click(),
  ]);

  await expect(appPage.getByRole("status")).toHaveText(/Téléchargement demandé : cortex-diagnostic-.+\.json/);
  expect(download.suggestedFilename()).toMatch(/^cortex-diagnostic-.+\.json$/);
  await expect(download.failure()).resolves.toBeNull();
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  expect(JSON.parse(await readFile(downloadPath!, "utf8"))).toEqual({
    source: "fixture",
    generated_at: "2026-07-26T08:00:00.000Z",
  });
  await appPage.screenshot({ path: testInfo.outputPath("diagnostics-export-fixture.png"), fullPage: true });
});
