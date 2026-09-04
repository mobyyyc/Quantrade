import { defineConfig, devices } from "@playwright/test";
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { e2eDatabaseUrls } = require("./e2e/database-url.cjs") as {
  e2eDatabaseUrls: () => { testUrl: string };
};

const { testUrl } = e2eDatabaseUrls();

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm start --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      DATABASE_URL: testUrl,
      QUANTRADE_WORKSPACE_ROOT: process.env.QUANTRADE_WORKSPACE_ROOT ?? "../../",
    },
  },
});
