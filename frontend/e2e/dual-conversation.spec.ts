import { expect, test } from "./fixtures/app";

test("two writers stay isolated and a third preserves its draft and file", async ({ appPage }) => {
  const composer = appPage.getByRole("textbox", { name: "Message à envoyer" });
  await composer.fill("Message A");
  await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();

  await appPage.getByRole("button", { name: /Local site prototype/ }).click();
  await composer.fill("Message B");
  await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();

  await appPage.getByRole("button", { name: /Research/ }).click();
  await composer.fill("Brouillon C conservé");
  await appPage.locator('input[type="file"]').setInputFiles({ name: "preuve.txt", mimeType: "text/plain", buffer: Buffer.from("preuve") });
  await appPage.getByRole("button", { name: "Envoyer", exact: true }).click();

  await expect(composer).toHaveValue("Brouillon C conservé");
  await expect(appPage.getByText("preuve.txt")).toBeVisible();
});
