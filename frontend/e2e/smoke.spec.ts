import { expect, test } from "./fixtures/app";

test("loads the synthetic conversation UI from loopback fixtures", async ({ appPage }) => {
  await expect(appPage.getByRole("main", { name: "Conversation principale" })).toBeVisible();
  await expect(appPage.getByText("Release checklist", { exact: true }).first()).toBeVisible();
  expect(new URL(appPage.url()).origin).toBe("http://127.0.0.1:3420");
});

test("Chrome connection opens the login dialog and retries the same tab", async ({ appPage }) => {
  await appPage.getByRole("button", { name: "Ouvrir et connecter ChatGPT" }).click();

  await expect(appPage.getByRole("heading", { name: "Connexion à ChatGPT requise" })).toBeVisible();
  await expect(appPage.getByText(/Connecte-toi dans l’onglet ChatGPT/)).toBeVisible();
  await appPage.getByRole("button", { name: "Réessayer" }).click();
  await expect(appPage.getByRole("heading", { name: "Connexion à ChatGPT requise" })).toBeHidden();
  await expect(appPage.getByTitle("Statut de la connexion ChatGPT")).toContainText("Connecté");
});
