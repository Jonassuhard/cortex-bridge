import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CortexApp } from "./CortexApp";

describe("CortexApp", () => {
  it("exposes a named main conversation region", () => {
    render(<CortexApp />);

    expect(screen.getByRole("main", { name: /conversation/i })).toBeInTheDocument();
  });
});
