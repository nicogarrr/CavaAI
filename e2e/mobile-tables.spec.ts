import { expect, test, type Page } from "@playwright/test";

const runUiE2E = process.env.E2E_UI_RUN === "1";

// iPhone 14 viewport: 390x844 con táctil.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

// Las páginas con datos tabulares deben renderizar cards o tablas con scroll
// interno: la página nunca desborda horizontalmente. Si una tabla es más
// ancha que el viewport, debe vivir dentro de un contenedor con
// overflow-x auto/scroll.
async function expectTablesScrollInside(page: Page, route: string) {
  const report = await page.evaluate(() => {
    const pageOverflow =
      document.documentElement.scrollWidth <= window.innerWidth + 1;
    const tables = Array.from(document.querySelectorAll("table"));
    const bad: string[] = [];
    for (const table of tables) {
      const rect = table.getBoundingClientRect();
      if (rect.width <= window.innerWidth + 1) continue;
      let el: HTMLElement | null = table.parentElement;
      let contained = false;
      while (el) {
        const style = getComputedStyle(el);
        if (
          (style.overflowX === "auto" || style.overflowX === "scroll") &&
          el.getBoundingClientRect().width <= window.innerWidth + 1
        ) {
          contained = true;
          break;
        }
        el = el.parentElement;
      }
      if (!contained) {
        bad.push(
          `tabla de ${Math.round(rect.width)}px sin contenedor de scroll interno`,
        );
      }
    }
    return {
      pageOverflow,
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      tableCount: tables.length,
      bad,
    };
  });
  expect(
    report.pageOverflow,
    `${route}: overflow de página scrollWidth=${report.scrollWidth} > innerWidth=${report.innerWidth}`,
  ).toBe(true);
  expect(
    report.bad,
    `${route}: ${report.bad.join("; ")} (${report.tableCount} tablas)`,
  ).toEqual([]);
}

const TABLE_ROUTES = [
  { path: "/watchlist", heading: "Watchlist" },
  { path: "/portfolio", heading: undefined },
  { path: "/research/MSFT", heading: "MSFT" },
];

test.describe("mobile tablas con scroll interno", () => {
  test.skip(!runUiE2E, "Set E2E_UI_RUN=1 to run browser tests.");

  for (const route of TABLE_ROUTES) {
    test(`${route.path} renderiza cards o tabla contenida, sin overflow`, async ({
      page,
    }) => {
      await page.goto(route.path);
      await expect(page.locator("main, body").first()).toBeVisible();
      await expect(page.getByText(/Application error|Something went wrong/i)).toHaveCount(0);
      if (route.heading) {
        await expect(
          page.getByRole("heading", { name: route.heading, level: 1 }),
        ).toBeVisible();
      }
      await expectTablesScrollInside(page, route.path);
    });
  }
});
