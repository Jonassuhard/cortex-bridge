import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConversationSidebar } from "./ConversationSidebar";

describe("ConversationSidebar", () => {
  it("renders a neutral local account identity", () => {
    render(
      <ConversationSidebar
        collapsed={false}
        conversations={[]}
        loading={false}
        onCollapse={() => undefined}
        onNewConversation={() => undefined}
        onOpenSettings={() => undefined}
        onRefresh={() => undefined}
        onSelect={() => undefined}
        selectedKey={null}
      />,
    );

    expect(screen.getByText("CL")).toBeInTheDocument();
    expect(screen.getByText("Compte local")).toBeInTheDocument();
    expect(screen.getByText("Session locale")).toBeInTheDocument();
  });

  it("selects only one provisional UUID even when two rows share the new-chat URL", () => {
    render(
      <ConversationSidebar
        collapsed={false}
        conversations={[
          { url: "https://chatgpt.com/", identity: "provisional:a", title: "Nouveau A" },
          { url: "https://chatgpt.com/", identity: "provisional:b", title: "Nouveau B" },
        ]}
        loading={false}
        onCollapse={() => undefined}
        onNewConversation={() => undefined}
        onOpenSettings={() => undefined}
        onRefresh={() => undefined}
        onSelect={() => undefined}
        selectedKey="provisional:b"
      />,
    );

    const selected = screen.getAllByRole("button").filter((row) => row.getAttribute("aria-current") === "page");
    expect(selected).toHaveLength(1);
    expect(selected[0]).toHaveTextContent("Nouveau B");
  });

  it("renders exclusive pinned, project, and recent groups without fabricated metadata", () => {
    render(
      <ConversationSidebar
        collapsed={false}
        conversations={[
          { url: "https://chatgpt.com/c/pinned", identity: "pinned", title: "Épinglée réelle", pinned: true },
          { url: "https://chatgpt.com/c/project", identity: "project", title: "Projet réel", project: true, project_id: "atlas", project_title: "Atlas" },
          { url: "https://chatgpt.com/c/recent", identity: "recent", title: "Récente réelle" },
        ]}
        loading={false}
        onCollapse={() => undefined}
        onNewConversation={() => undefined}
        onOpenSettings={() => undefined}
        onRefresh={() => undefined}
        onSelect={() => undefined}
        selectedKey={null}
      />,
    );

    expect(screen.getByRole("heading", { name: "Épinglées" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Atlas" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Récentes" })).toBeInTheDocument();
    expect(screen.getAllByText("Épinglée réelle")).toHaveLength(1);
    expect(screen.queryByText("Non synchronisé")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nouvelle mission" })).not.toBeInTheDocument();
  });
});
