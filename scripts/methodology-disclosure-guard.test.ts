/**
 * Quick win UX 2: los muros de metodología (/propicks, /risk, backtesting)
 * quedan colapsados en un desplegable nativo, cerrado por defecto en todos
 * los viewports y sin JS de cliente.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const disclosure = readFileSync('components/ui/methodology-disclosure.tsx', 'utf8');
const propicks = readFileSync('app/(root)/propicks/page.tsx', 'utf8');
const risk = readFileSync('app/(root)/risk/page.tsx', 'utf8');
const walkforward = readFileSync('components/proPicks/WalkForwardResults.tsx', 'utf8');

test('el desplegable es nativo, sin JS y cerrado por defecto', () => {
    assert.ok(!disclosure.includes("'use client'"), 'el desplegable no necesita JS de cliente');
    assert.match(disclosure, /<details className="group /);
    assert.match(disclosure, /<summary /);
    assert.ok(!/<details[^>]*\bopen\b/.test(disclosure), 'no debe abrirse por defecto en ningún viewport');
    // Chevron rota solo cuando el details está abierto (group-open).
    assert.match(disclosure, /group-open:rotate-180/);
    // El icono de ayuda marca el patrón «?».
    assert.match(disclosure, /CircleHelp/);
});

test('propicks colapsa el muro del embudo y mantiene su copy íntegro', () => {
    assert.match(propicks, /<MethodologyDisclosure>/);
    assert.match(propicks, /import \{ MethodologyDisclosure \} from '@\/components\/ui\/methodology-disclosure';/);
    // El copy explicativo no se borra: se mueve dentro del desplegable.
    assert.match(propicks, /El embudo v1 puntúa cada categoría cuando hay datos/);
    assert.match(propicks, /baseline\s+walk-forward aparte/);
    // Y ya no es un párrafo suelto en la cabecera.
    assert.ok(!/<p className="text-sm text-gray-500">/.test(propicks), 'queda un muro suelto en la cabecera de propicks');
});

test('risk deja una línea de orientación y colapsa alcance y límites', () => {
    assert.match(risk, /<MethodologyDisclosure title="Alcance y límites">/);
    // La orientación de una línea sigue visible.
    assert.match(risk, /Pesos, concentración \(top 1 y top 5\)/);
    // El detalle (qué NO calcula + salidas) vive dentro del desplegable.
    assert.match(risk, /Esta página no calcula volatilidad, drawdown ni VaR/);
});

test('el backtesting colapsa su bloque Metodología', () => {
    assert.match(walkforward, /<MethodologyDisclosure title="Metodología del backtest">/);
    assert.match(walkforward, /Walk-forward mensual: cada corte usa únicamente precios de cierre anteriores/);
    // Sin cabecera duplicada del bloque antiguo.
    assert.ok(!/<h4 className="text-sm font-semibold text-gray-300">Metodología<\/h4>/.test(walkforward));
});
