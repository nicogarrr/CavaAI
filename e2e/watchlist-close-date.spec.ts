import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
test.skip(process.env.E2E_UI_RUN !== '1', 'Local UI fixture required');
const source = readFileSync('app/(root)/watchlist/page.tsx', 'utf8');
const dateClass = source.match(/<dd className="([^"]+)"[^>]*>\{stock\.priceAsOf/)?.[1];
for (const width of [320, 390, 820]) {
 test(`watchlist full close date remains readable at ${width}px`, async ({page}) => {
  await page.setViewportSize({width,height:844});
  await page.goto('/watchlist');
  await expect(page.getByRole('heading',{name:'Watchlist',level:1})).toBeVisible();
  const sheets = await page.locator('link[rel=stylesheet]').evaluateAll(nodes=>nodes.map(node=>(node as HTMLLinkElement).href));
  expect(sheets.length).toBeGreaterThan(0);
  await page.setContent(`${sheets.map(href=>`<link rel="stylesheet" href="${href}">`).join('')}<main class="p-8 bg-gray-950 text-gray-200"><article class="p-4 border border-gray-800 rounded-lg"><dl class="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-gray-800/50 px-2 py-3 text-center"><div class="min-w-0"><dt>Precio</dt><dd>29,47 US$</dd><dd data-testid="close-date" class="${dateClass}">Cierre 2026-10-06</dd></div><div>Market Cap<br>$6.92B</div><div>PER (TTM)<br>N/D</div></dl></article></main>`);
  const date = page.getByTestId('close-date');
  await expect(date).toBeVisible();
  const geometry=await date.evaluate(node=>({width:node.clientWidth,scroll:node.scrollWidth,ellipsis:getComputedStyle(node).textOverflow}));
  expect(geometry.ellipsis).not.toBe('ellipsis');
  expect(geometry.scroll).toBeLessThanOrEqual(geometry.width+1);
  await page.screenshot({path:`test-results/watchlist-close-date-${width}.png`});
 });
}
