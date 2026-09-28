import { expect, test } from "@playwright/test";

// Quick win UX 4: la ficha y las tarjetas de research leen sector/industria
// en español (nunca «Information Technology» cruda). Capturas para el OK
// visual; el titular SEC español lo cubre test_sec_connector_title_es.py
// (el conector no es alcanzable desde el stack de navegador).
test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

test("cabecera de la ficha sin sector en inglés", async ({ page }) => {
  await page.goto("/research/MSFT");

  await expect(page.getByRole("heading", { name: "MSFT", level: 1 })).toBeVisible();
  await expect(page.getByText("Information Technology")).toHaveCount(0);
  await page.screenshot({ path: "test-results/news-es-ficha-header.png" });
});

test("tarjetas de /research sin sector en inglés", async ({ page }) => {
  await page.goto("/research");

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Information Technology")).toHaveCount(0);
  await page.screenshot({ path: "test-results/news-es-research-cards.png" });
});
