import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChromeConnectionResult } from "@/lib/types";
import { ChatGPTConnectionDialog } from "./ChatGPTConnectionDialog";


const loginRequired: ChromeConnectionResult = {
  code: "LOGIN_REQUIRED",
  state: "manual_action",
  title: "Connexion à ChatGPT requise",
  message: "ChatGPT est ouvert dans Chrome, mais tu n’es pas connecté. Connecte-toi dans l’onglet ChatGPT, puis réessaie.",
  recoverable: true,
  driver: "chrome_extension",
  url: "https://chatgpt.com/auth/login",
  tab_id: 42,
  window_id: 7,
};

describe("ChatGPTConnectionDialog", () => {
  it("explains login without hiding the retry and close actions", async () => {
    const onRetry = vi.fn<() => void>();
    const onClose = vi.fn<() => void>();
    render(
      <ChatGPTConnectionDialog
        open
        result={loginRequired}
        busy={false}
        onRetry={onRetry}
        onClose={onClose}
      />,
    );

    expect(screen.getByRole("heading", { name: "Connexion à ChatGPT requise" })).toBeInTheDocument();
    expect(screen.getByText(/Connecte-toi dans l’onglet ChatGPT/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    await userEvent.setup().click(screen.getByRole("button", { name: "Fermer" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape and returns focus to the trigger", () => {
    const onClose = vi.fn<() => void>();
    const trigger = document.createElement("button");
    trigger.textContent = "Ouvrir et connecter ChatGPT";
    document.body.append(trigger);
    trigger.focus();
    const rendered = render(
      <ChatGPTConnectionDialog
        open
        result={loginRequired}
        busy={false}
        onRetry={vi.fn<() => void>()}
        onClose={onClose}
      />,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    rendered.unmount();
    expect(trigger).toHaveFocus();
    trigger.remove();
  });

  it("disables retry while the connection is being checked", () => {
    render(
      <ChatGPTConnectionDialog
        open
        result={{
          ...loginRequired,
          code: "CHATGPT_LOADING",
          state: "checking",
          title: "ChatGPT est encore en chargement",
          message: "Garde l’onglet ChatGPT ouvert et réessaie dans un instant.",
        }}
        busy
        onRetry={vi.fn<() => void>()}
        onClose={vi.fn<() => void>()}
      />,
    );

    expect(screen.getByRole("button", { name: "Vérification en cours…" })).toBeDisabled();
  });
});
