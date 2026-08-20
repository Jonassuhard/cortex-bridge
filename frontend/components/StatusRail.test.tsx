import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusRail } from "./StatusRail";

describe("StatusRail", () => {
  it("keeps transport and executor truth independent and humanized", () => {
    render(<StatusRail transport="connected" executor="unavailable" execution="WAITING_FOR_APPROVAL" latencyMs={null} />);
    expect(screen.getByTitle("Statut de la connexion ChatGPT")).toHaveTextContent("Connecté");
    expect(screen.getByTitle("Statut de l'agent exécutif local")).toHaveTextContent("Approbation requise");
    expect(screen.queryByText("connected")).not.toBeInTheDocument();
    expect(screen.queryByText("WAITING_FOR_APPROVAL")).not.toBeInTheDocument();
    expect(screen.queryByText("Latence")).not.toBeInTheDocument();
  });
});
