import { expect, test } from "@playwright/test";
import { createHash, createHmac, randomUUID } from "node:crypto";
import { seedMarketPrices } from "./fixtures/market-prices";
import { seedProPicksRun } from "./fixtures/propicks-run";

// Guard de regresion (bug d del lote log-hygiene, 2026-10-12).
//
// Contexto: el log de un run e2e del 11/10 mostro un warning de hidratacion
// de React 19 en /propicks sobre el input oculto del Slider Radix
// (SliderBubbleInput): el diff mostraba el SSR con
// style="display:none;caret-color:transparent" y el cliente con
// {display:"none"}.
//
// Estado de la investigacion (12/10, rama instinct/fix-log-hygiene):
// NO REPRODUCIBLE en el codigo actual. Hechos verificados:
// - Direccion del diff leida en el source de React 19.2
//   (react-dom-client.development.js, diffHydratedStyles):
//   "-" = atributo DOM servido por el SSR, "+" = props del cliente.
// - "caret-color" NO aparece en: el repo, components/ui/slider.tsx, ninguna
//   version publicada de @radix-ui/react-slider (tarballs npm 1.0.0, 1.1.0,
//   1.1.1, 1.1.2, 1.2.3, la 1.3.6 instalada y el source main en GitHub), ni
//   en los chunks .next del dev server.
// - 0 ocurrencias en: run completo del spec methodology-disclosure y cargas
//   directas de /propicks /risk /portfolio /plan con captura de consola.
// La causa NO esta probada: con la evidencia actual no se puede afirmar de
// donde salio el atributo caret-color del SSR de aquel run. Lo que si esta
// probado es que el codigo y las dependencias actuales no lo emiten.
//
// Este guard monta /propicks CON DATOS (run del embudo sembrado) para que
// los Sliders Radix y sus inputs ocultos esten montados de verdad, y falla
// si reaparece cualquier warning de hidratacion. Si algun dia falla, el
// diff completo queda en el log del test.

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

async function seedProPicksData(request: import("@playwright/test").APIRequestContext) {
  // Tickers sinteticos exclusivos de esta spec (tenant e2e compartido).
  const tickers = ["E2EPP1", "E2EPP2", "E2EPP3"];
  const days: { date: string; close: number }[] = [];
  for (let i = 30; i >= 1; i--) {
    days.push({ date: new Date(Date.now() - i * 86400000).toISOString().slice(0, 10), close: 100 + i });
  }
  for (const t of tickers) {
    const body = Buffer.from(JSON.stringify({ ticker: t, name: `${t} Inc`, exchange: "NASDAQ", currency: "USD" }));
    const res = await request.post(`${apiBase}/api/companies/ensure`, {
      data: body, headers: signedHeaders("POST", "/api/companies/ensure", body),
    });
    expect(res.status(), await res.text()).toBeLessThan(300);
    seedMarketPrices(t, days);
  }
  const asOf = new Date().toISOString().slice(0, 10);
  seedProPicksRun(apiUser, tickers.map((t, i) => ({ ticker: t, rank: i + 1, score: 90 - i * 5 })), asOf);
}

const HYDRATION_PATTERNS = [
  "An error occurred during hydration",
  "Hydration failed",
  "did not match. Server-rendered HTML",
  "A tree hydrated but some attributes",
  "caret-color",
];

for (const vp of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "movil", width: 390, height: 844 },
]) {
  test(`/propicks con Slider montado sin warnings de hidratacion (${vp.name})`, async ({ page, request }) => {
    await seedProPicksData(request);
    const consoleLines: string[] = [];
    page.on("console", (m) => consoleLines.push(m.text()));
    page.on("pageerror", (e) => consoleLines.push(String(e)));

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto("/propicks", { waitUntil: "networkidle", timeout: 60000 });

    // El guard solo prueba algo si la pagina renderiza el componente que
    // originaba el warning: los Sliders Radix de los filtros, montados con
    // su thumb (role=slider) y el input oculto interno (SliderBubbleInput).
    const sliders = page.getByRole("slider");
    await expect(sliders.first(), "los filtros con Slider Radix deben estar montados (pagina con datos, no ProPicksLoadError)").toBeVisible({ timeout: 30000 });
    const sliderCount = await sliders.count();
    expect(sliderCount, "EnhancedProPicksFilters monta 2 Sliders (score y riesgo)").toBeGreaterThanOrEqual(2);
    const hiddenInputs = await page.locator("[data-radix-slider-thumb] input, [role='slider'] input").count();

    // Margen para hidratacion tardia de boundaries Suspense streameados.
    await page.waitForTimeout(4000);

    const hits = consoleLines.filter((l) =>
      HYDRATION_PATTERNS.some((p) => l.includes(p))
    );
    expect(
      hits,
      `warnings de hidratacion en /propicks (${vp.name}, ${sliderCount} sliders, ${hiddenInputs} inputs ocultos):\n${hits.join("\n").slice(0, 2000)}`
    ).toEqual([]);
  });
}
