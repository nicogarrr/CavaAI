import { expect, test } from '@playwright/test';

// Isolated production build with MONGODB_URI pointing at an unused local port.
// Never point this fixture at production or a real account/database.
const outageURL = process.env.E2E_ANON_OUTAGE_URL;
if (outageURL) {
  const target = new URL(outageURL);
  if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname)) {
    throw new Error('El canario de auth/DB solo admite HTTP loopback aislado');
  }
}
test.describe('visitante sin Cookie con auth DB indisponible', () => {
  test.skip(!outageURL, 'Necesita standalone aislado con Mongo inaccesible');
  test.setTimeout(75000);
  for (const path of ['/', '/sign-in', '/metodologia']) {
    test(`${path} sigue pública sin Cookie`, async ({ playwright }) => {
      const context = await playwright.request.newContext({ baseURL: outageURL });
      try {
        const response = await context.get(path, { timeout: 10000 });
        expect(response.status()).toBe(200);
        expect(await response.text()).not.toMatch(/Application error|MongoDB URI is missing/);
      } finally { await context.dispose(); }
    });
  }
  test('Cookie presente no evita la comprobación de auth', async ({ playwright }) => {
    const context = await playwright.request.newContext({
      baseURL: outageURL,
      extraHTTPHeaders: { Cookie: 'unrelated=1' },
    });
    try {
      // Con cookie se conserva el fallo de DB de la pantalla de auth. No se
      // clasifica como visitante sin sesión sin hacer la validación existente.
      const response = await context.get('/sign-in', { timeout: 65000 });
      expect(response.status()).toBe(500);
    } finally { await context.dispose(); }
  });
});
