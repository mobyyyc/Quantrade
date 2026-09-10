import { expect, type Page } from "@playwright/test";

const email = "owner@quantrade.test";
const password = "Quantrade-E2E-Owner-2026";

export async function authenticateTestOwner(page: Page) {
  await page.goto("/sign-in");
  const setup = await page.getByRole("heading", { name: "Secure this workspace." }).isVisible().catch(() => false);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: setup ? "Create owner account" : "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);
  const cleared = await page.request.put("/api/v1/watchlist", {
    data: { entries: [] }, headers: { Origin: "http://127.0.0.1:3100" },
  });
  expect(cleared.ok()).toBe(true);
}
