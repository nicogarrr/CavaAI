import { test } from '@e2e-dev/web';
import { expect } from 'e2e';
import { z } from 'zod';

// Pasada de SOLO LECTURA contra produccion, solo paginas publicas (sin login).
const RULES =
  'READ-ONLY. Never create, edit, delete or submit anything except the login form. ' +
  'Do not click buttons that save, add, remove, buy, sell, import, or generate. Only navigate and read.';

test('public landing loads', async ({ app, browser }) => {
  await app.open('/');
  await expect(browser.locator('body')).toBeVisible();
});

test('login page is reachable and clean', async ({ app, agent }) => {
  await app.open('/');
  await agent.act(`${RULES} Find and open the login or sign-in page. Do not type anything.`);
  await agent.assert('a login form or sign-in prompt is visible with no error banner');
  const info = await agent.extract(
    'List visible UI problems on this page: error messages, untranslated English text, overlapping or cut-off elements. Use an empty list if clean.',
    { schema: z.object({ problems: z.array(z.string()) }) },
  );
  console.log('[login]', JSON.stringify(info.problems.length ? info.problems : 'ninguno'));
});
