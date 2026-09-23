import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

function source(...parts: string[]): string {
  return readFileSync(resolve(process.cwd(), ...parts), "utf8");
}

test.describe("hardening frontend estático", () => {
  test("el layout raíz no envuelve páginas con otro landmark main", () => {
    const layout = source("app", "(root)", "layout.tsx");

    expect(layout).not.toContain("<main");
    expect(layout).toContain('<div className="min-h-screen text-gray-400">');
  });

  test("la pantalla de error no muestra el mensaje interno", () => {
    const errorBoundary = source("app", "(root)", "error.tsx");

    expect(errorBoundary).toContain('role="alert"');
    expect(errorBoundary).toContain("Se produjo un error inesperado");
    expect(errorBoundary).not.toMatch(/error\.message\s*\|\|/);
  });

  test("MutationForm y SelectField exponen estado pending y validación", () => {
    const mutationForm = source("components", "forms", "MutationForm.tsx");
    const selectField = source("components", "forms", "SelectField.tsx");

    expect(mutationForm).toContain("aria-busy={isPending}");
    expect(mutationForm).toContain("disabled={isPending}");
    expect(mutationForm).toContain('role="status"');
    expect(selectField).toContain("id={selectId}");
    expect(selectField).toContain("aria-required={required}");
    expect(selectField).toContain("aria-invalid={Boolean(error)}");
    expect(selectField).toContain("aria-describedby=");
  });

  test("los controles iconográficos y el fallo de búsqueda tienen semántica", () => {
    const mobileNav = source("components", "MobileNav.tsx");
    const searchCommand = source("components", "SearchCommand.tsx");
    const portfolioChat = source("components", "portfolio", "PortfolioChat.tsx");

    expect(mobileNav).toContain("closeButtonRef");
    expect(mobileNav).toContain("aria-labelledby=\"mobile-nav-title\"");
    expect(searchCommand).toContain("searchError");
    expect(searchCommand).toContain("No se pudo completar la búsqueda");
    expect(searchCommand).not.toMatch(/catch \(error: any\)[\s\S]*?setStocks\(\[\]\);[\s\S]*?\n\s*}/);
    expect(portfolioChat).toContain("Abrir asistente de cartera");
    expect(portfolioChat).toContain("aria-labelledby=\"portfolio-chat-title\"");
  });
});

test.describe("hardening frontend en navegador", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("las páginas raíz exponen un único main", async ({ page }) => {
    await page.goto("/alerts");
    await expect(page.locator("main")).toHaveCount(1);
  });

  test("el menú móvil abre, enfoca y restaura el foco", async ({ page }) => {
    const trigger = page.getByRole("button", { name: "Abrir menú de navegación" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Menú de navegación" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Cerrar menú de navegación" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("la ruta inexistente ofrece una recuperación accesible", async ({ page }) => {
    const response = await page.goto("/ruta-inexistente-cavaai");
    expect(response?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: "Página no encontrada", level: 1 })).toBeVisible();
    await expect(page.getByRole("link", { name: "Volver al inicio" })).toBeVisible();
  });
});
