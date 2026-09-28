import { expect, test } from "@playwright/test";
import { createHash, createHmac, randomUUID } from "node:crypto";

// Quick win UX 5: badges «En cartera / En watchlist» en eventos de noticias.
// Semilla firmada (patrón f339, tenant del bypass de navegador): una
// posición COST, NFLX en watchlist y un evento de cada uno.
test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

const apiSecret = process.env.RESEARCH_AUTH_SECRET ?? "cavaai-e2e-research-secret-at-least-32-characters";
const apiUser = "e2e-browser-user";
const apiBase = "http://127.0.0.1:8100";

function signedHeaders(method: string, path: string, body: Buffer) {
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

async function post(request: import("@playwright/test").APIRequestContext, path: string, payload: unknown) {
  const body = Buffer.from(JSON.stringify(payload));
  const res = await request.post(`${apiBase}${path}`, { data: body, headers: signedHeaders("POST", path, body) });
  expect(res.status(), await res.text()).toBeLessThan(300);
}

test("los eventos de noticias muestran En cartera / En watchlist", async ({ page, request }) => {
  const marker = randomUUID().slice(0, 8);
  await post(request, "/api/portfolio/transactions", {
    ticker: "COST", action: "buy", quantity: 1, price: 900, trade_date: "2026-01-15", currency: "USD", fees: 0,
  });
  await post(request, "/api/watchlist", { symbol: "NFLX" });
  await post(request, "/api/news/ingest", {
    items: [
      { ticker: "COST", title: `COST expands warehouses ${marker}`, text: "COST announced new warehouses.", source: "e2e", url: "https://e2e.invalid/cost" },
      { ticker: "NFLX", title: `NFLX raises prices ${marker}`, text: "NFLX announced a price change.", source: "e2e", url: "https://e2e.invalid/nflx" },
    ],
  });

  // Movers: el universo se calcula desde market_prices local; la semilla
  // firmada (endpoint test-only, 404 en produccion) pobla dos cierres por
  // ticker para que COST suba (+10%) y NFLX baje (-10%).
  await post(request, "/api/market/prices/seed", {
    items: [
      { ticker: "COST", date: "2026-09-24", close: 100, volume: 1000 },
      { ticker: "COST", date: "2026-09-25", close: 110, volume: 2000 },
      { ticker: "NFLX", date: "2026-09-24", close: 100, volume: 1000 },
      { ticker: "NFLX", date: "2026-09-25", close: 90, volume: 3000 },
    ],
  });

  await page.goto("/research/news");
  await expect(page.getByRole("heading", { name: "Eventos de noticias", level: 1 })).toBeVisible({ timeout: 60_000 });

  const costRow = page.getByRole("row", { name: new RegExp(`COST expands warehouses ${marker}`) });
  await expect(costRow.getByText("En cartera", { exact: true })).toBeVisible();
  await expect(costRow.getByText("En watchlist", { exact: true })).toHaveCount(0);

  const nflxRow = page.getByRole("row", { name: new RegExp(`NFLX raises prices ${marker}`) });
  await expect(nflxRow.getByText("En watchlist", { exact: true })).toBeVisible();
  await expect(nflxRow.getByText("En cartera", { exact: true })).toHaveCount(0);

  await page.screenshot({ path: "test-results/ticker-badges-news.png" });

  await page.goto("/movers");
  await expect(page.getByRole("heading", { name: "Movers", level: 1 })).toBeVisible({ timeout: 60_000 });
  const costMover = page.getByRole("row", { name: /COST/ });
  await expect(costMover.getByText("En cartera", { exact: true })).toBeVisible();
  const nflxMover = page.getByRole("row", { name: /NFLX/ });
  await expect(nflxMover.getByText("En watchlist", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/ticker-badges-movers.png" });
});
