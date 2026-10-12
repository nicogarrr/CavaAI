import { expect, test } from "@playwright/test";
import { createHash, createHmac, randomUUID } from "node:crypto";
import { seedMarketPrices } from "./fixtures/market-prices";
import { seedFxRates } from "./fixtures/fx-rates";

// Regresion (bug b del lote log-hygiene, 2026-10-12): el log de un run e2e
// del 11/10 mostraba dos warnings de Recharts
// "The width(-1) and height(-1) of chart should be greater than 0" al
// renderizar /portfolio Resumen a 768px con cartera real.
//
// Causa raiz (verificada en node_modules/recharts@3.3.0,
// es6/component/ResponsiveContainer.js): ResponsiveContainer arranca con el
// estado initialDimension = {width: -1, height: -1} y el primer render (antes
// de que el ResizeObserver mida) dispara el warn dev. El chart no se
// renderiza con ese estado (devuelve null), asi que es un falso positivo de
// log, pero ensucia cada montaje. Fix: pasar initialDimension con la caja
// real del wrapper (h-[200px] en ambos charts) en PortfolioNavChart y
// PortfolioAllocationChart; el ResizeObserver corrige despues.
//
// Esta spec renderiza /portfolio Resumen con datos reales sembrados
// (companies + precios + FX EUR/USD + transacciones firmadas) y falla si
// reaparece el warning, en desktop y a 768px (el viewport del log).

test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

const apiSecret = process.env.RESEARCH_AUTH_SECRET ?? "cavaai-e2e-research-secret-at-least-32-characters";
const apiUser = "e2e-browser-user";
const apiBase = "http://127.0.0.1:8100";

function signedHeaders(method: string, path: string, body: Buffer = Buffer.alloc(0)) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const nonce = randomUUID().replaceAll("-", "");
  const bodyHash = createHash("sha256").update(body).digest("hex");
  const signature = createHmac("sha256", apiSecret)
    .update(`${apiUser}:${apiUser}:${timestamp}:${nonce}:${method}:${path}:${bodyHash}`)
    .digest("hex");
  return {
    "X-CavaAI-Tenant": apiUser,
    "X-CavaAI-User": apiUser,
    "X-CavaAI-Timestamp": timestamp,
    "X-CavaAI-Nonce": nonce,
    "X-CavaAI-Method": method,
    "X-CavaAI-Path": path,
    "X-CavaAI-Body-Hash": bodyHash,
    "X-CavaAI-Signature": signature,
    "Content-Type": "application/json",
  };
}

async function seedPortfolioWithCharts(request: import("@playwright/test").APIRequestContext) {
  // Tickers sinteticos exclusivos de esta spec (mismo criterio que
  // methodology-disclosure: el tenant e2e es compartido).
  const seeds = [
    { ticker: "E2ECW1", quantity: 5, price: 900 },
    { ticker: "E2ECW2", quantity: 4, price: 700 },
    { ticker: "E2ECW3", quantity: 6, price: 250 },
  ];
  const days: { date: string; close: number }[] = [];
  for (let i = 90; i >= 1; i--) {
    const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    days.push({ date: d, close: 100 + i });
  }
  for (const s of seeds) {
    const body = Buffer.from(JSON.stringify({
      ticker: s.ticker, name: `${s.ticker} Inc`, exchange: "NASDAQ", currency: "USD",
    }));
    const res = await request.post(`${apiBase}/api/companies/ensure`, {
      data: body, headers: signedHeaders("POST", "/api/companies/ensure", body),
    });
    expect(res.status(), await res.text()).toBeLessThan(300);
    seedMarketPrices(s.ticker, days);
  }
  // FX en la direccion que consulta portfolio_fx_service.py: base=EUR,
  // quote=USD, rate_date <= as_of. Desde antes de la fecha de compra.
  const fxRows: { date: string; rate: number }[] = [];
  for (let i = 0; i < 300; i++) {
    fxRows.push({ date: new Date(Date.parse("2026-01-01T00:00:00Z") + i * 86400000).toISOString().slice(0, 10), rate: 1.087 });
  }
  seedFxRates(apiUser, "EUR", "USD", fxRows);
  for (const s of seeds) {
    const body = Buffer.from(JSON.stringify({
      ticker: s.ticker, action: "buy", quantity: s.quantity, price: s.price,
      trade_date: "2026-01-15", currency: "USD", fees: 0,
    }));
    const res = await request.post(`${apiBase}/api/portfolio/transactions`, {
      data: body, headers: signedHeaders("POST", "/api/portfolio/transactions", body),
    });
    expect(res.status(), await res.text()).toBeLessThan(300);
  }
}

const RECHARTS_SIZE_PATTERNS = ["width(-1)", "height(-1)"];

for (const vp of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "movil-768", width: 768, height: 900 },
]) {
  test(`/portfolio Resumen sin warnings de tamano de Recharts (${vp.name})`, async ({ page, request }) => {
    await seedPortfolioWithCharts(request);
    const consoleLines: string[] = [];
    page.on("console", (m) => consoleLines.push(m.text()));

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto("/portfolio", { waitUntil: "networkidle", timeout: 60000 });
    // Espera por estado: el NAV chart solo aparece cuando scores.history
    // tiene datos; sin chart el guard no prueba nada.
    await page.waitForSelector(".recharts-responsive-container", { timeout: 30000 });
    await page.waitForTimeout(4000);

    const charts = await page.locator(".recharts-responsive-container").count();
    expect(charts, "la cartera sembrada debe renderizar al menos un chart").toBeGreaterThan(0);
    const hits = consoleLines.filter((l) => RECHARTS_SIZE_PATTERNS.some((p) => l.includes(p)));
    expect(
      hits,
      `warnings de Recharts en /portfolio (${vp.name}):\n${hits.join("\n").slice(0, 2000)}`
    ).toEqual([]);
  });
}
