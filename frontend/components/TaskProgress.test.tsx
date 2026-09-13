import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TaskProgress } from "./TaskProgress";

afterEach(() => vi.useRealTimers());

it("uses indeterminate progress for sending, never an invented percentage", () => {
  render(<TaskProgress kind="chat" state="SENDING_TO_CHATGPT" />);
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  expect(screen.getByRole("status")).toHaveTextContent("Envoi à ChatGPT");
});

it.each(["DELIVERY_UNCERTAIN", "FAILED", "CANCELLED", "COMPLETED", "UNRECOGNIZED"])("does not animate chat state %s", (state) => {
  render(<TaskProgress kind="chat" state={state} />);
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

it.each(["WAITING_FOR_APPROVAL", "PAUSED", "PAUSED_RECOVERY_REQUIRED", "COMPLETED", "FAILED", "UNKNOWN"])("does not pretend a mission is working in %s", (state) => {
  render(<TaskProgress kind="mission" state={state} />);
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

it("counts elapsed wall time from the recorded start and stops the ticker on pause", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-10T12:00:00Z"));
  const { rerender } = render(<TaskProgress kind="mission" state="EXECUTING_LOCAL_ACTION" startedAt="2026-09-10T11:59:00Z" />);
  expect(screen.getByLabelText("Temps depuis le démarrage")).toHaveTextContent("1 min 0 s");
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByLabelText("Temps depuis le démarrage")).toHaveTextContent("1 min 2 s");
  rerender(<TaskProgress kind="mission" state="PAUSED" startedAt="2026-09-10T11:59:00Z" />);
  expect(screen.queryByLabelText("Temps depuis le démarrage")).not.toBeInTheDocument();
  expect(vi.getTimerCount()).toBe(0);
});

it("does not turn an invalid date into an elapsed time", () => {
  render(<TaskProgress kind="chat" state="CHATGPT_STREAMING" startedAt="invalid" />);
  expect(screen.queryByLabelText("Temps depuis le démarrage")).not.toBeInTheDocument();
});
