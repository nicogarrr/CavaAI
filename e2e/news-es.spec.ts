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

// Procedencia: un titular SEC generado por CavaAI (headline_from_source=false)
// no repite el ticker como prefijo — la UI muestra el título recortado y la
// API expone el flag que lo gobierna.
test("titular sintético SEC sin prefijo de ticker duplicado", async ({ page, request }) => {
  const url = `https://www.sec.gov/Archives/edgar/data/320193/e2e-strip-${Date.now()}.htm`;
  const ingestion = await request.post("/api/news/ingest", {
    data: {
      source: "sec_filing",
      items: [
        {
          ticker: "E2ESEC",
          title: "E2ESEC 8-K presentado ante la SEC (strip e2e)",
          summary: "E2ESEC 8-K presentado ante la SEC (strip e2e)",
          url,
          headline_from_source: false,
        },
      ],
    },
  });
  expect(ingestion.ok()).toBeTruthy();

  await page.goto("/research/news");
  // La caché del feed puede servir la lista previa unos segundos: reintentar
  // con recarga hasta ver la fila sembrada.
  await expect(async () => {
    await page.reload();
    await expect(
      page.getByText("8-K presentado ante la SEC (strip e2e)", { exact: true })
    ).toBeVisible();
  }).toPass({ intervals: [2_000, 5_000, 10_000], timeout: 30_000 });
  // El compuesto con prefijo nunca se renderiza para esta fila.
  await expect(page.getByText("E2ESEC 8-K presentado ante la SEC (strip e2e)")).toHaveCount(0);
  await page.screenshot({ path: "test-results/news-es-sec-title-strip.png" });
});
