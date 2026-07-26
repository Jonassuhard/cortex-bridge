import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { extname } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

interface PrivacyFingerprint {
  category: string;
  length: number;
  sha256: string;
}

interface SourceSnippet {
  path: string;
  content: string;
}

const scannedExtensions = new Set([
  ".cjs", ".config", ".css", ".html", ".js", ".json", ".jsx", ".md", ".mjs", ".mts",
  ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
]);
const excludedFiles = new Set(["package-lock.json", "tsconfig.tsbuildinfo"]);
const excludedDirectories = [
  ".next/", "coverage/", "node_modules/", "out/", "playwright-report/", "test-results/",
];
const antiObfuscationExclusions = new Set(["test/privacy.test.mts"]);
const astScannedExtensions = new Set([".cjs", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"]);

const bannedFingerprints: PrivacyFingerprint[] = [
  { category: "personal account", length: 8, sha256: "b53fd2a5e757a97ced3d59c11e56f30f793b725e36a30f478d575ff41f340c0d" },
  { category: "personal account", length: 5, sha256: "bf74e4a280affafbdf6692bc6a9f3d66b03094fbfb4a91589bc7fd6b32664fdb" },
  { category: "personal account", length: 6, sha256: "edf7cda2e256d7234fcaeee199840a5ab3442683cd4c9ccc454e3b3fb541c331" },
  { category: "personal workspace", length: 4, sha256: "e4f9c522e1c89280e9561b825f4f24fe32b51ff82d61e5c2b1dfd0321c35a90b" },
  { category: "personal volume", length: 3, sha256: "f68037abc082783e2de1adb2db7d96e6c7a0b8efd04cefd82bc3cac5a0f1fb5e" },
  { category: "unrelated project", length: 9, sha256: "b944f71f549f394c0b2d0fa7a9b1a9305f29eef5ba95cc196ef485b3021ff327" },
  { category: "unrelated project", length: 9, sha256: "2914be845439fef5b6fa99f4c78ed344d786402336ebdb0f52f0fa652bd994b2" },
  { category: "unrelated project", length: 9, sha256: "c97945a464719a1773c92f5801524bb5139a0fbbfb7e6f8ae88bbe0f3d4f4a06" },
  { category: "unrelated design brand", length: 7, sha256: "baba03f4054218588fa0d9394c9bb5c771a335817bad42c2bf3070f5579680cd" },
  { category: "personal macOS home", length: 7, sha256: "3e44fb009899c0f900c1e74cd803b171d70a5d799d2cc933898d78e8d5fc17ca" },
  { category: "personal mounted volume", length: 9, sha256: "6592078a7321c458cd4586c3945ef79b7fd3b13947eba1faa78568364918178d" },
];

function decodeCommonLiteralEscapes(value: string): string {
  let decoded = value;
  for (let pass = 0; pass < 3; pass += 1) {
    const next = decoded
      .replace(/\+/gu, " ")
      .replace(/\\u\{([0-9a-f]{1,6})\}/giu, (_match, codePoint: string) => (
        String.fromCodePoint(Number.parseInt(codePoint, 16))
      ))
      .replace(/\\u([0-9a-f]{4})/giu, (_match, codePoint: string) => (
        String.fromCodePoint(Number.parseInt(codePoint, 16))
      ))
      .replace(/\\x([0-9a-f]{2})/giu, (_match, codePoint: string) => (
        String.fromCodePoint(Number.parseInt(codePoint, 16))
      ))
      .replace(/(?:%[0-9a-f]{2})+/giu, (encoded) => {
        try {
          return decodeURIComponent(encoded);
        } catch {
          return encoded;
        }
      });
    if (next === decoded) break;
    decoded = next;
  }
  return decoded;
}

function normalizePrivacyText(value: string): string {
  return decodeCommonLiteralEscapes(value).normalize("NFKC").toLocaleLowerCase("en-US");
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function fingerprintForSyntheticSentinel(value: string): PrivacyFingerprint {
  const normalized = normalizePrivacyText(value);
  return { category: "synthetic sentinel", length: [...normalized].length, sha256: sha256(normalized) };
}

function findFingerprintCategories(content: string, fingerprints: PrivacyFingerprint[]): string[] {
  const characters = [...normalizePrivacyText(content)];
  const byLength = new Map<number, Map<string, string>>();
  for (const fingerprint of fingerprints) {
    const hashes = byLength.get(fingerprint.length) ?? new Map<string, string>();
    hashes.set(fingerprint.sha256, fingerprint.category);
    byLength.set(fingerprint.length, hashes);
  }

  const findings = new Set<string>();
  for (const [length, hashes] of byLength) {
    for (let index = 0; index <= characters.length - length; index += 1) {
      const category = hashes.get(sha256(characters.slice(index, index + length).join("")));
      if (category) findings.add(category);
    }
  }
  return [...findings];
}

function findDynamicAssemblyCategories(content: string): string[] {
  const patterns = [
    /\bString\s*\.\s*from(?:CharCode|CodePoint)\s*\(/u,
    /\batob\s*\(/u,
    /\bBuffer\s*\.\s*from\s*\([\s\S]{0,200}?,\s*["'`](?:base64|hex)["'`]\s*\)/u,
    /\.split\s*\(\s*["'`][^"'`\n]*["'`]\s*\)\s*\.join\s*\(/u,
    /\[\s*["'`][^"'`\n]*["'`]\s*,\s*["'`][^"'`\n]*["'`](?:\s*,\s*["'`][^"'`\n]*["'`])*\s*\]\s*\.join\s*\(/u,
  ];
  return patterns.some((pattern) => pattern.test(content))
    ? ["dynamic string assembly"]
    : [];
}

function evaluateConstantStringExpression(expression: ts.Expression): string | undefined {
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    return expression.text;
  }
  if (ts.isParenthesizedExpression(expression)) {
    return evaluateConstantStringExpression(expression.expression);
  }
  if (ts.isTemplateExpression(expression)) {
    let value = expression.head.text;
    for (const span of expression.templateSpans) {
      const foldedExpression = evaluateConstantStringExpression(span.expression);
      if (foldedExpression === undefined) return undefined;
      value += foldedExpression + span.literal.text;
    }
    return value;
  }
  if (ts.isBinaryExpression(expression) && expression.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const left = evaluateConstantStringExpression(expression.left);
    const right = evaluateConstantStringExpression(expression.right);
    return left === undefined || right === undefined ? undefined : left + right;
  }
  return undefined;
}

function scriptKindForPath(path: string): ts.ScriptKind {
  switch (extname(path)) {
    case ".cjs":
    case ".js":
    case ".mjs":
      return ts.ScriptKind.JS;
    case ".jsx":
      return ts.ScriptKind.JSX;
    case ".tsx":
      return ts.ScriptKind.TSX;
    default:
      return ts.ScriptKind.TS;
  }
}

function findFoldedFingerprintCategories(
  path: string,
  content: string,
  fingerprints: PrivacyFingerprint[],
): string[] {
  if (!astScannedExtensions.has(extname(path))) return [];

  const sourceFile = ts.createSourceFile(
    path,
    content,
    ts.ScriptTarget.Latest,
    true,
    scriptKindForPath(path),
  );
  const findings = new Set<string>();
  const visit = (node: ts.Node): void => {
    if (ts.isExpression(node)) {
      const folded = evaluateConstantStringExpression(node);
      if (folded !== undefined) {
        for (const category of findFingerprintCategories(folded, fingerprints)) {
          findings.add(category);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return [...findings];
}

function isScannableSource(path: string): boolean {
  return scannedExtensions.has(extname(path));
}

function scanSources(sources: SourceSnippet[], fingerprints: PrivacyFingerprint[]): string[] {
  const findings: string[] = [];
  for (const source of sources) {
    if (!isScannableSource(source.path)) continue;
    const sourceCategories = new Set<string>();
    for (const category of findFingerprintCategories(source.content, fingerprints)) {
      sourceCategories.add(category);
    }
    for (const category of findFoldedFingerprintCategories(source.path, source.content, fingerprints)) {
      sourceCategories.add(category);
    }
    if (!antiObfuscationExclusions.has(source.path)) {
      for (const category of findDynamicAssemblyCategories(source.content)) {
        sourceCategories.add(category);
      }
    }
    for (const category of sourceCategories) findings.push(`${source.path}: ${category}`);
  }
  return findings;
}

function trackedFrontendSources(): SourceSnippet[] {
  return execFileSync(
    "git",
    ["ls-files", "--cached", "--others", "--exclude-standard", "--", "."],
    { encoding: "utf8" },
  )
    .split("\n")
    .filter(Boolean)
    .map((file) => file.replace(/^frontend\//, ""))
    .filter((file) => isScannableSource(file))
    .filter((file) => !excludedFiles.has(file))
    .filter((file) => excludedDirectories.every((directory) => !file.startsWith(directory)))
    .filter((path) => existsSync(path))
    .map((path) => ({ path, content: readFileSync(path, "utf8") }));
}

const syntheticSentinel = "synthetic private marker";
const syntheticFingerprint = fingerprintForSyntheticSentinel(syntheticSentinel);

test("detects raw synthetic marker fingerprints in JavaScript sources", () => {
  assert.deepEqual(
    scanSources([{ path: "temporary.js", content: `const value = "${syntheticSentinel}";` }], [syntheticFingerprint]),
    ["temporary.js: synthetic sentinel"],
  );
});

test("detects escaped and URL-encoded synthetic marker fingerprints", () => {
  const cases = [
    "synthetic\\u0020private\\x20marker",
    "synthetic%20private%20marker",
  ];
  for (const content of cases) {
    assert.deepEqual(findFingerprintCategories(content, [syntheticFingerprint]), ["synthetic sentinel"]);
  }
});

test("treats form-urlencoded plus signs as spaces", () => {
  assert.deepEqual(
    findFingerprintCategories("synthetic+private+marker", [syntheticFingerprint]),
    ["synthetic sentinel"],
  );
});

test("covers JavaScript and JSX source extensions", () => {
  const sources = [
    { path: "temporary.js", content: syntheticSentinel },
    { path: "temporary.jsx", content: syntheticSentinel },
  ];
  assert.deepEqual(scanSources(sources, [syntheticFingerprint]), [
    "temporary.js: synthetic sentinel",
    "temporary.jsx: synthetic sentinel",
  ]);
});

test("detects banned fingerprints in folded literal concatenations", () => {
  const content = 'const value = "synthetic " + ("private " + "marker");';
  assert.deepEqual(
    scanSources([{ path: "temporary.ts", content }], [syntheticFingerprint]),
    ["temporary.ts: synthetic sentinel"],
  );
});

test("detects banned fingerprints in folded template interpolations", () => {
  const content = 'const value = `synthetic ${"private"} marker`;';
  assert.deepEqual(
    scanSources([{ path: "temporary.ts", content }], [syntheticFingerprint]),
    ["temporary.ts: synthetic sentinel"],
  );
});

test("rejects common dynamic string assembly mechanisms", () => {
  const attempts = [
    "String.fromCharCode(115, 121, 110)",
    "String.fromCodePoint(115, 121, 110)",
    "atob(encodedValue)",
    "Buffer.from(encodedValue, \"base64\")",
    "\"synthetic-private\".split(\"-\").join(\" \" )",
    "[\"synthetic\", \"marker\"].join(\" \" )",
  ];
  for (const content of attempts) {
    assert.deepEqual(findDynamicAssemblyCategories(content), ["dynamic string assembly"]);
  }
});

test("accepts neutral synthetic content", () => {
  assert.deepEqual(
    scanSources([{ path: "temporary.jsx", content: "Compte local · /tmp/cortex-demo-workspace" }], [syntheticFingerprint]),
    [],
  );
});

test("accepts neutral constant string expressions", () => {
  const content = 'const label = "Compte " + "local"; const session = `Session ${"locale"}`;';
  assert.deepEqual(
    scanSources([{ path: "temporary.tsx", content }], [syntheticFingerprint]),
    [],
  );
});

test("committed frontend sources contain only privacy-safe synthetic data", () => {
  assert.deepEqual(scanSources(trackedFrontendSources(), bannedFingerprints), []);
});
