import { createHmac } from "node:crypto";
import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

const uiBackendURL = process.env.E2E_UI_BACKEND_URL ?? "http://127.0.0.1:8100";
const e2eResearchSecret =
  process.env.RESEARCH_AUTH_SECRET ?? "cavaai-e2e-research-secret-at-least-32-characters";

// /research/MSFT solo renderiza el workspace si la empresa existe: el spec
// asegura su propio dato en vez de depender del estado de otros specs
// (misma firma que el harness de playwright.config).
test.beforeAll(async () => {
  if (!runUiE2E) return;
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const res = await fetch(`${uiBackendURL}/api/companies/ensure`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-CavaAI-Tenant": "e2e-api-tenant",
      "X-CavaAI-User": "e2e-api-user",
      "X-CavaAI-Timestamp": timestamp,
      "X-CavaAI-Signature": createHmac("sha256", e2eResearchSecret)
        .update(`e2e-api-tenant:e2e-api-user:${timestamp}`)
        .digest("hex"),
    },
    body: JSON.stringify({ ticker: "MSFT", name: "Microsoft Corporation" }),
  });
  if (!res.ok) throw new Error(`ensure MSFT fallo: ${res.status} ${await res.text()}`);
});

test.describe("research thesis workspace", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("thesis view shows honest empty states when no thesis is persisted", async ({
    page,
  }) => {
    await page.goto("/research/MSFT?view=thesis");

    // Async generation entry point is present and idle.
    await expect(
      page.getByRole("button", { name: "Generar tesis" }),
    ).toBeVisible();

    // Memo export link targets the per-ticker markdown endpoint.
    await expect(
      page.getByRole("link", { name: "Exportar memo" }),
    ).toHaveAttribute("href", "/api/thesis-memo/MSFT");

    // Without a persisted thesis the workspace says so - nothing invented.
    await expect(page.getByText("Aún no existe ninguna tesis.")).toBeVisible();

    // Collapsible panels open by default on desktop viewports.
    await expect(
      page.getByText("Aún no hay historial de versiones."),
    ).toBeVisible();
    await expect(page.getByText("0 versiones")).toBeVisible();
    await expect(page.getByText("0 afirmaciones")).toBeVisible();

    // The history panel states its own provenance limits.
    await expect(
      page.getByText(
        "el sistema no registra quién aprobó cada versión",
      ),
    ).toBeVisible();
  });

  test("collapsible panels start collapsed on a 390px mobile viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/research/MSFT?view=thesis");

    const emptyHistory = page.getByText("Aún no hay historial de versiones.");
    await expect(emptyHistory).toBeHidden();

    // The tap target expands the panel on demand.
    await page
      .locator("summary", { hasText: "Historial de versiones y aprobaciones" })
      .click();
    await expect(emptyHistory).toBeVisible();
  });
});
