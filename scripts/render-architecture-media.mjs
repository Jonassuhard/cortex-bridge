#!/usr/bin/env node

const args = process.argv.slice(2);
if (args.includes("--help") || args.length === 0) {
  process.stdout.write(`Usage: node scripts/render-architecture-media.mjs --url <loopback-url> --output <png> [--gif <gif>]\n\nRenders the in-app Info diagram with Playwright. If --gif is supplied, ffmpeg creates a synthetic still-frame GIF.\n`);
  process.exit(0);
}
const value = (flag) => args[args.indexOf(flag) + 1];
const url = value("--url");
const output = value("--output");
const gif = value("--gif");
if (!url || !output) throw new Error("--url and --output are required");
if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(url)) throw new Error("only loopback URLs are allowed");

const { chromium } = await import("../frontend/node_modules/playwright/index.mjs");
const { spawnSync } = await import("node:child_process");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Paramètres/ }).click();
  await page.getByRole("button", { name: "Info" }).click();
  await page.locator(".bridge-diagram").screenshot({ path: output });
} finally {
  await browser.close();
}
if (gif) {
  const result = spawnSync("ffmpeg", ["-y", "-loop", "1", "-i", output, "-t", "2", "-vf", "fps=12,scale=960:-1:flags=lanczos", gif], { stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status || 1);
}
