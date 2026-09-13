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
  it("blocks all dispatch paths when the composer is blocked independently of execution", async () => {
    const props = renderComposer({ blocked: true, executionBlocked: false });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Envoyer/ }));
    await user.click(screen.getByRole("button", { name: /Exécuter/ }));
    expect(props.onSend).not.toHaveBeenCalled();
    expect(props.onPrepareExecution).not.toHaveBeenCalled();
  });

  it("makes the message destination visible and sends without starting local work", async () => {
    const props = renderComposer();
    await userEvent.setup().click(screen.getByRole("button", { name: "Envoyer à ChatGPT" }));
    expect(props.onSend).toHaveBeenCalledTimes(1);
    expect(props.onPrepareExecution).not.toHaveBeenCalled();
  });

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
    await userEvent.setup().click(screen.getByRole("button", { name: "Exécuter sur ce Mac…" }));
    expect(props.onPrepareExecution).toHaveBeenCalledTimes(1);
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it.each([
    {
      label: "fichier",
      file: new File([new Uint8Array(2 * 1024 * 1024 + 1)], "archive.pdf", { type: "application/pdf" }),
      limit: "2 Mo",
    },
    {
      label: "image",
      file: new File([new Uint8Array(1024 * 1024 + 1)], "capture.png", { type: "image/png" }),
      limit: "1 Mo",
    },
  ])("rejects an oversized $label without replacing the staged attachment or draft", async ({ file, limit }) => {
    const existing = new File(["original"], "original.txt", { type: "text/plain" });
    const capabilities = {
      upload_file: true,
      take_screenshot: true,
      limits: { file_bytes: 2 * 1024 * 1024, image_bytes: 1024 * 1024 },
    };
    const props = renderComposer({ attachment: existing, capabilities });
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("file input missing");

    await userEvent.setup().upload(input, file);

    expect(screen.getByRole("alert")).toHaveTextContent(new RegExp(`limite.*${limit}`, "i"));
    expect(screen.getByRole("textbox", { name: "Message à envoyer" })).toHaveValue("Brouillon exact");
    expect(screen.getByText("original.txt")).toBeInTheDocument();
    expect(screen.queryByText(file.name)).not.toBeInTheDocument();
    expect(props.onAttachmentStaged).not.toHaveBeenCalled();
  });

  it("uses the fail-closed 20 MiB image limit when capabilities omit limits", async () => {
    const file = new File(["image"], "capture.png", { type: "image/png" });
    Object.defineProperty(file, "size", { value: 20 * 1024 * 1024 + 1 });
    const props = renderComposer();
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("file input missing");

    await userEvent.setup().upload(input, file);

    expect(screen.getByRole("alert")).toHaveTextContent(/limite.*20 Mo/i);
    expect(props.onAttachmentStaged).not.toHaveBeenCalled();
  });

  it("refuses an image when the active transport does not advertise image upload", async () => {
    const props = renderComposer({
      capabilities: {
        upload_file: true,
        upload_image: false,
        take_screenshot: true,
      },
    });
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("file input missing");

    await userEvent.setup().upload(
      input,
      new File(["image"], "capture.png", { type: "image/png" }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/images.*indisponibles/i);
    expect(props.onAttachmentStaged).not.toHaveBeenCalled();
  });
});
