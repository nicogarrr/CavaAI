import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const quote = readFileSync('components/research/CompanyHeaderQuote.tsx', 'utf8');
const page = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');
describe('ficha: cifra grande y métricas compactas', () => {
    it('precio grande y variación en píldora, neutro si es cero', () => {
        assert.match(quote, /text-4xl/);
        assert.match(quote, /rounded-full/);
        assert.match(quote, /signBase > 0/);
        assert.match(quote, /signBase < 0/);
        assert.match(quote, /text-emerald-300/);
        assert.match(quote, /text-red-300/);
    });
    it('cuatro métricas verificadas de la cotización, sin adivinar múltiplos', () => {
        assert.match(quote, /company-metric-strip/);
        for (const label of ['Apertura', 'Máximo', 'Mínimo', 'Cierre anterior']) assert.ok(quote.includes(label));
        assert.match(quote, /value == null \? NA : formatMoney/);
        assert.match(quote, /divide-gray-800/);
        assert.match(quote, /isValidCurrencyCode\(currency\)/);
    });
    it('pestañas limpias sin borrar rutas ni módulos', () => {
        assert.match(page, /activeModule.group === group.key \? 'border-teal-300 text-gray-100'/);
        for (const view of ['resumen', 'tesis', 'financieros', 'modelo', 'evidencia', 'seguimiento']) assert.ok(page.includes(`key: '${view}'`));
        assert.doesNotMatch(page, /captura de solo lectura/);
    });
});
