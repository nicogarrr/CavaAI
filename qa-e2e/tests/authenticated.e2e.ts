import { test } from '@e2e-dev/web';
import { z } from 'zod';

// Pasada de SOLO LECTURA con la cuenta desechable "Instinct Audit" (datos ficticios).
// Las credenciales llegan por secrets del repo (E2E_USER_EMAIL / E2E_USER_PASSWORD),
// nunca estan en el codigo ni en los logs. Sin ellas, el fichero se salta de forma
// explicita (el resumen lo dice) en vez de pasar en verde sin haber mirado nada.
const EMAIL = process.env.E2E_USER_EMAIL ?? '';
const PASSWORD = process.env.E2E_USER_PASSWORD ?? '';

const RULES =
  'READ-ONLY. Only navigate, click tabs and read. Never create, edit, delete, import, ' +
  'save, buy, sell, generate or submit anything. Never click buttons named like Add, ' +
  'Remove, Delete, Save, Sync, Import, Upload, Create, Generate, Buy or Sell.';

const FINDINGS = z.object({
  checked: z.literal(true),
  problems: z.array(z.string()),
});

const REPORT =
  'Report visible UI problems on the screen as JSON with exactly two keys: "checked" ' +
  '(the boolean true) and "problems" (array of short strings, empty if clean). A problem is: ' +
  'an error banner, a stuck loading state, untranslated English text in the Spanish UI, ' +
  'a value shown without currency or unit, an empty state that hides a failed load, ' +
  'text cut off or overlapping, or "Fecha desconocida" / "SIN DATOS" / "N/D" where a value is expected.';

test.describe('rutas autenticadas (solo lectura)', () => {
  test.skip(!EMAIL || !PASSWORD, 'Faltan los secrets E2E_USER_EMAIL / E2E_USER_PASSWORD: no se ejecuta.');

  test.beforeEach(async ({ app, browser }) => {
    await app.open('/sign-in');
    await browser.getByPlaceholder('email@ejemplo.com').fill(EMAIL);
    await browser.getByPlaceholder('Introduce tu contraseña').fill(PASSWORD);
    await browser.getByRole('button', { name: /iniciar sesi|entrar|acceder/i }).click();
    await browser.waitForURL((url) => !url.pathname.startsWith('/sign-in'), { timeout: 30_000 });
  });

  const scenarios: Array<{ tag: string; path: string; task: string }> = [
    {
      tag: 'cartera',
      path: '/portfolio',
      task: 'Open every tab of the portfolio page one by one (click each tab, wait for it to load). Also check that amounts show a currency consistently (EUR vs US$).',
    },
    {
      tag: 'research',
      path: '/research',
      task: 'Open the research page for AAPL, then open every tab and the Modelo (valuation model) section, scrolling to read each one.',
    },
    { tag: 'propicks', path: '/propicks', task: 'Read the page and open every visible tab or card detail without saving anything.' },
    { tag: 'inteligencia', path: '/portfolio/intelligence', task: 'Read the page and open every tab.' },
    { tag: 'conocimiento', path: '/knowledge', task: 'Read the page, open every tab, and then open the Grafo (knowledge graph) page.' },
    { tag: 'noticias', path: '/research/news', task: 'Read the news list and open one item detail if available. Check dates and the ticker each item is attached to.' },
    { tag: 'watchlist', path: '/watchlist', task: 'Read the watchlist rows and check dates and N/D values.' },
  ];

  for (const s of scenarios) {
    test(`${s.tag}: navega pestanas y detecta problemas`, async ({ app, agent }) => {
      await app.open(s.path);
      await agent.act(`${RULES} ${s.task}`);
      await agent.assert('the page is not showing a crash, a blank screen or an unhandled error');
      const info = await agent.extract(REPORT, { schema: FINDINGS });
      console.log(`[${s.tag}]`, JSON.stringify(info.problems.length ? info.problems : 'ninguno'));
    });
  }
});
