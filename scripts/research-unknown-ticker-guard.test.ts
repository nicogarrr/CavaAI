/**
 * Guard F286: /research/<ticker> fuera del master NUNCA devuelve 404 desde
 * este camino ni ofrece CTA «Generar tesis» sobre una identidad no
 * verificada. Procedencia exacta de la señal: getResearchCompanySnapshot solo
 * devuelve null ante el 404 de /api/companies/{ticker}/snapshot, y ese 404 en
 * backend es «compañía ausente del master» (resolve_company) — una empresa
 * del master sin research recibe snapshot construido. Política de veracidad:
 * ninguna respuesta del proveedor prueba la inexistencia del emisor buscado
 * (perfil {} = Finnhub no conoce el símbolo), y un perfil con nombre prueba
 * que el símbolo existe en alguna bolsa, no que sea ese emisor (ALM ->
 * Almonty US, no Almirall/BME). Tres estados honestos sin CTA.
 * Ejecución: node --experimental-strip-types --test scripts/research-unknown-ticker-guard.test.ts
 */
import test from 'node:test';
// @ts-expect-error TS5097
import { drainRejection } from '../lib/research/drain-rejection.ts';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { resolveUnknownListingIdentity } from '../lib/research/unknown-listing.ts';

/* ------------------------------------------------------------------ *
 * Detector de drenaje.
 *
 * El manejador de rechazo tiene que ir PEGADO a la creacion de la
 * promesa: entre `const xPromise =` y `drainRejection(xPromise)` no puede
 * haber un `await`, porque durante ese `await` la promesa puede rechazar y
 * quedar sin manejar (unhandledRejection tumba el proceso en Node).
 *
 * Lo que NO se comprueba es la posicion respecto a las demás fases. FIX6
 * movio el lanzamiento del market DESPUES de `await snapshotPromise` (para
 * darle los `basics` del snapshot y quitar el round-trip redundante de
 * `/api/companies/{ticker}`), y eso es correcto: el market no dependia del
 * snapshot, dependia de sus `basics`, y en master-miss ya no se lanza. Un
 * guard que exigiera «el drenaje antes del primer await de la pagina»
 * estaba fijando la cadena vieja y habria tumbado esa mejora.
 * ------------------------------------------------------------------ */

/** Deja el codigo, borra comentarios (y solo comentarios), sin mover indices. */
function sinComentarios(source: string): string {
  let out = '';
  let i = 0;
  while (i < source.length) {
    const ch = source[i];
    const dos = source.slice(i, i + 2);
    if (dos === '//') {
      const fin = source.indexOf('\n', i);
      const hasta = fin === -1 ? source.length : fin;
      out += ' '.repeat(hasta - i);
      i = hasta;
      continue;
    }
    if (dos === '/*') {
      const fin = source.indexOf('*/', i + 2);
      const hasta = fin === -1 ? source.length : fin + 2;
      out += source.slice(i, hasta).replace(/[^\n]/g, ' ');
      i = hasta;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      let j = i + 1;
      while (j < source.length && source[j] !== ch) {
        if (source[j] === '\\') j += 1;
        j += 1;
      }
      out += source.slice(i, j + 1);
      i = j + 1;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}

/**
 * Promesas cuya cadena lleva `drainRejection` y tienen un `await` entre la
 * creacion y el drenaje.
 */
export function findDrenajesDiferidos(source: string): string[] {
  const code = sinComentarios(source);
  const findings: string[] = [];
  const created = /const\s+(\w*[Pp]romise)\s*=/g;
  let match: RegExpExecArray | null;
  while ((match = created.exec(code)) !== null) {
    const name = match[1]!;
    const drainAt = code.indexOf(`drainRejection(${name})`);
    // Sin `drainRejection` no se comprueba adyacencia: la promesa se drena con
    // un `.catch` en la propia cadena (`watchlistPromise`) o se recoge en un
    // `try`/`catch` (`snapshotPromise`), y son invariantes distintos.
    if (drainAt === -1) continue;
    const entre = code.slice(match.index, drainAt);
    if (/\bawait\b/.test(entre)) {
      findings.push(
        `${name}: hay un await entre la creacion (offset ${match.index}) y el drenaje (offset ${drainAt}): ventana de unhandledRejection`,
      );
    }
  }
  return findings;
}

void test('perfil sin nombre propio -> not-in-sources', () => {
    assert.deepEqual(resolveUnknownListingIdentity({}, 'ZZZZ'), { kind: 'not-in-sources' });
    assert.deepEqual(resolveUnknownListingIdentity({ name: '   ' }, 'ZZZZ'), { kind: 'not-in-sources' });
    assert.deepEqual(resolveUnknownListingIdentity({ name: 'ZZZZ' }, 'ZZZZ'), { kind: 'not-in-sources' });
});

void test('perfil del ticker desnudo con nombre -> unverified (emisor ambiguo)', () => {
    assert.deepEqual(
        resolveUnknownListingIdentity({ name: 'Almonty Industries' }, 'ALM'),
        { kind: 'unverified', providerName: 'Almonty Industries' },
    );
});

void test('proveedor no disponible -> unavailable', () => {
    assert.deepEqual(resolveUnknownListingIdentity(null, 'VZ'), { kind: 'unavailable' });
});

void test('la procedencia master-miss es exacta: null solo por 404 y 404 solo por compañía ausente', () => {
    // Frontend: getResearchCompanySnapshot devuelve null SOLO ante 404; el
    // resto de fallos se propaga (null no puede significar «error»).
    const actions: string = readFileSync(new URL('../lib/actions/research.actions.ts', import.meta.url), 'utf8');
    const fnStart = actions.indexOf('export async function getResearchCompanySnapshot');
    assert.ok(fnStart > -1);
    const fn = actions.slice(fnStart, actions.indexOf('\n}', fnStart));
    assert.match(fn, /error\.statusCode === 404\) return null/);
    assert.match(fn, /throw error/, 'los fallos que no son 404 deben propagarse');

    // Backend: /{ticker}/snapshot 404 solo cuando resolve_company no
    // encuentra la compañía; si existe, construye el snapshot (con o sin
    // research), así que snapshot null nunca es «master sin research».
    const routes: string = readFileSync(new URL('../data-engine/app/api/routes/companies.py', import.meta.url), 'utf8');
    const routeStart = routes.indexOf('"/{ticker}/snapshot"');
    assert.ok(routeStart > -1);
    const route = routes.slice(routeStart, routes.indexOf('@router.', routeStart));
    assert.match(route, /if not company:\s*\n\s*raise HTTPException\(status_code=404/);
    assert.match(route, /CompanySnapshotService\(\)\.build\(db, company\)/);
});

void test('la página pinta los tres estados sin 404, sin CTA y sin panel fuera del master', () => {
    const source: string = readFileSync(new URL('../app/(root)/research/[ticker]/page.tsx', import.meta.url), 'utf8');
    assert.ok(!source.includes('notFound'), 'este camino nunca devuelve 404 (ninguna respuesta prueba inexistencia)');

    const branchStart = source.indexOf('if (!snapshot) {');
    const branchEnd = source.indexOf('const company = snapshot.company;', branchStart);
    assert.ok(branchStart > -1 && branchEnd > branchStart, 'debe existir la rama if (!snapshot)');
    const branch = source.slice(branchStart, branchEnd);

    // La rama resuelve la identidad con el perfil del proveedor y pinta los
    // tres estados honestos.
    assert.match(branch, /resolveUnknownListingIdentity\(await getProfile\(ticker\), ticker\)/);
    assert.match(branch, /Identidad del ticker no verificada/);
    assert.match(branch, /puede no ser el emisor que buscas/);
    assert.match(branch, /No encontramos este ticker en nuestras fuentes/);
    assert.match(branch, /No pudimos comprobar este ticker/);

    // Fuera del master no hay CTA de generación, ni panel de mercado N/D,
    // ni una segunda consulta al master (la señal ya es exacta).
    assert.ok(!branch.includes('<ThesisGenerateButton'), 'sin CTA de generación fuera del master');
    assert.ok(!branch.includes('<CompanyMarketPanel'), 'sin panel N/D fuera del master');
    assert.ok(!branch.includes('getCompanyMarketSnapshot'), 'sin fetch de mercado fuera del master');
    assert.ok(!branch.includes('getResearchCompanyBasics'), 'sin segunda consulta al master: el 404 del snapshot ya es la señal');
});

void test('el drenaje se adjunta EN CREACIÓN, sin ningún await intermedio', () => {
    const page: string = readFileSync(new URL('../app/(root)/research/[ticker]/page.tsx', import.meta.url), 'utf8');
    assert.deepEqual(
        findDrenajesDiferidos(page),
        [],
        'cada promesa drenada tiene que llevar su manejador pegado a su creación: un await entre las dos abre ventana de unhandledRejection',
    );
    // Las promesas del grafo de la ficha siguen adjuntando su drenaje.
    for (const nombre of ['moatPromise', 'viewPromise', 'chatPromise', 'marketPromise']) {
        assert.ok(page.includes(`const ${nombre} =`), `debe existir ${nombre}`);
        assert.ok(page.includes(`drainRejection(${nombre})`), `${nombre} debe drenar su rechazo`);
    }
});

void test('el detector ve un await entre la creación y el drenaje (caso negativo)', () => {
    const conHueco = `
const marketPromise = getCompanyMarketSnapshot(ticker);
const snapshot = await snapshotPromise;
drainRejection(marketPromise);`;
    assert.equal(
        findDrenajesDiferidos(conHueco).length,
        1,
        `un await intermedio tiene que marcar la promesa: ${JSON.stringify(findDrenajesDiferidos(conHueco))}`,
    );
    assert.match(findDrenajesDiferidos(conHueco)[0]!, /^marketPromise: hay un await entre la creacion \(offset \d+\) y el drenaje \(offset \d+\)/);
    // Y sin ese await, la misma forma de codigo no se marca.
    assert.deepEqual(
        findDrenajesDiferidos(`
const marketPromise = getCompanyMarketSnapshot(ticker);
drainRejection(marketPromise);
const snapshot = await snapshotPromise;`),
        [],
        'drenar pegado a la creacion es correcto aunque el await venga despues',
    );
});

void test('en master-miss el market ni se lanza: la rama retorna antes', () => {
    const page: string = readFileSync(new URL('../app/(root)/research/[ticker]/page.tsx', import.meta.url), 'utf8');
    const branchStart = page.indexOf('if (!snapshot) {');
    const branchEnd = page.indexOf('const company = snapshot.company;', branchStart);
    assert.ok(branchStart > -1 && branchEnd > branchStart, 'debe existir la rama if (!snapshot)');
    const branch = page.slice(branchStart, branchEnd);
    // La rama no cae: retorna. Con esto, que el market se lance despues del
    // `const company` significa que en master-miss no se lanza nunca.
    assert.match(branch, /return\s*\(/, 'la rama de master-miss retorna: no hay camino que siga al market');
    const launched = page.indexOf('const marketPromise =');
    assert.ok(
        launched > branchEnd,
        `el market se lanza DESPUES de la rama de master-miss (${branchEnd}), no antes: en master-miss no se pide (offset ${launched})`,
    );
    // Y la rama no se lleva por delante una consulta al master que ya no hace falta.
    assert.ok(!branch.includes('getCompanyMarketSnapshot'), 'sin fetch de mercado en la rama de master-miss');
    assert.ok(!branch.includes('getResearchCompanyBasics'), 'sin segunda consulta al master: el 404 del snapshot ya es la senal');
});

void test('drainRejection: sin unhandledRejection aunque nadie consuma, y el consumidor sigue recibiendo el error', async () => {
    let unhandled = 0;
    const listener = () => {
        unhandled += 1;
    };
    process.on('unhandledRejection', listener);
    try {
        drainRejection(Promise.reject(new Error('proveedor caído')));
        await new Promise((resolve) => setImmediate(resolve));
        await new Promise((resolve) => setImmediate(resolve));
        assert.equal(unhandled, 0, 'ningún rechazo queda sin manejar');
        const consumida = Promise.reject(new Error('el consumidor la ve'));
        drainRejection(consumida);
        await assert.rejects(consumida, /el consumidor la ve/, 'la propagación al consumidor no cambia');
    } finally {
        process.off('unhandledRejection', listener);
    }
});

void test('el diseño anti-homónimos sigue intacto en el snapshot de mercado', () => {
    const marketModule: string = readFileSync(new URL('../lib/actions/market-workspace.actions.ts', import.meta.url), 'utf8');
    assert.match(marketModule, /if \(!quoteSymbol\) \{/, 'quoteSymbolFor null debe seguir cortando antes del proveedor');
});


void test('los escapes E2E conocen los tres estados honestos', () => {
    // audit-closure vuelve antes si la ficha no ofrece workspace: los tres
    // estados de F286 deben estar en su lista o los tests exigirán controles
    // de tesis en una página que honestamente no los tiene.
    const spec: string = readFileSync(new URL('../e2e/audit-closure.spec.ts', import.meta.url), 'utf8');
    assert.match(spec, /Identidad del ticker no verificada/);
    assert.match(spec, /No encontramos este ticker/);
    assert.match(spec, /No pudimos comprobar este ticker/);
});

console.log('research-unknown-ticker-guard: ok');
