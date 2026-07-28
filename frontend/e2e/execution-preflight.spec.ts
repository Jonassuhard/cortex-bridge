import { expect, test } from "./fixtures/app";

test("execution remains preflight-only until confirmation", async ({ appPage }) => {
  const missionRequests: string[] = [];
  appPage.on("request", (request) => { if (new URL(request.url()).pathname === "/api/missions" && request.method() === "POST") missionRequests.push(request.postData() || ""); });
  await appPage.getByRole("textbox", { name: "Message à envoyer" }).fill("Inspecter le workspace");
  await appPage.getByRole("button", { name: "Exécuter…" }).click();
  await expect(appPage.getByRole("dialog", { name: "Vérifier l’exécution locale" })).toBeVisible();
  expect(missionRequests).toEqual([]);
  await appPage.getByRole("button", { name: "Démarrer en lecture seule" }).click();
  await expect.poll(() => missionRequests.length).toBe(1);
  expect(JSON.parse(missionRequests[0])).toMatchObject({ allow_processes: false, allow_network: false, allow_write: false });
});
