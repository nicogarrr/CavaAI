import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/ownership/page.tsx', 'utf8');

test('F327: la vista /ownership no pierde tildes en su copy', () => {
    assert.doesNotMatch(page, /nueva posicion/);
    assert.doesNotMatch(page, /se declaro\)/);
    assert.doesNotMatch(page, /su ultimo informe/);
    assert.doesNotMatch(page, /gestor aun no/);
    assert.match(page, /nueva posición/);
    assert.match(page, /se declaró\)/);
    assert.match(page, /su último informe/);
    assert.match(page, /gestor aún no/);
});
