import { expect, test } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

test.describe("research thesis workspace", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  test("thesis view shows honest empty states when no thesis is persisted", async ({
    page,
  }) => {
    await page.goto("/research/MSFT?view=thesis");

    // Async generation entry point is present and idle.
    await expect(
      page.getByRole("button", { name: "Generate thesis" }),
    ).toBeVisible();

    // Memo export link targets the per-ticker markdown endpoint.
    await expect(
      page.getByRole("link", { name: "Exportar memo" }),
    ).toHaveAttribute("href", "/api/thesis-memo/MSFT");

    // Without a persisted thesis the workspace says so - nothing invented.
    await expect(page.getByText("No thesis exists.")).toBeVisible();

    // The version-history panel is a <details> collapsed by default.
    await page
      .locator("summary", { hasText: "Historial de versiones y aprobaciones" })
      .click();
    await expect(
      page.getByText("Aún no hay historial de versiones."),
    ).toBeVisible();
    await expect(page.getByText("0 versions")).toBeVisible();
    await expect(page.getByText("0 claims")).toBeVisible();

    // The history panel states its own provenance limits.
    await expect(
      page.getByText(
        "el sistema no registra quién aprobó cada versión",
      ),
    ).toBeVisible();
  });
});
