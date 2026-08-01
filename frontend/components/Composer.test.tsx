import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

function renderComposer(overrides: Partial<React.ComponentProps<typeof Composer>> = {}) {
  const props: React.ComponentProps<typeof Composer> = {
    value: "Brouillon exact",
    attachment: null,
    blocked: false,
    executionBlocked: false,
    chatActive: false,
    cancelPending: false,
    capabilities: { upload_file: true, take_screenshot: true },
    workspaceLabel: "atlas",
    onChange: vi.fn<(value: string) => void>(),
    onAttachmentStaged: vi.fn<(file: File | null) => void>(),
    onSend: vi.fn<() => void>(),
    onScreenshot: vi.fn<() => void>(),
    onPrepareExecution: vi.fn<() => void>(),
    onCancelChat: vi.fn<() => void>(),
    ...overrides,
  };
  render(<Composer {...props} />);
  return props;
}

describe("Composer", () => {
  it("maps Enter only to ChatGPT send", async () => {
    const props = renderComposer();
    await userEvent.setup().type(screen.getByRole("textbox", { name: "Message à envoyer" }), "{enter}");
    expect(props.onSend).toHaveBeenCalledTimes(1);
    expect(props.onPrepareExecution).not.toHaveBeenCalled();
  });

  it("leaves Shift+Enter to the textarea", async () => {
    const props = renderComposer();
    await userEvent.setup().type(screen.getByRole("textbox", { name: "Message à envoyer" }), "{shift>}{enter}{/shift}");
    expect(props.onSend).not.toHaveBeenCalled();
    expect(props.onPrepareExecution).not.toHaveBeenCalled();
  });

  it("opens execution review without sending", async () => {
    const props = renderComposer();
    await userEvent.setup().click(screen.getByRole("button", { name: "Exécuter…" }));
    expect(props.onPrepareExecution).toHaveBeenCalledTimes(1);
    expect(props.onSend).not.toHaveBeenCalled();
  });
});
