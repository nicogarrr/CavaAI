/**
 * Guard F288: «Aprobar tesis» deshabilitado (sin versiones, B17) NO puede
 * rendirse con la variante primaria: el bg casi blanco al 50% de opacidad
 * seguía siendo lo más luminoso de /research?view=tesis y se leía como la
 * acción principal activa (affordance engañosa). Deshabilitado debe ser
 * outline + leyenda visible que explique por qué no hay nada que aprobar.
 * Ejecución: node --experimental-strip-types --test scripts/thesis-approve-affordance-guard.test.ts
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source: string = readFileSync(new URL('../components/research/ThesisApproveButton.tsx', import.meta.url), 'utf8');

// Acotamos al botón de aprobar (entre su apertura y la de Rechazar).
const approveStart = source.indexOf("onClick={() => decide('approved')}");
const rejectStart = source.indexOf("onClick={() => decide('rejected')}");
assert.ok(approveStart > -1 && rejectStart > approveStart, 'deben existir ambos botones');
const approveTag = source.slice(source.lastIndexOf('<Button', approveStart), approveStart);

void test('el botón Aprobar no usa la variante primaria cuando está deshabilitado', () => {
    // La variante debe ser condicional al estado disabled; un botón aprobar
    // sin `variant` renderiza `default` (primario casi blanco) siempre.
    assert.match(
        approveTag,
        /variant=\{disabled \? 'outline' : 'default'\}/,
        'Aprobar deshabilitado debe rendirse como outline, no como primario',
    );
});

void test('el estado sin versiones se explica con una leyenda visible', () => {
    // Tooltip solo no basta: el motivo del disabled debe leerse en pantalla.
    assert.match(
        source,
        /\{disabled \? \(\s*<span[^>]*>Sin versiones de tesis que aprobar o rechazar\./,
        'debe existir la leyenda visible «Sin versiones de tesis que aprobar o rechazar.» cuando disabled',
    );
});

console.log('thesis-approve-affordance-guard: ok');
