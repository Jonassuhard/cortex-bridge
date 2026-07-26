import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { extname } from "node:path";
import { readFileSync } from "node:fs";
import test from "node:test";

const scannedExtensions = new Set([".css", ".html", ".json", ".md", ".mjs", ".mts", ".ts", ".tsx"]);
const excludedFiles = new Set(["package-lock.json", "tsconfig.tsbuildinfo"]);
const excludedDirectories = [".next/", "coverage/", "node_modules/", "out/", "playwright-report/", "test-results/"];

function fromHex(value: string): string {
  return Buffer.from(value, "hex").toString("utf8");
}

const bannedMarkers = [
  ["personal account", "6173746572696f6e"],
  ["personal account", "6a6f6e6173"],
  ["personal account", "737568617264"],
  ["personal workspace", "6b696d69"],
  ["personal volume", "646a6f"],
  ["unrelated project", "636f6f6c2062616e6b"],
  ["unrelated project", "636f6f6c2d62616e6b"],
  ["unrelated project", "636f6f6c5f62616e6b"],
  ["unrelated design brand", "70726575766961"],
  ["personal macOS home", "2f75736572732f"],
  ["personal mounted volume", "2f766f6c756d65732f"],
] as const;

test("committed frontend sources contain only privacy-safe synthetic data", () => {
  const files = execFileSync(
    "git",
    ["ls-files", "--cached", "--others", "--exclude-standard", "--", "."],
    { encoding: "utf8" },
  )
    .split("\n")
    .filter(Boolean)
    .map((file) => file.replace(/^frontend\//, ""))
    .filter((file) => scannedExtensions.has(extname(file)))
    .filter((file) => !excludedFiles.has(file))
    .filter((file) => excludedDirectories.every((directory) => !file.startsWith(directory)));

  const findings: string[] = [];
  for (const file of files) {
    const content = readFileSync(file, "utf8").toLocaleLowerCase("en-US");
    for (const [label, encodedMarker] of bannedMarkers) {
      if (content.includes(fromHex(encodedMarker))) findings.push(`${file}: ${label}`);
    }
  }

  assert.deepEqual(findings, []);
});
