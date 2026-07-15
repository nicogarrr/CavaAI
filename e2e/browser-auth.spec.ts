import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

test.describe("public authentication shell", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("renders CavaAI sign-in, validates required fields and links to sign-up", async ({ page }) => {
    await page.goto("/sign-in");

    await expect(page).toHaveTitle(/CavaAI/);
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();

    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByText("Email is required")).toBeVisible();
    await expect(page.getByText("Password is required")).toBeVisible();

    await page.screenshot({ path: "test-results/cavaai-sign-in-validation.png", fullPage: true });
    await page.getByRole("link", { name: "Create an account" }).click();
    await expect(page).toHaveURL(/\/sign-up$/);
    await expect(page.getByRole("heading", { name: "Sign Up & Personalize" })).toBeVisible();
  });
});

test.describe("company research workspace", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("loads the compact snapshot and lazy-loads research modules", async ({ page }) => {
    await page.goto("/research/MSFT");

    await expect(page).toHaveURL(/\/research\/MSFT$/);
    await expect(page.getByRole("heading", { name: "MSFT", level: 1 })).toBeVisible();
    await expect(page.getByText("read-only snapshot")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Long-Term Fundamental Model" })).toBeVisible();

    await page.getByRole("link", { name: "Long-Term Model", exact: true }).click();
    await expect(page).toHaveURL(/view=model/);
    await expect(page.getByRole("heading", { name: "Long-Term Fundamental Model" })).toBeVisible();

    await page.getByRole("link", { name: "What Changed", exact: true }).click();
    await expect(page).toHaveURL(/view=changes/);
    await expect(page.getByRole("heading", { name: "Decision Journal" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Expectation vs Reality" })).toBeVisible();
    await page.screenshot({ path: "test-results/cavaai-company-workspace.png", fullPage: true });
  });
});
