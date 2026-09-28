import { expect, test } from "@playwright/test";

// Quick win UX 2: los muros de metodología quedan colapsados en un
// desplegable nativo, cerrado por defecto, y se expanden al tocarlo.
test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

test("propicks abre con el contenido y la metodología colapsada", async ({ page }) => {
  await page.goto("/propicks");

  await expect(page.getByRole("heading", { name: "ProPicks IA", level: 1 })).toBeVisible();

  const wall = page.getByText(/El embudo v1 puntúa cada categoría/);
  await expect(wall).toBeHidden();

  await page.screenshot({ path: "test-results/methodology-collapsed.png" });

  await page.getByText("Metodología y límites").click();
  await expect(wall).toBeVisible();
  await page.screenshot({ path: "test-results/methodology-expanded.png" });
});
