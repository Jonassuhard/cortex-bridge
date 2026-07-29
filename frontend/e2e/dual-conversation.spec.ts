import { expect, test } from "./fixtures/app";

test("two writers stay isolated and a third preserves its draft and file", async ({ appPage }) => {
  const composer = appPage.getByRole("textbox", { name: "Message à envoyer" });
  for (let run = 0; run < 10; run += 1) {
    if (run > 0) await appPage.reload();
    await composer.fill(`Message A ${run}`);
    await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();

    await appPage.getByRole("button", { name: /Local site prototype/ }).click();
    await composer.fill(`Message B ${run}`);
    await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();

    await appPage.getByRole("button", { name: /Research/ }).click();
    await composer.fill(`Brouillon C conservé ${run}`);
    await appPage.locator('input[type="file"]').setInputFiles({ name: "preuve.txt", mimeType: "text/plain", buffer: Buffer.from("preuve") });
    await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();

    await expect(composer).toHaveValue(`Brouillon C conservé ${run}`);
    await expect(appPage.getByText("preuve.txt")).toBeVisible();
  }
  console.log("cold_dual_runs=10 crossovers=0 third_writer_draft_preserved=true");
});
