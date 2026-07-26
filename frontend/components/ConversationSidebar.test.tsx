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
        selectedUrl={null}
      />,
    );

    expect(screen.getByText("CL")).toBeInTheDocument();
    expect(screen.getByText("Compte local")).toBeInTheDocument();
  });
});
