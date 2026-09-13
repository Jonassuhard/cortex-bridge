import { expect, test } from "./fixtures/app";

test("refresh motion follows the request and respects reduced motion", async ({ appPage }) => {
  const button = appPage.getByRole("button", { name: "Actualiser les conversations", exact: true });
  const icon = button.locator("svg");
  await expect(icon).toHaveCSS("animation-name", "none");
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await appPage.route("**/api/conversations", async (route) => {
    await pending;
    await route.fallback();
  });
  await button.click();
  try {
    await expect(button).toHaveAttribute("aria-busy", "true");
    await expect(icon).toHaveCSS("animation-name", "task-spin");
    const before = await icon.evaluate((el) => getComputedStyle(el).transform);
    await expect.poll(() => icon.evaluate((el) => getComputedStyle(el).transform)).not.toBe(before);
    await appPage.emulateMedia({ reducedMotion: "reduce" });
    await expect(icon).toHaveCSS("animation-name", "none");
  } finally { release(); }
  await expect(button).toHaveAttribute("aria-busy", "false");
  await appPage.emulateMedia({ reducedMotion: "no-preference" });
  await expect(icon).toHaveCSS("animation-name", "none");
});

test("send icon responds to pressing without moving its layout slot", async ({ appPage }) => {
  const button = appPage.getByRole("button", { name: "Envoyer à ChatGPT", exact: true });
  await appPage.getByRole("textbox", { name: "Message à envoyer" }).fill("Brouillon synthétique non envoyé");
  const box = (await button.boundingBox())!;
  await appPage.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await appPage.mouse.down();
  const icon = button.locator("svg");
  await expect(icon).toHaveCSS("transform", "matrix(1, 0, 0, 1, 2, -2)");
  expect(await button.boundingBox()).toEqual(box);
  // Release outside: no message dispatched.
  await appPage.mouse.move(0, 0);
  await appPage.mouse.up();
  await expect(icon).toHaveCSS("transform", "none");
});
