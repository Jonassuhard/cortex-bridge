import { expect, test } from "./fixtures/app";

test("has zero page, console, or hydration errors", async ({ appPage }) => {
  const errors: string[] = [];
  appPage.on("pageerror", (error) => errors.push(`page: ${error.message}`));
  appPage.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  await appPage.reload();
  await expect(appPage.getByRole("main", { name: "Conversation principale" })).toBeVisible();
  expect(errors.filter((error) => /hydration|error|failed/i.test(error))).toEqual([]);
});
