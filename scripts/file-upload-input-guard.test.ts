import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const component = readFileSync('components/forms/FileUploadInput.tsx', 'utf8');
const uiInput = readFileSync('components/ui/input.tsx', 'utf8');

test('F303: el input file oculto es nativo con sr-only, sin la base w-full de ui/Input', () => {
    // ui/Input impone w-full/h-10/borde en su clase base; con sr-only el
    // width:100% ganaba al width:1px (sr-only se ordena antes en el
    // stylesheet de Tailwind) y la caja invisible desbordaba el viewport.
    assert.match(component, /<input\n[\s\S]*?type="file"\n[\s\S]*?className="sr-only"/);
    assert.doesNotMatch(component, /from '@\/components\/ui\/input'/);
});

test('F303: ui/Input sigue imponiendo w-full (el conflicto vive en su base)', () => {
    assert.match(uiInput, /h-10 w-full/);
});

test('F303: el disparador visible sigue siendo el label asociado', () => {
    assert.match(component, /<label\n[\s\S]*?htmlFor=\{inputId\}/);
});
