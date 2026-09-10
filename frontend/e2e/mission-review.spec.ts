import { fileURLToPath } from "node:url";
import { expect, test } from "./fixtures/app";

for (const width of [375, 768, 1440]) {
  test(`mission review and recorded diff ${width}px`, async ({ appPage }) => {
    await appPage.setViewportSize({ width, height: width === 375 ? 812 : 1024 });
    await appPage.emulateMedia({ reducedMotion: "reduce" });
    const decisions: unknown[] = [];
    await appPage.route("**/api/missions/fixture-mission/approve", async (route) => {
      decisions.push(route.request().postDataJSON());
      await route.fulfill({ json: { approved: false, scope: null } });
    });
    await appPage.route("**/api/missions/fixture-mission", (route) => route.fulfill({ json: {
      mission: { id: "fixture-mission", objective: "Démo isolée · Mettre à jour le titre", workspace: "/tmp/cortex-demo-workspace", state: "WAITING_FOR_APPROVAL", created_at: 1 },
      awaiting_approval: true, stopped: false,
      timeline: {
        policy_decisions: [{ action_id: "a1", tool: "write_file", requires_approval: 1 }],
        orchestrator_decisions: [{ action_id: "a1", valid: 1, decision_json: JSON.stringify({ action: { tool: "write_file", arguments: { path: "title.txt", content: "Cortex Atelier" } } }) }],
        artifacts: [{ id: "report", name: "Rapport synthétique", path: "/tmp/cortex-demo-workspace/report.md" }],
        tool_executions: [{ id: "previous", tool: "apply_patch", exit_code: 0, result_json: JSON.stringify({ path: "README.md", diff: "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-Cortex\n+Cortex Bridge" }) }],
      },
    } }));
    await appPage.reload();
    await appPage.getByRole("textbox", { name: "Message à envoyer" }).fill("Démo isolée");
    await appPage.getByRole("button", { name: "Exécuter sur ce Mac…" }).click();
    await appPage.getByRole("button", { name: "Démarrer en lecture seule" }).click();
    // The transient notice must not cover cancellation or auto-continue controls.
    const notice = await appPage.locator(".app-toast").boundingBox();
    const composer = await appPage.locator(".composer-box").boundingBox();
    expect(notice).not.toBeNull();
    expect(notice!.y + notice!.height).toBeLessThanOrEqual(composer!.y);
    await expect(appPage.locator(".inline-approval").getByText("Approbation requise", { exact: true })).toBeVisible();
    expect(decisions).toEqual([]);
    if (process.env.CORTEX_DOCS_GUIDE === "1") {
      await appPage.getByRole("button", { name: "Approuver une fois" }).scrollIntoViewIfNeeded();
      await appPage.screenshot({ path: fileURLToPath(new URL(`../../docs/screenshots/v0.6.1/${width}/12-approval.png`, import.meta.url)), animations: "disabled" });
    }
    await appPage.getByRole("button", { name: "Afficher le détail" }).click();
    const diff = appPage.getByText("Diff enregistré · README.md", { exact: true });
    await diff.click();
    await expect(appPage.locator(".mission-diff pre")).toHaveText(/\+Cortex Bridge/);
    if (process.env.CORTEX_DOCS_GUIDE === "1") {
      await appPage.locator(".mission-diff pre").scrollIntoViewIfNeeded();
      await appPage.screenshot({ path: fileURLToPath(new URL(`../../docs/screenshots/v0.6.1/${width}/12-mission-review.png`, import.meta.url)), animations: "disabled" });
    }
    await appPage.getByRole("button", { name: "Refuser", exact: true }).click();
    await expect.poll(() => decisions.length).toBe(1);
    expect(decisions[0]).toMatchObject({ approve: false });
  });
}
