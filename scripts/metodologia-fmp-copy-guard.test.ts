import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const metodologia = readFileSync('app/(public)/metodologia/page.tsx', 'utf8');
const ficha = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');

test('F325: la metodología describe el uso real de FMP (solo US), no un retiro inexistente', () => {
    // La ficha ofrece «Refrescar financieros (FMP)» en tickers US mientras la
    // metodología decía «FMP retirado, ningún cálculo depende de FMP».
    assert.match(ficha, /Refrescar financieros \(FMP\)/);
    assert.doesNotMatch(metodologia, /FMP retirado/);
    assert.doesNotMatch(metodologia, /Ningún cálculo actual\s+depende de FMP/);
    assert.match(metodologia, /FMP solo cubre mercado US/);
    // El copy no promete restriccion en la app ni cobertura universal
    // EDGAR/ESEF: FMP rechaza fuera de US y la cobertura regulatoria
    // depende del emisor.
    assert.match(metodologia, /intenta el refresco con FMP en cualquier ticker/);
    assert.match(metodologia, /cuando el emisor reporta a alguna de las dos/);
    assert.doesNotMatch(metodologia, /el resto se sirve de SEC EDGAR y ESEF/);
});
