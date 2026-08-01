import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useAccessibleDialog } from "./useAccessibleDialog";

function Harness() {
  const [open, setOpen] = useState(false);
  const ref = useAccessibleDialog({ open, onClose: () => setOpen(false) });
  return <><button onClick={() => setOpen(true)}>Ouvrir</button>{open && <section ref={ref}><button>Premier</button><button>Dernier</button></section>}</>;
}

describe("useAccessibleDialog", () => {
  it("handles Escape and restores trigger focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Ouvrir" });
    await user.click(trigger);
    expect(screen.getByRole("button", { name: "Premier" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("button", { name: "Premier" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
