import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

// Visitante anónimo: `/` es la landing pública (ya no el panel autenticado),
// y las rutas legales/ayuda cargan sin sesión. El panel vive en /inicio.
// En el harness UI el bypass E2E de auth hace que la cabecera muestre
// "Ir a mi panel" en lugar de "Iniciar sesión"; ambos CTAs son válidos.
test.describe("landing pública (visitante anónimo)", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("/ renderiza la landing y no rebota a /sign-in", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /tesis trazables/i }),
    ).toBeVisible();
    await expect(
      page.getByText(/Application error|Something went wrong/i),
    ).toHaveCount(0);
  });

  test("los CTAs públicos están presentes y el de cabecera navega", async ({ page }) => {
    await page.goto("/");
    const cta = page
      .getByRole("link", { name: "Ir a mi panel" })
      .or(page.getByRole("link", { name: "Iniciar sesión" }))
      .first();
    await expect(cta).toBeVisible();
    await cta.click();
    // Con sesión (o bypass E2E) -> panel; sin sesión -> formulario de acceso.
    await expect(page).toHaveURL(/\/(inicio|sign-in)/);
  });

  test("metodología, términos y ayuda cargan sin sesión", async ({ page }) => {
    for (const path of ["/metodologia", "/terms", "/help"]) {
      await page.goto(path);
      await expect(page.getByRole("heading").first()).toBeVisible();
      await expect(
        page.getByText(/Application error|Something went wrong/i),
      ).toHaveCount(0);
      expect(page.url()).toContain(path);
    }
  });

  test("los enlaces del footer público apuntan a rutas existentes", async ({ page }) => {
    await page.goto("/");
    for (const name of ["Términos", "Metodología"]) {
      const link = page.getByRole("link", { name }).first();
      await expect(link).toBeVisible();
    }
  });
});
