import { expect, test } from '@playwright/test';

test.describe('fuentes locales por shell', () => {
  test.skip(process.env.E2E_UI_RUN !== '1', 'Necesita frontend');
  for (const path of ['/', '/sign-in']) {
    test(`${path} carga solo las fuentes usadas en WOFF2`, async ({ page }) => {
      const fontResponses: string[] = [];
      page.on('response', (response) => {
        if (/\.(ttf|woff2)(?:\?|$)/.test(response.url())) fontResponses.push(response.url());
      });
      await page.goto(path);
      await page.evaluate(() => document.fonts.ready);
      const expected = path === '/' ? ['publicSans', 'publicEditorial'] : ['publicSans'];
      const faces = await page.evaluate(() => [...document.fonts].map((face) => ({
        family: face.family.replace(/["']/g, ''), status: face.status,
      })));
      for (const family of expected) expect(faces).toContainEqual({ family, status: 'loaded' });
      expect(fontResponses.length).toBeGreaterThan(0);
      expect(fontResponses.every((url) => url.endsWith('.woff2'))).toBe(true);
      if (path === '/sign-in') {
        expect(faces.some((face) => face.family === 'publicEditorial' && face.status === 'loaded')).toBe(false);
        expect(fontResponses.some((url) => /InstrumentSerif/.test(url))).toBe(false);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    });
  }
});
