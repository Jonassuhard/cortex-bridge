import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CheckIcon, RefreshIcon, SearchIcon } from "./Icons";

describe("Cortex icon contract", () => {
  it("keeps decorative icons out of the accessible name and gives them a nonshrinking slot", () => {
    const { container } = render(<SearchIcon size={20} />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("focusable", "false");
    expect(svg).toHaveAttribute("width", "20");
    expect(svg).toHaveClass("cortex-icon");
  });
  it("animates refresh only on explicit busy state", () => {
    const { container, rerender } = render(<RefreshIcon />);
    expect(container.querySelector("svg")).not.toHaveClass("is-busy");
    rerender(<RefreshIcon busy />);
    expect(container.querySelector("svg")).toHaveClass("is-busy");
    rerender(<RefreshIcon busy={false} />);
    expect(container.querySelector("svg")).not.toHaveClass("is-busy");
  });
  it("does not replay old confirmations unless explicitly requested", () => {
    const { container, rerender } = render(<CheckIcon />);
    expect(container.querySelector("svg")).not.toHaveClass("is-confirmed");
    rerender(<CheckIcon confirmed />);
    expect(container.querySelector("svg")).toHaveClass("is-confirmed");
  });
});
