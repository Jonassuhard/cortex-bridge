import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

Object.defineProperty(Element.prototype, "scrollTo", {
  configurable: true,
  value: () => undefined,
});

afterEach(() => {
  cleanup();
});
