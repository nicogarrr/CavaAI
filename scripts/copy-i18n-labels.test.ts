/**
 * Batch copy/i18n honestidad (F208/F174/F175): las cadenas internas o en
 * inglés no se pintan crudas - sectores de la cabecera de /risk, tipos de
 * instrumento del buscador, tiers y tipos de evento de /research/news.
 * Ejecución: node --experimental-strip-types --test scripts/copy-i18n-labels.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { etiquetaSector, etiquetaTierFuente, etiquetaTipoEvento, etiquetaTipoInstrumento } from '../lib/labels.ts';

void test('sectores de la cabecera de exposición se traducen (F208)', () => {
    assert.equal(etiquetaSector('Communication Services'), 'Servicios de comunicación');
    assert.equal(etiquetaSector('Sector Inventado'), 'Sector Inventado');
});

void test('tipos de instrumento del buscador en español (F174)', () => {
    assert.equal(etiquetaTipoInstrumento('Common Stock'), 'Acción ordinaria');
    assert.equal(etiquetaTipoInstrumento('Canadian DR'), 'Recibo de depósito canadiense');
    assert.equal(etiquetaTipoInstrumento('Otro tipo'), 'Otro tipo');
});

void test('tiers y tipos de evento sin tokens internos (F175)', () => {
    assert.equal(etiquetaTierFuente('tier_1_regulatory'), 'Regulatoria · T1');
    assert.equal(etiquetaTipoEvento('regulatory'), 'Regulatorio');
    assert.equal(etiquetaTipoEvento('earnings'), 'Resultados');
    assert.equal(etiquetaTierFuente('tier_raro'), 'tier_raro');
});

void test('los componentes usan las etiquetas, no la cadena cruda', () => {
    const risk = readFileSync('components/risk/RiskDashboardView.tsx', 'utf8');
    assert.match(risk, /exposureRecord\(value, etiquetaSector\)/);
    assert.doesNotMatch(risk, /hace falta historia de precios/);
    const search = readFileSync('components/SearchCommand.tsx', 'utf8');
    assert.match(search, /etiquetaTipoInstrumento\(stock\.type\)/);
    const news = readFileSync('app/(root)/research/news/page.tsx', 'utf8');
    assert.match(news, /etiquetaTierFuente\(event\.source_tier\)/);
    assert.match(news, /etiquetaTipoEvento\(event\.event_type\)/);
});
