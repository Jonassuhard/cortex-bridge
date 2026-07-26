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
        onNewMission={() => undefined}
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
        onNewMission={() => undefined}
        onOpenSettings={() => undefined}
        onRefresh={() => undefined}
        onSelect={() => undefined}
        selectedKey="provisional:b"
      />,
    );

    const selected = screen.getAllByRole("option").filter((row) => row.getAttribute("aria-selected") === "true");
    expect(selected).toHaveLength(1);
    expect(selected[0]).toHaveTextContent("Nouveau B");
  });
});
