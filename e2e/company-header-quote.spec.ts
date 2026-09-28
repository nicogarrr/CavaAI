import { expect, test } from "@playwright/test";

// Quick win UX 1: la cabecera de la ficha muestra precio + variación +
// sparkline con el fixture E2E determinista, en desktop y móvil, y las
// capturas quedan en test-results como prueba píxel a píxel.
test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

test("cabecera de la ficha con precio, variación y sparkline (desktop)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/research/MSFT");

  await expect(page.getByRole("heading", { name: "MSFT", level: 1 })).toBeVisible();
  await expect(page.getByText("336,56 US$")).toBeVisible();
  await expect(page.getByText("+2,34")).toBeVisible();
  await expect(page.getByRole("img", { name: /Evolución del precio/ })).toBeVisible();
  await page.screenshot({ path: "test-results/header-quote-desktop.png" });
});

test("cabecera de la ficha con precio, variación y sparkline (móvil)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/research/MSFT");

  await expect(page.getByRole("heading", { name: "MSFT", level: 1 })).toBeVisible();
  await expect(page.getByText("336,56 US$")).toBeVisible();
  await expect(page.getByText("+0,70 %")).toBeVisible();
  await expect(page.getByRole("img", { name: /Evolución del precio/ })).toBeVisible();
  await page.screenshot({ path: "test-results/header-quote-mobile.png" });
});

test("otras vistas también llevan la cotización en cabecera", async ({ page }) => {
  await page.goto("/research/MSFT?view=thesis");

  await expect(page.getByRole("heading", { name: "MSFT", level: 1 })).toBeVisible();
  await expect(page.getByText("336,56 US$")).toBeVisible();
});
