import { expect, test } from "@playwright/test";
import { authenticateTestOwner } from "./auth";

const appleId = "11111111-1111-4111-8111-111111111111";
const microsoftId = "22222222-2222-4222-8222-222222222222";

test.beforeEach(async ({ page }, testInfo) => {
  if (testInfo.title === "unauthenticated pages redirect and APIs fail closed") return;
  await authenticateTestOwner(page);
});

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
  await expect(page.getByLabel("Supports the score").getByText("12–1 month momentum")).toBeVisible();
  const inputSummary = page.getByLabel("Model input summary");
  await expect(inputSummary.locator("dd").nth(0)).toContainText("2");
  await expect(inputSummary.locator("dd").nth(1)).toContainText("3");
  await expect(inputSummary.locator("dd").nth(2)).toContainText("2");
  await expect(inputSummary.locator("dd").nth(3)).toContainText("3");
  await page.getByText("View all 3 registered model inputs").click();
  await expect(page.getByText("Zero weight · does not affect score")).toBeVisible();

  const scoreResponse = await page.request.get(`/api/v1/scores/${appleId}?date=2026-08-25`);
  expect(scoreResponse.ok()).toBeTruthy();
  const scorePayload = await scoreResponse.json();
  expect(scorePayload.score.rank).toBe(1);
  expect(scorePayload.explanations).toHaveLength(2);
  expect(scorePayload.modelCard.modelVersion).toBe("tier_b_monthly_elastic_net_sec_clean_v3");
  expect(scorePayload.modelCard.inputs.map((input: { active: boolean }) => input.active)).toEqual([true, true, false]);
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

test("research exposes immutable model health and integrity lineage", async ({ page }) => {
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "Healthy for Aug 25, 2026." })).toBeVisible();
  await expect(page.getByText("Artifact hash Verified")).toBeVisible();
  await expect(page.getByText("Registry hash Verified")).toBeVisible();
  await expect(page.getByText("Explanation lineage Verified")).toBeVisible();
  await expect(page.getByText("Forward readiness Recorded")).toBeVisible();
  await page.getByText("View active-feature health").click();
  await expect(page.getByText("PSI 0.040")).toBeVisible();

  const response = await page.request.get("/api/v1/model-health");
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.health.status).toBe("healthy");
  expect(payload.health.features).toHaveLength(2);
  expect(payload.health.logicalSha256).toHaveLength(64);
});

test("watchlist persists saved companies and displays live score and price context", async ({ page }) => {
  await page.goto(`/stocks/${appleId}`);
  await page.getByRole("button", { name: "Save to watchlist" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toHaveAttribute("aria-pressed", "true");

  await page.goto(`/stocks/${microsoftId}`);
  await page.getByRole("button", { name: "Save to watchlist" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toHaveAttribute("aria-pressed", "true");

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

test("daily update partial completion remains retryable without claiming full success", async ({ page }) => {
  let attempts = 0;
  await page.route("**/api/v1/operations/daily-update", async (route) => {
    attempts += 1;
    const partial = attempts === 1;
    const events = [
      { type: "progress", progress: { contract: "daily_update_progress_v1", stage: "completion",
        status: partial ? "warning" : "completed", message: partial ? "Maintenance pending." : "Maintenance complete." } },
      { type: "complete", outcome: partial ? "partial" : "complete",
        message: partial ? "Scores are ready. Retry maintenance without recalculating scores." : "Maintenance completed. No scores were recalculated.",
        result: { scoreDate: "2026-08-25", eligibleCount: 2, totalCount: 2 } },
    ];
    await route.fulfill({ status: 200, contentType: "application/x-ndjson",
      body: events.map((event) => JSON.stringify(event)).join("\n") + "\n" });
  });
  await page.goto("/");
  const button = page.getByRole("button", { name: "Run daily update" });
  await button.click();
  await expect(page.getByText("SCORES READY · MAINTENANCE PENDING", { exact: true })).toBeVisible();
  await expect(page.getByText("DAILY UPDATE COMPLETE", { exact: true })).toHaveCount(0);
  const retryButton = page.getByRole("button", { name: "Retry maintenance" });
  await expect(retryButton).toBeEnabled();
  await retryButton.click();
  await expect(page.getByText("DAILY UPDATE COMPLETE", { exact: true })).toBeVisible();
  await expect(page.getByText("Maintenance completed. No scores were recalculated.", { exact: true })).toBeVisible();
  expect(attempts).toBe(2);
});

test("daily update control renders streamed progress and completion safely", async ({ page }) => {
  await page.route("**/api/v1/operations/daily-update", async (route) => {
    expect(route.request().method()).toBe("POST");
    const events = [
      { type: "progress", progress: { stage: "market_data", message: "Current prices validated." } },
      { type: "progress", progress: { stage: "scoring", message: "Eligible scores calculated." } },
      {
        type: "complete",
        outcome: "complete",
        message: "Daily update completed.",
        result: { scoreDate: "2026-08-25", eligibleCount: 2, totalCount: 2 },
      },
    ].map((event) => JSON.stringify(event)).join("\n") + "\n";
    await route.fulfill({ status: 200, contentType: "application/x-ndjson", body: events });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Run daily update" }).click();
  await expect(page.getByRole("heading", { name: "Research for Aug 25, 2026 is ready." })).toBeVisible();
  await expect(page.getByRole("paragraph").filter({ hasText: /^Daily update completed\.$/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Review rankings" })).toHaveAttribute("href", "/rankings?date=2026-08-25");
});

test("daily update distinguishes skipped and duplicate-prevented outcomes", async ({ page }) => {
  let attempts = 0;
  await page.route("**/api/v1/operations/daily-update", async (route) => {
    attempts += 1;
    const event = attempts === 1
      ? { type: "complete", outcome: "skipped", message: "No regular market session was available, so no dated publication was created." }
      : { type: "complete", outcome: "duplicate_prevented", message: "Today’s scores already exist and maintenance is complete. Nothing was recalculated or duplicated.", result: { scoreDate: "2026-08-25", eligibleCount: 2, totalCount: 2 } };
    await route.fulfill({ status: 200, contentType: "application/x-ndjson", body: `${JSON.stringify(event)}\n` });
  });
  await page.goto("/");
  const button = page.getByRole("button", { name: "Run daily update" });
  await button.click();
  await expect(page.getByText("UPDATE SKIPPED", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No publication was needed." })).toBeVisible();
  await button.click();
  await expect(page.getByText("DUPLICATE PREVENTED", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Nothing was duplicated." })).toBeVisible();
});

test("research history preserves every operational state", async ({ page }) => {
  await page.goto("/research");
  const history = page.locator("ol.operations-history-list");
  for (const label of ["Complete", "Retrying provider", "Needs attention", "Scores ready, maintenance pending", "No market session", "Duplicate prevented", "In progress"]) {
    await expect(history.getByText(label, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText("provider detail must remain private", { exact: false })).toHaveCount(0);
  await expect(page.getByText("SEC filing retrieval or validation did not complete. The update stopped safely before publication; no duplicate scores were created.", { exact: true })).toBeVisible();
  await expect(page.getByText("Newer market data is awaiting publication", { exact: true })).toBeVisible();
  await expect(page.getByText(/10:15 PM Toronto$/)).toBeVisible();
});

test("official portfolio shows immutable holdings and completed history", async ({ page }) => {
  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: "Official basket active." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recorded formation weights" })).toBeVisible();
  await expect(page.getByRole("link", { name: /AAPL, formation rank 2, score 78 out of 100/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /MSFT, formation rank 1, score 81 out of 100/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Monthly formation record" })).toBeVisible();
  await expect(page.getByRole("listitem", { name: /gross basket return \+8\.00%.*gross SPY return \+3\.00%.*estimated net difference \+4\.75 pp/i })).toBeVisible();
  await expect(page.getByRole("listitem", { name: /Jun 30, 2026 formation, Basket not formed.*Month-end score unavailable/i })).toBeVisible();
});

test("unauthenticated pages redirect and APIs fail closed", async ({ page }) => {
  await page.context().clearCookies();
  const apiResponse = await page.request.get("/api/v1/prices?securityIds=11111111-1111-4111-8111-111111111111");
  expect(apiResponse.status()).toBe(401);
  const healthResponse = await page.request.get("/api/v1/model-health");
  expect(healthResponse.status()).toBe(401);
  await page.goto("/rankings");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Frankings$/);
  await expect(page.getByRole("heading", { name: "Welcome back." })).toBeVisible();
});
