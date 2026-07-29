#!/usr/bin/env node

import { mkdirSync, mkdtempSync, renameSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

const args = process.argv.slice(2);
if (args.includes("--help") || args.length === 0) {
  process.stdout.write(`Usage: node scripts/render-architecture-media.mjs --url <loopback-url> --output <png> [--gif <gif>] [--frames <count>]\n\nRenders the shared in-app Info diagram. Playwright is used only as the rendering test tool; the diagram describes the Chrome extension product flow.\n`);
  process.exit(0);
}
const value = (flag) => args[args.indexOf(flag) + 1];
const url = value("--url");
const output = value("--output");
const gif = value("--gif");
const frameCount = Number(value("--frames") || 24);
if (!url || !output) throw new Error("--url and --output are required");
if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(url)) throw new Error("only loopback URLs are allowed");
if (!Number.isInteger(frameCount) || frameCount < 2 || frameCount > 120) throw new Error("--frames must be an integer between 2 and 120");

const { chromium } = await import("../frontend/node_modules/playwright/index.mjs");
const { spawnSync } = await import("node:child_process");
mkdirSync(dirname(output), { recursive: true });
if (gif) mkdirSync(dirname(gif), { recursive: true });

async function openDiagram(browser, reducedMotion) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion, colorScheme: "dark" });
  await page.route("**/*", async (route) => {
    const requestUrl = new URL(route.request().url());
    if (!new Set(["127.0.0.1", "localhost"]).has(requestUrl.hostname)) {
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.locator(".settings-entry").click();
  await page.getByRole("button", { name: "Info", exact: true }).click();
  const diagram = page.locator(".bridge-diagram");
  await diagram.waitFor({ state: "visible" });
  return { page, diagram };
}

const browser = await chromium.launch({ headless: true });
const framesDirectory = gif ? mkdtempSync(join(tmpdir(), "cortex-architecture-")) : null;
try {
  const reduced = await openDiagram(browser, "reduce");
  const animationNames = await reduced.page.locator(".bridge-diagram .bd-pulse").evaluateAll((elements) => elements.map((element) => getComputedStyle(element).animationName));
  if (animationNames.some((name) => name !== "none")) throw new Error(`reduced-motion verification failed: ${animationNames.join(",")}`);
  await reduced.diagram.screenshot({ path: output, animations: "disabled" });
  await reduced.page.close();

  if (gif && framesDirectory) {
    const animated = await openDiagram(browser, "no-preference");
    for (let index = 0; index < frameCount; index += 1) {
      const frame = join(framesDirectory, `frame-${String(index).padStart(3, "0")}.png`);
      await animated.diagram.screenshot({ path: frame });
      await animated.page.waitForTimeout(80);
    }
    await animated.page.close();
  }
} finally {
  await browser.close();
}

if (gif && framesDirectory) {
  const result = spawnSync("ffmpeg", [
    "-y", "-framerate", "10", "-i", join(framesDirectory, "frame-%03d.png"),
    "-filter_complex", "[0:v]fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3",
    "-loop", "0", "-map_metadata", "-1", gif,
  ], { stdio: "inherit" });
  rmSync(framesDirectory, { recursive: true, force: true });
  if (result.status !== 0) process.exit(result.status || 1);
}

const stripped = `${output}.stripped.png`;
const strip = spawnSync("ffmpeg", ["-y", "-i", output, "-map_metadata", "-1", "-frames:v", "1", stripped], { stdio: "ignore" });
if (strip.status !== 0) process.exit(strip.status || 1);
renameSync(stripped, output);
