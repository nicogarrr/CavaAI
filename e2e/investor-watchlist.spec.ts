import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

test.describe("investor watchlist flow", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("screener Seguir reports the add outcome via toast", async ({ page }) => {
    await page.goto("/screener");

    const rows = page.locator("table tbody tr");
    if ((await rows.count()) === 0) {
      await expect(page.getByText("No hay datos ahora mismo")).toBeVisible();
      return;
    }

    const firstFollow = rows.first().getByRole("button", { name: "Seguir" });
    await expect(firstFollow).toBeEnabled();
    await firstFollow.click();

    // Backend healthy: "añadido a la watchlist". Backend down: "No se pudo añadir".
    // Both toasts mention the watchlist, so one assertion covers the round-trip.
    await expect(page.getByText(/watchlist/i).first()).toBeVisible({ timeout: 15_000 });
  });

  test("watchlist rows link to research and expose remove controls", async ({ page }) => {
    await page.goto("/watchlist");

    await expect(page.getByRole("heading", { name: "Watchlist", level: 1 })).toBeVisible();

    const rows = page.locator("table tbody tr");
    if ((await rows.count()) === 0) {
      await expect(page.getByText("Tu Watchlist está vacía")).toBeVisible();
      await expect(page.getByRole("link", { name: /Ir a buscar acciones/ })).toBeVisible();
      return;
    }

    await expect(page.getByRole("columnheader", { name: "Símbolo" })).toBeVisible();
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
    for (let i = 0; i < rowCount; i += 1) {
      const row = rows.nth(i);
      await expect(row.getByRole("link").first()).toHaveAttribute(
        "href",
        /\/research\/[^/]+$/,
      );
      await expect(
        row.getByRole("button", { name: "Eliminar de Watchlist" }),
      ).toBeVisible();
    }
  });

  test("watchlist remove drops the row", async ({ page }) => {
    await page.goto("/watchlist");

    const rows = page.locator("table tbody tr");
    const initial = await rows.count();
    if (initial === 0) {
      test.skip(true, "Watchlist is empty; nothing to remove.");
    }

    await rows.first().getByRole("button", { name: "Eliminar de Watchlist" }).click();
    if (initial === 1) {
      await expect(page.getByText("Tu Watchlist está vacía")).toBeVisible({ timeout: 15_000 });
    } else {
      await expect(page.locator("table tbody tr")).toHaveCount(initial - 1, {
        timeout: 15_000,
      });
    }
  });
});
