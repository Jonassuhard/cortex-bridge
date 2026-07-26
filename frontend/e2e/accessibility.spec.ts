import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures/app";

test("@a11y exposes one named main landmark", async ({ appPage }) => {
  await expect(appPage.getByRole("main", { name: "Conversation principale" })).toBeVisible();

  const results = await new AxeBuilder({ page: appPage })
    .withRules(["landmark-one-main"])
    .analyze();

  expect(results.violations).toEqual([]);
});
