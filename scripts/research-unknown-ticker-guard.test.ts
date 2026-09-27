/**
 * Guard F286: /research/<ticker> fuera del master NUNCA devuelve 404 desde
 * este camino ni ofrece el CTA «Generar tesis» sobre una identidad no
 * verificada. Política de veracidad: ninguna respuesta del proveedor prueba
 * la inexistencia del emisor buscado (un perfil {} solo dice que Finnhub no
 * conoce el símbolo), y un perfil con nombre prueba que el símbolo existe en
 * alguna bolsa, no que sea ese emisor (ALM -> Almonty US, no Almirall/BME).
 * Tres estados honestos sin CTA; el fallback completo (panel + CTA) queda
 * reservado a empresas del master.
 * Ejecución: node --experimental-strip-types --test scripts/research-unknown-ticker-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { resolveUnknownListingIdentity } from '../lib/research/unknown-listing.ts';

void test('perfil sin nombre propio -> not-in-sources (nunca 404)', () => {
    assert.deepEqual(resolveUnknownListingIdentity({}, 'ZZZZ'), { kind: 'not-in-sources' });
    assert.deepEqual(resolveUnknownListingIdentity({ name: '   ' }, 'ZZZZ'), { kind: 'not-in-sources' });
    assert.deepEqual(resolveUnknownListingIdentity({ name: 'ZZZZ' }, 'ZZZZ'), { kind: 'not-in-sources' });
});

void test('perfil del ticker desnudo con nombre -> unverified (emisor ambiguo)', () => {
    // El caso ALM: el símbolo existe (Almonty US) pero puede no ser el emisor
    // buscado (Almirall/BME).
    assert.deepEqual(
        resolveUnknownListingIdentity({ name: 'Almonty Industries' }, 'ALM'),
        { kind: 'unverified', providerName: 'Almonty Industries' },
    );
});

void test('proveedor no disponible -> unavailable', () => {
    assert.deepEqual(resolveUnknownListingIdentity(null, 'VZ'), { kind: 'unavailable' });
});

void test('la página pinta los tres estados sin 404 y sin CTA fuera del master', () => {
    const source: string = readFileSync(new URL('../app/(root)/research/[ticker]/page.tsx', import.meta.url), 'utf8');
    const fallbackStart = source.indexOf('if (!snapshot) {');
    const fallbackEnd = source.indexOf('const company = snapshot.company;', fallbackStart);
    assert.ok(fallbackStart > -1 && fallbackEnd > fallbackStart, 'debe existir la rama if (!snapshot)');
    const window = source.slice(fallbackStart, fallbackEnd);

    // La rama fuera del master no puede devolver 404: notFound no existe en la página.
    assert.ok(!source.includes('notFound'), 'este camino nunca devuelve 404 (ninguna respuesta prueba inexistencia)');

    // La pertenencia al master se comprueba con un boolean EXPLÍCITO
    // (getResearchCompanyBasics), nunca inferida del snapshot de mercado:
    // una empresa real del master con name === ticker y sin cotización no
    // puede perder el CTA por una inferencia.
    assert.match(window, /getResearchCompanyBasics\(ticker\)/);
    assert.match(window, /if \(!masterBasics\) \{/);
    // El perfil del proveedor solo se consulta en master-miss.
    assert.match(window, /resolveUnknownListingIdentity\(await getProfile\(ticker\), ticker\)/);

    // Los tres estados con sus copies honestos.
    assert.match(window, /Identidad del ticker no verificada/);
    assert.match(window, /puede no ser el emisor que buscas/);
    assert.match(window, /No encontramos este ticker en nuestras fuentes/);
    assert.match(window, /No pudimos comprobar este ticker/);

    // Ningún estado fuera del master lleva CTA: el de generación solo existe
    // en el fallback posterior, reservado a empresas del master.
    const missIdx = window.indexOf('if (!masterBasics)');
    const ctaIdx = window.indexOf('<ThesisGenerateButton');
    assert.ok(missIdx > -1 && ctaIdx > missIdx, 'el CTA solo existe en el fallback del master');
    const statesBlock = window.slice(missIdx, ctaIdx);
    assert.ok(!statesBlock.includes('<ThesisGenerateButton'), 'los estados sin identidad verificada no pueden incluir el CTA');
    // El fallback del master conserva el panel de mercado completo.
    assert.ok(window.indexOf('<CompanyMarketPanel') > missIdx, 'el fallback del master conserva el panel de mercado');
});

void test('el diseño anti-homónimos sigue intacto en el snapshot de mercado', () => {
    const marketModule: string = readFileSync(new URL('../lib/actions/market-workspace.actions.ts', import.meta.url), 'utf8');
    assert.match(marketModule, /if \(!quoteSymbol\) \{/, 'quoteSymbolFor null debe seguir cortando antes del proveedor');
});

console.log('research-unknown-ticker-guard: ok');
