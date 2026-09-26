import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

// Visitante anonimo REAL: corre contra la instancia de playwright.config que
// NO lleva E2E_AUTH_BYPASS ni APP_ENV=test, asi que require-user.ts no deja
// pasar a nadie y la auth real decide, como en produccion. (Sigue siendo
// `next dev`; el build de produccion se valida en el job de frontend de CI.)
test.use({ baseURL: process.env.E2E_ANON_UI_URL ?? "http://127.0.0.1:3101" });

test.describe("landing pública sin bypass de auth (anónimo real)", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("/ renderiza la landing con CTA de acceso, no un muro de sesión", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /tesis trazables/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Iniciar sesión" }).first(),
    ).toBeVisible();
  });

  test("/dashboard exige sesión: un anónimo termina en /sign-in", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/sign-in/);
  });

  test("/sign-in y /sign-up cargan para el anónimo", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(
      page.getByText(/Application error|Something went wrong/i),
    ).toHaveCount(0);
    expect(page.url()).toContain("/sign-in");
  });
});
