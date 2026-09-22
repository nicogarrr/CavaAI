import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

test.describe("public authentication shell", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("renders CavaAI sign-in, validates required fields and links to sign-up", async ({ page }) => {
    await page.goto("/sign-in");

    await expect(page).toHaveTitle(/CavaAI/);
    await expect(page.getByRole("heading", { name: "Bienvenido de nuevo" })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Contraseña")).toBeVisible();

    await page.getByRole("button", { name: "Iniciar sesión" }).click();
    await expect(page.getByText("El email es obligatorio")).toBeVisible();
    await expect(page.getByText("La contraseña es obligatoria")).toBeVisible();

    await page.screenshot({ path: "test-results/cavaai-sign-in-validation.png", fullPage: true });
    await page.getByRole("link", { name: "Crear cuenta" }).click();
    await expect(page).toHaveURL(/\/sign-up$/);
    await expect(page.getByRole("heading", { name: "Crea tu cuenta" })).toBeVisible();
  });
});


test.describe("mobile authentication layout", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("sign-in form is fully reachable at 390px without inner scroll traps", async ({ page }) => {
    await page.goto("/sign-in");

    // Regresión: .auth-layout usaba h-screen + overflow-hidden en móvil, lo que
    // comprimía el formulario en una tira de ~190px con scroll interno oculto
    // y dejaba el botón fuera del viewport.
    await expect(page.getByRole("heading", { name: "Bienvenido de nuevo" })).toBeInViewport();
    await expect(page.getByLabel("Email")).toBeInViewport();
    await expect(page.getByLabel("Contraseña")).toBeInViewport();
    await expect(page.getByRole("button", { name: "Iniciar sesión" })).toBeInViewport();

    // La página completa hace scroll normal en documento (no hay trampas internas).
    const metrics = await page.evaluate(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      innerHeight: window.innerHeight,
    }));
    expect(metrics.scrollHeight).toBeGreaterThan(metrics.innerHeight);
    await page.screenshot({ path: "test-results/cavaai-sign-in-mobile.png", fullPage: true });
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
