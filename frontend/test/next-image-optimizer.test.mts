import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { getSharp, optimizeImage } = require(
  "next/dist/server/image-optimizer.js",
) as typeof import("next/dist/server/image-optimizer.js");

const inputWidth = 64;
const inputHeight = 48;
const outputWidth = 24;

test("Next image optimizer uses the reviewed Sharp release across formats", async (t) => {
  const sharp = getSharp(null);
  assert.equal(
    sharp.versions.sharp,
    "0.35.0",
    "Next must resolve the Sharp release that fixes GHSA-f88m-g3jw-g9cj",
  );

  const pixels = Buffer.alloc(inputWidth * inputHeight * 3);
  for (let index = 0; index < pixels.length; index += 3) {
    pixels[index] = (index / 3) % 256;
    pixels[index + 1] = 128;
    pixels[index + 2] = 255 - pixels[index];
  }

  const cases = [
    { input: "png", output: "webp", contentType: "image/webp" },
    { input: "jpeg", output: "png", contentType: "image/png" },
    { input: "webp", output: "jpeg", contentType: "image/jpeg" },
  ] as const;

  for (const imageCase of cases) {
    await t.test(`${imageCase.input} to ${imageCase.output}`, async () => {
      const source = await sharp(pixels, {
        raw: { width: inputWidth, height: inputHeight, channels: 3 },
      })[imageCase.input]().toBuffer();

      const optimized = await optimizeImage({
        buffer: source,
        contentType: imageCase.contentType,
        quality: 72,
        width: outputWidth,
        concurrency: null,
        limitInputPixels: inputWidth * inputHeight,
        sequentialRead: true,
        timeoutInSeconds: 5,
      });
      const metadata = await sharp(optimized).metadata();

      assert.equal(metadata.format, imageCase.output);
      assert.equal(metadata.width, outputWidth);
      assert.equal(metadata.height, 18);
    });
  }
});
