import { expect, test, type Page } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

// iPhone 14 viewport: 390x844 con táctil.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

async function expectNoPageOverflow(page: Page) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(
    overflow.scrollWidth,
    `overflow horizontal: scrollWidth=${overflow.scrollWidth} > innerWidth=${overflow.innerWidth} en ${page.url()}`,
  ).toBeLessThanOrEqual(overflow.innerWidth + 1);
}

async function expectPageLoaded(page: Page) {
  // La ruta carga: hay contenido principal y no hay pantalla de error 500.
  await expect(page.locator("main, body").first()).toBeVisible();
  await expect(page.getByText(/Application error|Something went wrong/i)).toHaveCount(0);
}

// Toda ruta del nav principal (+ /screener singular, cubierto por los specs
// investor-*) debe cargar a 390px sin overflow horizontal de página.
const NAV_ROUTES: { path: string; heading?: string }[] = [
  { path: "/" },
  { path: "/portfolio" },
  { path: "/research" },
  { path: "/knowledge" },
  { path: "/search" },
  { path: "/screeners" },
  { path: "/screener", heading: "Screener" },
  { path: "/watchlist", heading: "Watchlist" },
  { path: "/movers", heading: "Movers" },
  { path: "/propicks" },
  { path: "/alerts", heading: "Alertas" },
  { path: "/security", heading: "Seguridad" },
  { path: "/research/MSFT", heading: "MSFT" },
];

test.describe("mobile nav sin overflow horizontal", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  for (const route of NAV_ROUTES) {
    test(`${route.path} carga sin overflow a 390px`, async ({ page }) => {
      await page.goto(route.path);
      await expectPageLoaded(page);
      if (route.heading) {
        await expect(
          page.getByRole("heading", { name: route.heading, level: 1 }),
        ).toBeVisible();
      }
      await expectNoPageOverflow(page);
    });
  }
});
