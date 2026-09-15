import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { Client } from "pg";
import { authenticateTestOwner } from "./auth";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { e2eDatabaseUrls } = require("./database-url.cjs") as {
  e2eDatabaseUrls: () => { testUrl: string; testDatabaseName: string };
};

const appleId = "11111111-1111-4111-8111-111111111111";
const microsoftId = "22222222-2222-4222-8222-222222222222";
const withheldId = "90000000-0000-4000-8000-000000000003";

const longWatchlist = [
  { securityId: appleId, ticker: "AAPL", issuerName: "Apple Inc." },
  { securityId: microsoftId, ticker: "MSFT", issuerName: "Microsoft Corporation" },
  ...Array.from({ length: 18 }, (_, index) => {
    const number = index + 3;
    return {
      securityId: `90000000-0000-4000-8000-${String(number).padStart(12, "0")}`,
      ticker: `PX${String.fromCharCode(64 + number)}`,
      issuerName: `Portfolio Fixture ${number}`,
    };
  }),
];

async function expectAccessibleWithoutOverflow(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

async function expectMinimumTarget(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThanOrEqual(44);
  expect(box!.height).toBeGreaterThanOrEqual(44);
}

async function resetWatchlistRateWindow() {
  const { testUrl, testDatabaseName } = e2eDatabaseUrls();
  if (!testDatabaseName.endsWith("_e2e")) throw new Error("Refusing to alter a non-E2E rate window.");
  const database = new Client({ connectionString: testUrl });
  await database.connect();
  try {
    await database.query("DELETE FROM quantrade.web_rate_limit_windows WHERE scope = 'watchlist'");
  } finally {
    await database.end();
  }
}

test.beforeEach(async ({ page }) => authenticateTestOwner(page, { clearWatchlist: false }));

test("empty search and watchlist states remain useful on the narrowest viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/search?query=ZZZZ-NOT-A-COMPANY");
  await expect(page.getByRole("heading", { name: "0 matching companies" })).toBeVisible();
  await expect(page.getByText("No matching company was found in the current security master.")).toBeVisible();
  await expectAccessibleWithoutOverflow(page);

  await page.goto("/watchlist");
  await expect(page.getByRole("heading", { name: "Save companies worth returning to." })).toBeVisible();
  await expectAccessibleWithoutOverflow(page);
});

test("partial coverage explains the withheld company instead of silently dropping it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/rankings");
  await expect(page.locator(".ranking-coverage")).toContainText("2of 3 eligible");
  await expect(page.getByText("1 name", { exact: true })).toBeVisible();
  await expectMinimumTarget(page.getByLabel("Score date"));
  await expectMinimumTarget(page.getByRole("button", { name: "View date" }));
  await expectAccessibleWithoutOverflow(page);

  await page.goto(`/stocks/${withheldId}`);
  await expect(page.getByRole("heading", { name: "A score is not available for this run." })).toBeVisible();
  await expect(page.getByText("The required price-history window has not accumulated yet.")).toBeVisible();
  await expectAccessibleWithoutOverflow(page);
});

test("stale data and a failed refresh communicate safe next actions", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("New market data awaits scores", { exact: true })).toBeVisible();

  await page.route("**/api/v1/operations/daily-update", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "SEC filing validation is not ready. Retry after 10:00 p.m. Toronto time." }),
    });
  });
  const button = page.getByRole("button", { name: "Run daily update" });
  await button.click();
  await expect(page.locator(".daily-update-message[role='alert']")).toHaveText("SEC filing validation is not ready. Retry after 10:00 p.m. Toronto time.");
  await expect(button).toBeEnabled();
  await expectAccessibleWithoutOverflow(page);
});

test("month-end history distinguishes completed and missed formations on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/portfolio");
  await expect(page.locator(".portfolio-holdings-list > li")).toHaveCount(20);

  const completed = page.getByRole("listitem", { name: /gross basket return \+8\.00%/i });
  await expect(completed.locator("[data-label='Gross basket']")).toHaveText("+8.00%");
  const missed = page.getByRole("listitem", { name: /Basket not formed/ });
  await expect(missed.locator("[data-label='Status']")).toHaveText("Basket not formed");
  await expectAccessibleWithoutOverflow(page);
});

test("a long mixed-state watchlist is scrollable, keyboard reachable, and stable", async ({ page }) => {
  await resetWatchlistRateWindow();
  const response = await page.request.put("/api/v1/watchlist", {
    data: { entries: longWatchlist },
    headers: { Origin: "http://127.0.0.1:3100" },
  });
  expect(response.ok()).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/watchlist");
  await expect(page.getByText("20 saved")).toBeVisible();
  await expect(page.locator(".watchlist-list > li")).toHaveCount(20);
  await expect(page.getByText("Price unavailable").first()).toBeVisible();
  await expect(page.getByText("No score published").first()).toBeVisible();
  await expectMinimumTarget(page.getByRole("button", { name: "Score" }));
  await expectMinimumTarget(page.locator(".row-menu summary").first());

  const region = page.getByRole("region", { name: "Saved companies. Scroll to see more." });
  await region.focus();
  await expect(region).toBeFocused();
  expect(await region.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await region.press("End");
  await expect(page.locator(".watchlist-scroll-frame")).toHaveClass(/has-top-fade/);
  await expectAccessibleWithoutOverflow(page);
});
