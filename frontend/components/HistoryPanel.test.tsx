import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { HistoryPanel } from "./HistoryPanel";
const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn<(path: string) => Promise<unknown>>() }));
vi.mock("@/lib/api", () => ({ api: apiMock }));
beforeEach(() => { apiMock.mockReset(); });
const rows = [
  { id: "a", objective: "Relire le site", workspace: "/tmp/site", state: "COMPLETED", created_at: 1 },
  { id: "b", objective: "Vérifier les tests", workspace: "/tmp/api", state: "FAILED", created_at: 1 },
];
it("filters mission history by project and status", async () => {
  apiMock.mockResolvedValue(rows);
  const user = userEvent.setup();
  render(<HistoryPanel open onClose={() => undefined} />);
  await screen.findByText("Relire le site");
  await user.type(screen.getByRole("searchbox", { name: "Rechercher une mission ou un projet" }), "/tmp/api");
  expect(screen.queryByText("Relire le site")).not.toBeInTheDocument();
  expect(screen.getByText("Vérifier les tests")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Filtrer par état"), "COMPLETED");
  expect(screen.queryByText("Vérifier les tests")).not.toBeInTheDocument();
});
it("ends detail loading when fetching a mission fails", async () => {
  apiMock.mockImplementation((path) => path === "/api/missions" ? Promise.resolve(rows) : Promise.reject(new Error("offline")));
  const user = userEvent.setup();
  render(<HistoryPanel open onClose={() => undefined} />);
  await user.click(await screen.findByText("Relire le site"));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Impossible de charger le détail"));
  expect(screen.queryByText("Chargement du détail…")).not.toBeInTheDocument();
});
