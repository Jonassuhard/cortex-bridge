import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));
const oxlint = join(frontendRoot, "node_modules", ".bin", "oxlint");
const config = join(frontendRoot, ".oxlintrc.json");
const fixtureRoot = mkdtempSync(join(frontendRoot, ".lint-contract-"));

const cases = [
  {
    name: "conditional React hook",
    entry: "fixture.tsx",
    expectedCode: "react-hooks(rules-of-hooks)",
    files: {
      "fixture.tsx": `import { useState } from "react";
export function ConditionalHook({ enabled }: { enabled: boolean }) {
  if (enabled) {
    const [value] = useState(0);
    return <span>{value}</span>;
  }
  return null;
}
`,
    },
  },
  {
    name: "duplicate TypeScript enum value",
    entry: "fixture.ts",
    expectedCode: "typescript(no-duplicate-enum-values)",
    files: {
      "fixture.ts": `export enum Direction {
  Up = 1,
  Down = 1,
}
`,
    },
  },
  {
    name: "missing default import",
    entry: "fixture.js",
    expectedCode: "import(default)",
    files: {
      "fixture.js": `import missing from "./module.js";
export const value = missing;
`,
      "module.js": "export const present = 1;\n",
    },
  },
  {
    name: "empty accessible anchor",
    entry: "fixture.tsx",
    expectedCode: "jsx-a11y(anchor-has-content)",
    files: {
      "fixture.tsx": "export const EmptyAnchor = () => <a href=\"/local\" />;\n",
    },
  },
  {
    name: "unoptimized Next image",
    entry: "fixture.tsx",
    expectedCode: "next(no-img-element)",
    files: {
      "fixture.tsx": "export const RawImage = () => <img alt=\"fixture\" src=\"/fixture.png\" />;\n",
    },
  },
  {
    name: "focused Vitest test",
    entry: "fixture.test.ts",
    expectedCode: "vitest(no-focused-tests)",
    files: {
      "fixture.test.ts": `import { expect, it } from "vitest";
it.only("runs alone", () => expect(true).toBe(true));
`,
    },
  },
];

try {
  for (const contractCase of cases) {
    const caseRoot = join(fixtureRoot, contractCase.name.replaceAll(" ", "-"));
    mkdirSync(caseRoot);
    for (const [relativePath, content] of Object.entries(contractCase.files)) {
      writeFileSync(join(caseRoot, relativePath), content, "utf8");
    }

    const result = spawnSync(
      oxlint,
      ["--config", config, "--format", "json", join(caseRoot, contractCase.entry)],
      { cwd: frontendRoot, encoding: "utf8", maxBuffer: 1024 * 1024 },
    );
    assert.equal(result.signal, null, `${contractCase.name}: Oxlint was terminated by ${result.signal}`);
    assert.notEqual(result.status, 0, `${contractCase.name}: fixture unexpectedly passed`);

    const output = result.stdout.trim();
    assert.notEqual(output, "", `${contractCase.name}: Oxlint returned no JSON diagnostics`);
    const diagnosticCodes = JSON.parse(output).diagnostics.map(({ code }) => code);
    assert.ok(
      diagnosticCodes.includes(contractCase.expectedCode),
      `${contractCase.name}: expected ${contractCase.expectedCode}, received ${diagnosticCodes.join(", ") || "none"}`,
    );
  }
} finally {
  rmSync(fixtureRoot, { recursive: true, force: true });
}

assert.equal(existsSync(fixtureRoot), false, "lint contract fixtures were not cleaned up");
console.log(`lint contract: ${cases.length} rule families rejected their neutral fixtures`);
