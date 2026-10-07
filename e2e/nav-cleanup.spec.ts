import { expect, test } from "@playwright/test";

// Quick win UX 3: nav limpio. El drawer comparte NAV_SECTIONS con el
// sidebar de escritorio: una sola entrada por destino, sin Workflows,
// «Mercado» en vez de «Vista de mercado» y sin «Mi plan» duplicado.
test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

test.use({ viewport: { width: 700, height: 900 } });

// El indicador dev de Next («1 Issue», <nextjs-portal>) es chrome de
// desarrollo, no UI de producto, y tapa el pie del sidebar en las capturas
// (bottom-left fijo). Se oculta para que las capturas muestren solo la app.
async function ocultarDevIndicator(page: import("@playwright/test").Page) {
  await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
}

test("el menú ya no tiene duplicados ni Workflows", async ({ page }) => {
  await page.goto("/inicio");
  await ocultarDevIndicator(page);
  const trigger = page.getByRole("button", { name: "Abrir menú de navegación" });
  await expect(trigger).toBeVisible();
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Menú de navegación" });
  await expect(dialog).toBeVisible();

  await expect(dialog.getByRole("link", { name: "Mercado", exact: true })).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Vista de mercado", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("link", { name: "Workflows", exact: true })).toHaveCount(0);

  // Una sola entrada para el plan y una para ayuda.
  await expect(dialog.getByRole("link", { name: "Plan", exact: true })).toHaveCount(1);
  await expect(dialog.getByRole("link", { name: "Ayuda", exact: true })).toHaveCount(1);
  await expect(dialog.getByText("Mi plan", { exact: true })).toHaveCount(0);

  await page.screenshot({ path: "test-results/nav-cleanup-drawer.png" });

  // Primera pantalla no prueba posicion/legibilidad del final: captura
  // tambien tras scroll al fondo del drawer (Plan/Ayuda visibles).
  await dialog.getByRole("link", { name: "Ayuda", exact: true }).scrollIntoViewIfNeeded();
  await expect(dialog.getByRole("link", { name: "Plan", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/nav-cleanup-drawer-bottom.png" });
});

test("el sidebar de escritorio muestra el nav limpio", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/inicio");
  await ocultarDevIndicator(page);

  const sidebar = page.locator("aside");
  await expect(sidebar).toBeVisible();
  await expect(sidebar).toHaveAttribute('data-collapsed', 'true');
  await expect(sidebar.getByRole('button', { name: 'Expandir menú' })).toBeVisible();

  await expect(sidebar.getByRole("link", { name: "Mercado", exact: true })).toBeVisible();
  await expect(sidebar.getByRole("link", { name: "Workflows", exact: true })).toHaveCount(0);

  // Una sola entrada por destino en todo el sidebar (árbol + pie).
  await expect(sidebar.getByRole("link", { name: "Plan", exact: true })).toHaveCount(1);
  await expect(sidebar.getByRole("link", { name: "Mi plan", exact: true })).toHaveCount(0);
  await expect(sidebar.getByRole("link", { name: "Ayuda", exact: true })).toHaveCount(1);
  // El pie conserva lo que no está en el árbol.
  await expect(sidebar.getByRole("link", { name: "Seguridad", exact: true })).toHaveCount(1);

  await page.screenshot({ path: "test-results/nav-cleanup-sidebar-rail.png" });
  await sidebar.getByRole('button', { name: 'Expandir menú' }).click();
  await expect(sidebar).not.toHaveAttribute('data-collapsed', 'true');
  await expect(sidebar.getByRole('button', { name: 'Plegar menú' })).toBeVisible();
  await expect(sidebar.getByText('Mercado', { exact: true })).toBeVisible();
  const preference = (await page.context().cookies()).find((cookie) => cookie.name === 'cavaai-sidebar-collapsed');
  expect(preference?.value).toBe('0');
  await page.reload();
  await expect(sidebar).not.toHaveAttribute('data-collapsed', 'true');
  await page.screenshot({ path: "test-results/nav-cleanup-sidebar-desktop.png" });

  // Igual en desktop: captura del sidebar tras scroll al fondo, con el
  // pie (Seguridad) y la zona de Plan/Ayuda visibles.
  await sidebar.getByRole("link", { name: "Seguridad", exact: true }).scrollIntoViewIfNeeded();
  // El pie tiene que ser visible de verdad: bounding box entero dentro del
  // viewport (con h-dvh a secas el aside desbordaba el alto del header y el
  // pie caia bajo el fold a scroll 0).
  const seguridadBox = await sidebar.getByRole("link", { name: "Seguridad", exact: true }).boundingBox();
  const viewport = page.viewportSize();
  expect(seguridadBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(seguridadBox!.y).toBeGreaterThanOrEqual(0);
  expect(Math.ceil(seguridadBox!.y + seguridadBox!.height)).toBeLessThanOrEqual(viewport!.height);
  await page.screenshot({ path: "test-results/nav-cleanup-sidebar-bottom.png" });
});
