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
      page.getByRole("heading", { name: "Knowledge Library", level: 1 }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Upload knowledge" })).toBeVisible();
    await expect(page.getByPlaceholder("Document title")).toBeVisible();
    await expect(page.locator('input[type="file"]').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload", exact: true })).toBeVisible();

    if (await page.getByText("No knowledge documents yet.").isVisible()) {
      return;
    }

    // Listed documents expose chunk browsing and principle extraction per row.
    const chunksLinks = page.getByRole("link", { name: "Chunks" });
    expect(await chunksLinks.count()).toBeGreaterThan(0);
    await expect(chunksLinks.first()).toHaveAttribute("href", /\/knowledge\?document=\d+/);
    await expect(page.getByRole("button", { name: "Extract" }).first()).toBeVisible();
  });

  test("knowledge upload ingests a document and lists it", async ({ page }) => {
    const marker = `e2e-knowledge-${Date.now()}`;
    const title = `E2E investing notes ${marker}`;

    await page.goto("/knowledge");
    const uploadForm = page.locator("form", { has: page.getByPlaceholder("Document title") });
    await uploadForm.getByPlaceholder("Document title").fill(title);
    await uploadForm.locator('input[type="file"]').setInputFiles({
      name: `${marker}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from(
        `Inversor E2E ${marker}: comprar calidad con margen de seguridad y paciencia.`,
      ),
    });
    await uploadForm.getByRole("button", { name: "Upload", exact: true }).click();

    await expect(page.getByText("Document ingested")).toBeVisible({ timeout: 30_000 });

    await page.goto("/knowledge");
    await expect(page.getByText(title).first()).toBeVisible({ timeout: 30_000 });
  });
});
