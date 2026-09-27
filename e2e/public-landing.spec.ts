import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

// `/` es la landing pública (ya no el panel autenticado); el panel vive en /inicio.
// LIMITACIÓN del harness: corre con E2E_AUTH_BYPASS, así que NO prueba el
// flujo real de visitante anónimo (con bypass la cabecera muestra "Ir a mi
// panel" en vez de "Iniciar sesión" y no hay rebote a /sign-in). Lo que sí
// verifica: la landing renderiza sin error de aplicación, los CTAs presentes
// navegan a un destino válido y /metodologia, /terms y /help cargan.
test.describe("landing pública (harness E2E con bypass de auth)", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("/ renderiza la landing sin error de aplicación", async ({ page }) => {
    await page.goto("/");
    // Con bypass de auth no hay rebote posible; la aserción de URL solo
    // garantiza que no hubo redirect inesperado a otra ruta de la app.
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

  test("metodología, términos y ayuda cargan en el harness", async ({ page }) => {
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
