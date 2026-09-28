import { expect, test } from "@playwright/test";
import { createHash, createHmac, randomUUID } from "node:crypto";

// Prueba F339: a 390px el FAB del chat no debe tapar la leyenda del donut EN
// REPOSO. Stack e2e estándar del repo (webServer de playwright.config.ts).
test.use({
  viewport: { width: 390, height: 844 },
  hasTouch: true,
  isMobile: true,
  channel: "chrome",
});

const apiSecret = "cavaai-e2e-research-secret-at-least-32-characters";
const apiUser = "e2e-browser-user"; // el bypass E2E firma tenant=user.id
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

test("F339: el FAB queda oculto en reposo mientras la leyenda cruza su zona", async ({ page, request }) => {
  // Semilla: 6 posiciones para que el donut tenga leyenda real.
  const seeds = [
    { ticker: "GOOGL", quantity: 10, price: 150 },
    { ticker: "AAPL", quantity: 8, price: 170 },
    { ticker: "MSFT", quantity: 3, price: 400 },
    { ticker: "V", quantity: 4, price: 250 },
    { ticker: "AMZN", quantity: 5, price: 180 },
    { ticker: "JPM", quantity: 6, price: 200 },
  ];
  for (const s of seeds) {
    const body = Buffer.from(JSON.stringify({
      ticker: s.ticker, action: "BUY", quantity: s.quantity, price: s.price,
      trade_date: "2026-01-15", currency: "USD", fees: 0,
    }));
    const res = await request.post(`${apiBase}/api/portfolio/transactions`, {
      data: body, headers: signedHeaders("POST", "/api/portfolio/transactions", body),
    });
    expect(res.status(), await res.text()).toBeLessThan(300);
  }

  await page.goto("/portfolio");
  const legend = page.locator("#portfolio-allocation-legend");
  await expect(legend).toBeVisible({ timeout: 60_000 });
  const fab = page.locator('button[aria-label="Abrir asistente de cartera"]');
  await expect(fab).toBeVisible();

  // Coloca la leyenda dentro de la zona del FAB (banda 96px abajo-derecha).
  await page.evaluate(() => {
    const el = document.getElementById("portfolio-allocation-legend")!;
    const rect = el.getBoundingClientRect();
    const target = window.scrollY + rect.top - (window.innerHeight - 140);
    window.scrollTo(0, Math.max(0, target));
  });
  // En reposo (>600 ms sin scroll): el FAB debe quedar oculto.
  await page.waitForTimeout(1200);
  const overlap = await page.evaluate(() => {
    const rect = document.getElementById("portfolio-allocation-legend")!.getBoundingClientRect();
    return rect.bottom > window.innerHeight - 96 && rect.right > window.innerWidth - 96;
  });
  expect(overlap, "la leyenda debe quedar en la zona del FAB para la prueba").toBe(true);
  await expect.poll(async () => fab.evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
  await page.screenshot({ path: "/downloads/f339-rest-fab-hidden.png" });

  // Saca la leyenda de la zona: el FAB reaparece en reposo.
  await page.evaluate(() => {
    const el = document.getElementById("portfolio-allocation-legend")!;
    const rect = el.getBoundingClientRect();
    window.scrollTo(0, window.scrollY + rect.top - 220);
  });
  await page.waitForTimeout(1200);
  await expect.poll(async () => fab.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  await page.screenshot({ path: "/downloads/f339-rest-fab-visible.png" });
});
