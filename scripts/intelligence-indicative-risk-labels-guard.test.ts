/**
 * F6: con twr_is_exact=false, Sharpe y caída máxima salen de la MISMA serie
 * indicativa (pesos estáticos actuales) que el TWR (portfolio_intelligence_
 * service: portfolio_returns = indicative_returns). Solo el TWR se rotulaba
 * como indicativo; las tres tarjetas deben llevar el mismo aviso.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/portfolio/intelligence/page.tsx', 'utf8');

test('Sharpe y caída máxima se rotulan indicativos cuando el TWR no es exacto', () => {
    assert.match(page, /twr_is_exact \? 'Sharpe' : 'Sharpe indicativo'/);
    assert.match(page, /twr_is_exact \? 'Máx\. caída' : 'Máx\. caída indicativa'/);
    assert.match(page, /twr_is_exact \? 'TWR diario' : 'TWR indicativo'/);
});
