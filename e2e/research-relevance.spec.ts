import { expect, test } from "@playwright/test";
import { createHash, createHmac, randomUUID } from "node:crypto";

// Quick win UX 6: /research ordenado por relevancia. Semilla firmada
// (patrón f339, tenant del bypass de navegador): tres empresas E2E*,
// posición abierta en E2EZZZ y E2EMID en watchlist. El filtro ?q=E2E
// acota el índice a las tres para una aserción de orden estable.
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

test("el índice ordena cartera > watchlist > resto", async ({ page, request }) => {
  await post(request, "/api/companies/ensure", { ticker: "E2EAAA", name: "E2E Alpha Corp" });
  await post(request, "/api/companies/ensure", { ticker: "E2EMID", name: "E2E Middle Corp" });
  await post(request, "/api/companies/ensure", { ticker: "E2EZZZ", name: "E2E Zulu Corp" });
  await post(request, "/api/portfolio/transactions", {
    ticker: "E2EZZZ", action: "buy", quantity: 1, price: 100, trade_date: "2026-01-15", currency: "USD", fees: 0,
  });
  await post(request, "/api/watchlist", { symbol: "E2EMID" });

  await page.goto("/research?q=E2E");
  await expect(page.getByRole("heading", { name: "Índice de research", level: 1 })).toBeVisible({ timeout: 60_000 });

  const tickers = await page.locator("ul li a .text-base").allTextContents();
  const e2eTickers = tickers.map((t) => t.trim()).filter((t) => t.startsWith("E2E"));
  expect(e2eTickers).toEqual(["E2EZZZ", "E2EMID", "E2EAAA"]);

  await page.screenshot({ path: "test-results/research-relevance.png" });
});
