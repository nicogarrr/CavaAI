/**
 * Quick win UX 6: /research ordenado por relevancia
 * (tesis > cartera > watchlist > resto).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { researchRelevanceKey, sortCompaniesByRelevance } from '../lib/research/relevance.ts';

const page = readFileSync('app/(root)/research/page.tsx', 'utf8');

test('los buckets de relevancia son tesis > cartera > watchlist > resto', () => {
    const portfolio = new Set(['COST']);
    const watchlist = new Set(['NFLX']);
    assert.equal(researchRelevanceKey('AAPL', true, portfolio, watchlist), 0);
    assert.equal(researchRelevanceKey('COST', true, portfolio, watchlist), 0, 'la tesis gana a la cartera');
    assert.equal(researchRelevanceKey('cost', false, portfolio, watchlist), 1, 'normalización');
    assert.equal(researchRelevanceKey('NFLX', false, portfolio, watchlist), 2);
    assert.equal(researchRelevanceKey('AAPL', false, portfolio, watchlist), 3);
});

test('el orden es estable: bucket y luego ticker', () => {
    const companies = [{ ticker: 'ZZZ' }, { ticker: 'AAA' }, { ticker: 'MID' }, { ticker: 'TESIS' }];
    const ordered = sortCompaniesByRelevance(
        companies,
        (company) => company.ticker === 'TESIS',
        new Set(['ZZZ']),
        new Set(['MID']),
    );
    assert.deepEqual(ordered.map((company) => company.ticker), ['TESIS', 'ZZZ', 'MID', 'AAA']);
    assert.deepEqual(companies.map((company) => company.ticker), ['ZZZ', 'AAA', 'MID', 'TESIS'], 'no muta la entrada');
});

test('la página degrada sin fabricar pertenencia ni tesis', () => {
    // Sin snapshots: hasThesis es false para todas (nunca afirma tesis inexistentes).
    assert.match(page, /snapshots = null;/);
    assert.match(page, /snapshots\?\.snapshots\[company\.ticker\]\?\.latest_thesis != null/);
    // Lecturas de contexto degradan a vacío, no a badges/orden fabricados.
    assert.match(page, /getPortfolioSummary\(userId\)\.catch\(\(\) => null\)/);
    assert.match(page, /getWatchlist\(\)\.catch\(\(\) => \[\]/);
    // Solo posiciones abiertas cuentan como cartera (misma semántica que los badges).
    assert.match(page, /holding\.quantity !== 0/);
});

test('los snapshots se piden en lotes del tope del endpoint y se reutilizan', () => {
    assert.match(page, /SNAPSHOT_BATCH_SIZE = 50/);
    // Una sola llamada al endpoint (dentro del mapa de lotes): las tarjetas
    // reutilizan el mismo mapa, sin segunda llamada tras paginar.
    assert.equal((page.match(/getResearchCompanySnapshots\(/g) ?? []).length, 1);
    assert.match(page, /sortCompaniesByRelevance\(/);
});
