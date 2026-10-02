/**
 * /api/quote no puede volver.
 *
 * La ruta se borró por tres motivos honestos y ninguno se arregla parcheando:
 *
 *  1. CERO llamadas. Buscando `/api/quote` en app/, components/, lib/, hooks/,
 *     scripts/ y e2e/ no hay una sola referencia. Nadie la usaba.
 *  2. SUS CIFRAS MENTÍAN. `quote.c || 0` (y `d`, `dp`, `h`, `l`, `o`, `pc`)
 *     convertían «el proveedor no devolvió el campo» en un 0 que la UI pintaría
 *     como «sin variación». Un 0 inventado es peor que un campo ausente.
 *  3. SIN TECHO. `fetch(quoteUrl, { next: { revalidate } })` no llevaba
 *     `signal`: un Finnhub colgado dejaba la request colgada hasta el
 *     maxDuration de la función.
 *
 * Además era superficie muerta INAUDITABLE: los `route.ts` de app/ son entry
 * point de derecho, así que find-dead-code.mjs no la señalaba pese a no tener
 * consumidores. La misma cotización ya la dan las server actions con
 * frescura declarada (sanitizeFinnhubQuote + priceKind), que es lo que la UI
 * consume de verdad.
 *
 * Si algún día hace falta una API pública de cotización, que nazca con divisa,
 * frescura y timeout declarados — no resucitando este contrato.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/quote-route-dead-guard.test.ts
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.cwd();

function walk(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir)) {
        if (entry === 'node_modules' || entry.startsWith('.') || entry === 'build' || entry === 'dist') continue;
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) walk(full, out);
        else if (/\.(ts|tsx)$/.test(entry)) out.push(full);
    }
    return out;
}

test('app/api/quote/route.ts sigue muerto', () => {
    assert.equal(
        existsSync(join(ROOT, 'app', 'api', 'quote', 'route.ts')),
        false,
        'app/api/quote/route.ts volvió: 0 llamadas, || 0 inventados y sin timeout. Mira el header de este guard antes de resucitarla.',
    );
});

test('ninguna fuente llama a /api/quote', () => {
    const offenders: string[] = [];
    for (const scope of ['app', 'components', 'lib', 'hooks', 'e2e']) {
        const base = join(ROOT, scope);
        if (!existsSync(base)) continue;
        for (const file of walk(base)) {
            if (readFileSync(file, 'utf8').includes('/api/quote')) {
                offenders.push(file.slice(ROOT.length + 1));
            }
        }
    }
    assert.deepEqual(offenders, [], `referencias a /api/quote: ${offenders.join(', ')}`);
});
