import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { CortexProjectCard } from "./CortexProjectCard";

it.each(["PAUSED", "PAUSED_RECOVERY_REQUIRED", "WAITING_FOR_APPROVAL", "COMPLETED", "FAILED", "CANCELLED", "BLOCKED", "UNKNOWN", "QUEUED"])("does not suggest work for mission %s", missionState => {
  render(<CortexProjectCard active missionState={missionState} />);
  expect(screen.getByLabelText("Carte projet Cortex")).toHaveAttribute("data-busy", "false");
});
it.each(["INITIALIZING_MISSION", "SENDING_OBJECTIVE", "PARSING_DECISION", "EXECUTING_LOCAL_ACTION", "SENDING_REPORT", "VALIDATING_ACTION", "FINAL_VALIDATION", "WAITING_FOR_CHATGPT"])("animates confirmed mission work %s", missionState => {
  render(<CortexProjectCard active missionState={missionState} />);
  expect(screen.getByLabelText("Carte projet Cortex")).toHaveAttribute("data-busy", "true");
});
it("stops when work completes and closes on deactivation", () => {
  const { rerender } = render(<CortexProjectCard active chatState="CHATGPT_STREAMING" />);
  const card = screen.getByLabelText("Carte projet Cortex");
  expect(card).toHaveAttribute("data-busy", "true");
  rerender(<CortexProjectCard active chatState="COMPLETED" />);
  expect(card).toHaveAttribute("data-busy", "false");
  rerender(<CortexProjectCard active={false} chatState="CHATGPT_STREAMING" />);
  expect(card).toHaveAttribute("data-active", "false");
  expect(card).toHaveAttribute("data-busy", "false");
});
it.each(["FAILED", "CANCELLED", "DELIVERY_UNCERTAIN", "QUEUED", "UNKNOWN"])("does not animate chat %s", chatState => {
  render(<CortexProjectCard active chatState={chatState} />);
  expect(screen.getByLabelText("Carte projet Cortex")).toHaveAttribute("data-busy", "false");
});
