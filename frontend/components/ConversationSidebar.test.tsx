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
    expect(screen.getByText("Session locale")).toBeInTheDocument();

    const formerInitials = String.fromCharCode(74, 83);
    const formerAccountName = String.fromCharCode(
      74, 111, 110, 97, 115, 32, 83, 117, 104, 97, 114, 100,
    );
    const formerSessionLabel = String.fromCharCode(
      76, 111, 99, 97, 108, 32, 183, 32, 67, 104, 97, 116, 71, 80, 84, 32, 80, 114, 111,
    );

    expect(screen.queryByText(formerInitials)).not.toBeInTheDocument();
    expect(screen.queryByText(formerAccountName)).not.toBeInTheDocument();
    expect(screen.queryByText(formerSessionLabel)).not.toBeInTheDocument();
  });
});
