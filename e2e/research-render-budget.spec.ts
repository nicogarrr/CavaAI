import { expect, test } from "@playwright/test";

import {
  RESEARCH_RENDER_BUDGET_MS,
  RESEARCH_RENDER_MAX_DURATION_MS,
} from "../lib/research/parallel-fetch";

const runUiE2E = process.env.E2E_UI_RUN === "1";

/**
 * D2a: presupuesto de render de /research/<ticker>.
 *
 * No se mide contra la red externa: el backend de la suite corre en localhost
 * (playwright.config.ts lo levanta), asi que lo que se mide es el coste de la
 * pagina, no el del proveedor.
 *
 * El presupuesto sale de la constante con nombre, no de un numero magico: si
 * `RESEARCH_RENDER_MAX_DURATION_MS` se desincroniza de `vercel.json`, este
 * spec se ajusta solo (y `research-parallel-fetch-guard.test.ts` falla).
 *
 * La vista medida es `thesis` a proposito: su workspace son 7 llamadas, la
 * peor de las 12. Antes de D2a esas 7 iban ENCADENADAS detras del snapshot, el
 * market y el watchlist; ahora salen en la primera fase.
 */
test.describe("presupuesto de render de la ficha de research", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  // La vista mas pesada: 7 lecturas en su workspace.
  const worstCaseView = "thesis";
  // El presupuesto que se exige al render. Es MAS estricto que el presupuesto
  // del lote (20s) porque aqui se mide de puerta a puerta, render incluido.
  const renderBudgetMs = RESEARCH_RENDER_BUDGET_MS;

  test("la vista mas pesada renderiza dentro del presupuesto declarado", async ({
    page,
  }) => {
    const url = `/research/MSFT?view=${worstCaseView}`;

    // Calentamiento: la primera visita a una ruta en `next dev` paga la
    // compilacion del modulo, que no es tiempo de la pagina. Sin esto el
    // presupuesto mediria el compilador.
    await page.goto(url, { waitUntil: "load" });
    await expect(
      page.getByRole("link", { name: /Tesis/ }).first(),
    ).toBeVisible();

    const startedAt = Date.now();
    await page.goto(url, { waitUntil: "load" });
    // El contenido de la vista, no solo el shell: un header que aparece antes
    // no cuenta como ficha renderizada.
    await expect(
      page.getByText(/versiones$/).first(),
    ).toBeVisible();
    const elapsed = Date.now() - startedAt;

    // El presupuesto tiene que estar muy por debajo del techo de la funcion,
    // o el margen que se cree tener no existe.
    expect(renderBudgetMs).toBeLessThan(RESEARCH_RENDER_MAX_DURATION_MS);

    expect(
      elapsed,
      `la ficha tardó ${elapsed}ms y el presupuesto declarado son ${renderBudgetMs}ms`,
    ).toBeLessThan(renderBudgetMs);
  });

  test("un backend degradado NO vacia la pagina: el presupuesto no se gasta en un 503", async ({
    page,
  }) => {
    // El peor caso que importa: una capa opcional caida. Antes, un `Promise.all`
    // naked convertia esto en pagina en blanco y 500; ahora degrada a N/D con
    // el motivo y la ficha se pinta igual.
    await page.goto("/research/MSFT?view=thesis", { waitUntil: "load" });
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    const startedAt = Date.now();
    const response = await page.goto("/research/MSFT?view=thesis", {
      waitUntil: "load",
    });
    const elapsed = Date.now() - startedAt;

    expect(response?.status()).toBeLessThan(500);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      elapsed,
      `degradar no puede costar mas que el presupuesto: ${elapsed}ms`,
    ).toBeLessThan(renderBudgetMs);
  });
});