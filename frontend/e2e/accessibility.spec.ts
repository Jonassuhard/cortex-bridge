import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures/app";

test("@a11y has no automated accessibility violations", async ({ appPage }) => {
  await expect(appPage.getByRole("main", { name: "Conversation principale" })).toBeVisible();

  const results = await new AxeBuilder({ page: appPage }).analyze();

  expect(results.violations).toEqual([]);
});
