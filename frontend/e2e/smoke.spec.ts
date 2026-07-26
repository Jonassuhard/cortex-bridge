import { expect, test } from "./fixtures/app";

test("loads the synthetic conversation UI from loopback fixtures", async ({ appPage }) => {
  await expect(appPage.getByRole("main", { name: "Conversation principale" })).toBeVisible();
  await expect(appPage.getByText("Release checklist", { exact: true }).first()).toBeVisible();
  expect(new URL(appPage.url()).origin).toBe("http://127.0.0.1:3420");
});
