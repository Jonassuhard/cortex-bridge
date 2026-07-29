import { expect, test } from "./fixtures/app";

test("execution remains preflight-only until confirmation", async ({ appPage }) => {
  await appPage.setViewportSize({ width: 768, height: 1024 });
  await appPage.reload();
  const missionRequests: string[] = [];
  appPage.on("request", (request) => { if (new URL(request.url()).pathname === "/api/missions" && request.method() === "POST") missionRequests.push(request.postData() || ""); });
  await appPage.getByRole("textbox", { name: "Message à envoyer" }).fill("Inspecter le workspace");
  await appPage.getByRole("button", { name: "Exécuter…" }).click();
  const dialog = appPage.getByRole("dialog", { name: "Vérifier l’exécution locale" });
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  const viewport = appPage.viewportSize();
  expect(viewport).not.toBeNull();
  expect(Math.abs((box!.x + box!.width / 2) - viewport!.width / 2)).toBeLessThan(2);
  expect(box!.x).toBeGreaterThan(20);
  const dialogIsTopmostAtLeftEdge = await dialog.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return document.elementFromPoint(bounds.left + 8, bounds.top + 40)?.closest("dialog") === element;
  });
  expect(dialogIsTopmostAtLeftEdge).toBe(true);
  expect(missionRequests).toEqual([]);
  await appPage.getByRole("button", { name: "Démarrer en lecture seule" }).click();
  await expect.poll(() => missionRequests.length).toBe(1);
  expect(JSON.parse(missionRequests[0])).toMatchObject({ allow_processes: false, allow_network: false, allow_write: false });
});
