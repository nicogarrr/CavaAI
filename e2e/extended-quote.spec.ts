import { expect, test } from '@playwright/test';
test.skip(process.env.E2E_EXTENDED_QUOTE_RUN !== '1', 'Run scripts/test-extended-quote.mjs');
const quote = {
    ticker: 'MSFT', status: 'available', session: 'post', price_session: 'post', price: 523.0,
    timestamp: 1791497100, trading_date: '2026-10-08', currency: 'USD', fetched_at: 1791497100,
    source: 'Yahoo Finance (no oficial), retraso posible', previous_close: 529.76,
    previous_close_timestamp: null, change: -6.76, change_percent: -1.276,
    regular_close: 522.61, regular_close_timestamp: 1791489601,
    open: 533.51, high: 533.51, low: 518.79, metrics_timestamp: 1791489540, metrics_session: '2026-10-08',
};
for (const width of [1440, 390]) {
    test(`quote with real schema, mock provider ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        let response: Record<string, unknown> = quote;
        let calls = 0;
        await page.route('**/api/companies/MSFT/extended-quote', route => {
            calls++;
            return route.fulfill({ json: response });
        });
        await page.clock.install();
        await page.goto('/extended-quote-preview');
        const header = page.getByTestId('company-header-quote');
        await expect(header.getByText('Post-cierre · 00:05', { exact: true })).toBeVisible();
        await expect(header.getByText('Yahoo Finance (no oficial), retraso posible · 00:05 (Madrid)', { exact: true })).toBeVisible();
        await expect(header.getByText('Cierre anterior', { exact: true }).locator('..').locator('dd')).toHaveText('N/D');
        await expect(header.getByText('Cierre regular:', { exact: false })).toContainText('522,61');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: `/downloads/extended-quote-${width}.png`, fullPage: true });
        const initialCalls = calls;
        response = { ...quote, session: 'pre', status: 'retrasado' };
        await page.clock.fastForward(60000);
        await expect(header.getByText('Premercado · 00:05 · Retrasado', { exact: true })).toBeVisible();
        response = { ...quote, session: 'cerrado', change: null, change_percent: null };
        await page.clock.fastForward(60000);
        await expect(header.getByText('Cierre del 8 oct · 00:05', { exact: true })).toBeVisible();
        await expect(header.getByText('-1,28%', { exact: true })).not.toBeVisible();
        response = { status: 'unavailable' };
        await page.clock.fastForward(60000);
        await expect(header.locator('.text-4xl')).toHaveText('N/D');
        expect(calls).toBe(initialCalls + 3);
        await page.screenshot({ path: `/downloads/extended-quote-nd-${width}.png`, fullPage: true });
        const beforeHidden = calls;
        await page.evaluate(() => Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' }));
        await page.clock.fastForward(120000);
        expect(calls).toBe(beforeHidden);
        response = { ...quote, timestamp: null };
        await page.evaluate(() => {
            Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
            document.dispatchEvent(new Event('visibilitychange'));
        });
        await expect.poll(() => calls).toBe(beforeHidden + 1);
        await expect(header.locator('.text-4xl')).toHaveText('N/D');
    });
}
