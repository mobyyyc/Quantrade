import { expect, test } from "@playwright/test";

const appleId = "11111111-1111-4111-8111-111111111111";
const microsoftId = "22222222-2222-4222-8222-222222222222";

test("global search finds a company and opens its research detail", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Control+k");
  const search = page.getByRole("searchbox", { name: /Search companies/ });
  await expect(search).toBeFocused();
  await search.fill("Apple");
  await search.press("Enter");

  await expect(page).toHaveURL(/\/search\?query=Apple/);
  await expect(page.getByRole("heading", { name: "1 matching companies" })).toBeVisible();
  await page.getByRole("link", { name: /AAPL Apple Inc\./ }).click();

  await expect(page).toHaveURL(new RegExp(`/stocks/${appleId}`));
  await expect(page.getByRole("heading", { name: /AAPL.*Apple Inc\./ })).toBeVisible();
  await expect(page.getByLabel("Research and price context").getByText("84/100")).toBeVisible();
  await expect(page.getByRole("heading", { name: "What influenced it" })).toBeVisible();
  await expect(page.getByText("12–1 month momentum")).toBeVisible();
});

test("rankings expose dated scores and link to stock evidence", async ({ page }) => {
  await page.goto("/rankings");
  await expect(page.getByRole("heading", { name: "Highest scores" })).toBeVisible();
  await expect(page.getByText("2", { exact: true }).first()).toBeVisible();

  const apple = page.getByRole("link", { name: /AAPL.*score 84/i }).first();
  await expect(apple).toBeVisible();
  await apple.click();
  await expect(page).toHaveURL(new RegExp(`/stocks/${appleId}.*from=rankings`));
  await expect(page.getByRole("link", { name: /Rankings/ }).first()).toBeVisible();
});

test("watchlist persists saved companies and displays live score and price context", async ({ page }) => {
  await page.goto(`/stocks/${appleId}`);
  await page.getByRole("button", { name: "Save to watchlist" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toHaveAttribute("aria-pressed", "true");

  await page.goto(`/stocks/${microsoftId}`);
  await page.getByRole("button", { name: "Save to watchlist" }).click();

  await page.goto("/");
  const preview = page.locator("section.watchlist-preview");
  await expect(preview.getByRole("link", { name: /AAPL Apple Inc\./ })).toBeVisible();
  await expect(preview.getByText("$228.00")).toBeVisible();
  await expect(preview.getByText("84/100")).toBeVisible();

  await page.goto("/watchlist");

  await expect(page.getByText("2 saved")).toBeVisible();
  await expect(page.getByRole("link", { name: /AAPL Apple Inc\./ })).toBeVisible();
  await expect(page.getByRole("link", { name: /MSFT Microsoft Corporation/ })).toBeVisible();
  await expect(page.getByText("$228.00")).toBeVisible();
  await expect(page.getByText("84/100")).toBeVisible();
});

test("daily update control renders streamed progress and completion safely", async ({ page }) => {
  await page.route("**/api/v1/operations/daily-update", async (route) => {
    expect(route.request().method()).toBe("POST");
    const events = [
      { type: "progress", progress: { stage: "market_data", message: "Current prices validated." } },
      { type: "progress", progress: { stage: "scoring", message: "Eligible scores calculated." } },
      {
        type: "complete",
        message: "Daily update completed.",
        result: { scoreDate: "2026-08-25", eligibleCount: 2, totalCount: 2 },
      },
    ].map((event) => JSON.stringify(event)).join("\n") + "\n";
    await route.fulfill({ status: 200, contentType: "application/x-ndjson", body: events });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Run daily update" }).click();
  await expect(page.getByRole("heading", { name: "Research for Aug 25, 2026 is ready." })).toBeVisible();
  await expect(page.getByText("Daily update completed.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Review rankings" })).toHaveAttribute("href", "/rankings?date=2026-08-25");
});

test("official portfolio shows immutable holdings and completed history", async ({ page }) => {
  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: "Official basket active." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recorded formation weights" })).toBeVisible();
  await expect(page.getByRole("link", { name: /AAPL, formation rank 2, score 78 out of 100/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /MSFT, formation rank 1, score 81 out of 100/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Official 20-session results" })).toBeVisible();
  await expect(page.getByRole("listitem", { name: /basket return \+8\.00%.*SPY return \+3\.00%.*difference \+5\.00 pp/i })).toBeVisible();
});
