import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { authenticateTestOwner } from "./auth";

const appleId = "11111111-1111-4111-8111-111111111111";

test.beforeEach(async ({ page }) => authenticateTestOwner(page));

for (const width of [1280, 390, 320]) {
  test(`core routes pass automated accessibility checks at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((securityId) => {
      localStorage.setItem("quantrade.watchlist.v2", JSON.stringify([{ securityId, ticker: "AAPL", issuerName: "Apple Inc.", note: "", tags: [] }]));
    }, appleId);
    for (const route of ["/", "/rankings", "/watchlist", "/portfolio", "/research", "/search?query=Apple", `/stocks/${appleId}`]) {
      await page.goto(route);
      if (route === "/watchlist") await expect(page.getByText("1 saved")).toBeVisible();
      if (route === "/") await expect(page.locator(".watchlist-preview").getByText("$228.00")).toBeVisible();
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      expect(results.violations, `${width}px ${route}: ${JSON.stringify(results.violations.map(({ id, nodes }) => ({ id, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) })))}`).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `Horizontal overflow: ${route}`).toBe(true);
    }
  });
}

test("skip link and chart support keyboard access with a complete table alternative", async ({ page }, testInfo) => {
  await page.goto(`/stocks/${appleId}`);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  const chart = page.getByRole("img", { name: /AAPL moved from/ });
  await chart.focus();
  await chart.press("Home");
  await expect(page.locator(".price-chart-tooltip")).toContainText("$225.00");
  await chart.press("End");
  await expect(page.locator(".price-chart-tooltip")).toContainText("$228.00");
  const summary = page.getByText("View price history as a table", { exact: true });
  await summary.focus();
  await page.keyboard.press("Enter");
  const table = page.getByRole("table", { name: "AAPL daily closing prices in USD" });
  await expect(table.getByRole("cell", { name: "$225.00" })).toBeVisible();
  await expect(table.getByRole("cell", { name: "$228.00" })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.locator(".price-panel").screenshot({ path: testInfo.outputPath("price-history-accessible.png") });
});

test("mobile navigation contains focus, closes with Escape, and restores the trigger", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Open navigation" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Primary navigation" });
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 10; i++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("mobile-navigation.png") });
  await dialog.getByRole("button", { name: "Close navigation" }).focus();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("link", { name: "Research" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await dialog.getByRole("link", { name: "Rankings" }).click();
  await expect(page).toHaveURL(/\/rankings/);
  await expect(dialog).not.toBeVisible();
});

test("ranked links remain keyboard reachable and reduced motion disables smooth scrolling", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const region = page.getByRole("region", { name: /Ranked research candidates/ });
  await region.focus();
  const links = region.getByRole("link");
  await expect(links).toHaveCount(2);
  for (let index = 0; index < await links.count(); index++) {
    await page.keyboard.press("Tab");
    await expect(links.nth(index)).toBeFocused();
    expect(await links.nth(index).evaluate((element) => getComputedStyle(element).outlineStyle)).toBe("solid");
  }
  expect(await region.evaluate((element) => getComputedStyle(element).scrollBehavior)).toBe("auto");
});
