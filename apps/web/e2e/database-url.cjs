/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require("node:fs");
const path = require("node:path");

const TEST_DATABASE_NAME = "quantrade_e2e";

function envFileDatabaseUrl() {
  const envPath = path.join(process.cwd(), ".env.local");
  if (!fs.existsSync(envPath)) return undefined;
  const line = fs.readFileSync(envPath, "utf8")
    .split(/\r?\n/)
    .find((entry) => entry.startsWith("DATABASE_URL="));
  return line?.slice("DATABASE_URL=".length).trim().replace(/^['"]|['"]$/g, "");
}

function e2eDatabaseUrls() {
  const configured = process.env.QUANTRADE_E2E_ADMIN_DATABASE_URL ?? envFileDatabaseUrl();
  if (!configured) {
    throw new Error("Set QUANTRADE_E2E_ADMIN_DATABASE_URL or DATABASE_URL in apps/web/.env.local before running E2E tests.");
  }
  const admin = new URL(configured);
  if (!process.env.QUANTRADE_E2E_ADMIN_DATABASE_URL && !["localhost", "127.0.0.1"].includes(admin.hostname)) {
    throw new Error("The implicit E2E database administrator must be local. Set QUANTRADE_E2E_ADMIN_DATABASE_URL explicitly for another host.");
  }
  const test = new URL(admin);
  test.pathname = `/${TEST_DATABASE_NAME}`;
  return { adminUrl: admin.toString(), testUrl: test.toString(), testDatabaseName: TEST_DATABASE_NAME };
}

module.exports = { e2eDatabaseUrls };
