import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: { root },
  generateBuildId: async () => "cortex-bridge-v0.5.0",
};

export default nextConfig;
