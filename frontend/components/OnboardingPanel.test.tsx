import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { OnboardingPanel } from "./OnboardingPanel";

vi.mock("@/lib/api", () => ({
  api: vi.fn<() => Promise<unknown>>().mockResolvedValue({ completed: false, ready: false, checks: [] }),
  postJson: vi.fn<() => Promise<unknown>>().mockResolvedValue({}),
}));

it("keeps keyboard focus in onboarding and closes with Escape", async () => {
  const user = userEvent.setup();
  render(<OnboardingPanel onOpenSettings={() => undefined} onOpenChatGPTProfile={() => undefined} />);
  const close = await screen.findByRole("button", { name: "Fermer l'assistant" });
  await waitFor(() => expect(close).toHaveFocus());
  await user.tab({ shift: true });
  expect(screen.getByRole("button", { name: "Continuer quand même" })).toHaveFocus();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});
