import type { NextConfig } from "next";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function loadCanonicalDatabaseUrl() {
  if (process.env.DATABASE_URL) return;
  const workspaceRoot = process.env.QUANTRADE_WORKSPACE_ROOT
    ? resolve(process.env.QUANTRADE_WORKSPACE_ROOT)
    : resolve(process.cwd(), "../..");
  try {
    const line = readFileSync(resolve(workspaceRoot, ".env"), "utf8")
      .split(/\r?\n/)
      .find((entry) => entry.startsWith("DATABASE_URL="));
    const value = line?.slice("DATABASE_URL=".length).trim().replace(/^['"]|['"]$/g, "");
    if (value) process.env.DATABASE_URL = value;
  } catch {
    // Database-backed routes return a controlled 503 when no runtime value exists.
  }
}

loadCanonicalDatabaseUrl();

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
