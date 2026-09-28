import { expect, test } from "@playwright/test";

// Quick win UX 3: nav limpio. El drawer comparte NAV_SECTIONS con el
// sidebar de escritorio: una sola entrada por destino, sin Workflows,
// «Mercado» en vez de «Vista de mercado» y sin «Mi plan» duplicado.
test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

test.use({ viewport: { width: 700, height: 900 } });

test("el menú ya no tiene duplicados ni Workflows", async ({ page }) => {
  await page.goto("/inicio");
  const trigger = page.getByRole("button", { name: "Abrir menú de navegación" });
  await expect(trigger).toBeVisible();
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Menú de navegación" });
  await expect(dialog).toBeVisible();

  await expect(dialog.getByRole("link", { name: "Mercado", exact: true })).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Vista de mercado", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("link", { name: "Workflows", exact: true })).toHaveCount(0);

  // Una sola entrada para el plan y una para ayuda.
  await expect(dialog.getByRole("link", { name: "Plan", exact: true })).toHaveCount(1);
  await expect(dialog.getByRole("link", { name: "Ayuda", exact: true })).toHaveCount(1);
  await expect(dialog.getByText("Mi plan", { exact: true })).toHaveCount(0);

  await page.screenshot({ path: "test-results/nav-cleanup-drawer.png" });
});
