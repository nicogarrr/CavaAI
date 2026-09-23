import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

// The API-level evidence specs (research-evidence-flow) cover data-engine document
// ingest/claims/chat. These specs cover the gap: the Knowledge Library UI
// (upload form + document list) which no existing e2e spec touches.
test.describe("investor knowledge flow", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("knowledge upload form and document list render", async ({ page }) => {
    await page.goto("/knowledge");

    await expect(
      page.getByRole("heading", { name: "Biblioteca de conocimiento", level: 1 }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Subir conocimiento" })).toBeVisible();
    await expect(page.getByPlaceholder("Título del documento")).toBeVisible();
    await expect(page.locator('input[type="file"]').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Subir", exact: true })).toBeVisible();

    if (await page.getByText("Aún no hay documentos de conocimiento.").isVisible()) {
      return;
    }

    // Listed documents expose chunk browsing and principle extraction per row.
    const chunksLinks = page.getByRole("link", { name: "Fragmentos" });
    expect(await chunksLinks.count()).toBeGreaterThan(0);
    await expect(chunksLinks.first()).toHaveAttribute("href", /\/knowledge\?document=\d+/);
    await expect(page.getByRole("button", { name: "Extraer" }).first()).toBeVisible();
  });

  test("knowledge upload ingests a document and lists it", async ({ page }) => {
    const marker = `e2e-knowledge-${Date.now()}`;
    const title = `E2E investing notes ${marker}`;

    await page.goto("/knowledge");
    const uploadForm = page.locator("form", { has: page.getByPlaceholder("Título del documento") });
    await uploadForm.getByPlaceholder("Título del documento").fill(title);
    await uploadForm.locator('input[type="file"]').setInputFiles({
      name: `${marker}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from(
        `Inversor E2E ${marker}: comprar calidad con margen de seguridad y paciencia.`,
      ),
    });
    await uploadForm.getByRole("button", { name: "Subir", exact: true }).click();

    await expect(page.getByText("Documento ingerido")).toBeVisible({ timeout: 30_000 });

    await page.goto("/knowledge");
    await expect(page.getByText(title).first()).toBeVisible({ timeout: 30_000 });
  });
});
