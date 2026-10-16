import { expect, test } from '@playwright/test';

test.describe('landing: tipografía y header compacto', () => {
  test.skip(process.env.E2E_UI_RUN !== '1', 'Necesita frontend E2E');
  for (const width of [320, 360, 390, 400, 500, 639, 640, 767, 768, 1280]) {
    test(`header en una fila sin desbordes a ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('h1')).toHaveCSS('font-family', /editorial/);
      expect(await page.evaluate(() => document.fonts.check('16px editorial'))).toBe(true);
      const header = page.locator('.public-header-inner');
      await expect(header).toBeVisible();
      const geometry = await header.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        const boxes = [...element.children]
          .filter((child) => child.getClientRects().length > 0 && getComputedStyle(child).display !== 'none')
          .map((child) => child.getBoundingClientRect());
        return {
          height: bounds.height,
          fits: boxes.every((box) => box.left >= bounds.left && box.right <= bounds.right),
          overlap: boxes.some((box, index) => index > 0 && box.left < boxes[index - 1].right - 1),
          overflow: document.documentElement.scrollWidth > innerWidth,
          font: getComputedStyle(document.body).fontFamily,
        };
      });
      expect(geometry.height).toBe(56);
      expect(geometry.fits).toBe(true);
      expect(geometry.overlap).toBe(false);
      expect(geometry.overflow).toBe(false);
      expect(geometry.font.toLowerCase()).toContain('manrope');
      const trigger = page.getByRole('button', { name: 'Abrir menú de páginas' });
      if (width < 768) {
        await expect(trigger).toBeVisible();
        await trigger.click();
        await expect(page.getByRole('dialog')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog')).toHaveCount(0);
      } else {
        await expect(trigger).toBeHidden();
      }
    });
  }
});
