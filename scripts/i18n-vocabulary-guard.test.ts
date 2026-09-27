/**
 * F181 + copy insider: vocabulario ES fijo. «compostadora» y «ingestar»
 * no son español; «Rhino» era un resto sin sentido en la explicacion de
 * senales insider (el backend dice CEO/CFO/«C-suite»).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const es = readFileSync('lib/i18n/es.json', 'utf8');
const knowledge = readFileSync('app/(root)/knowledge/page.tsx', 'utf8');
const insider = readFileSync('app/(root)/insider/page.tsx', 'utf8');

test('el vocabulario ES no recae en compostadora/ingestar/Rhino', () => {
    assert.doesNotMatch(es, /compostadora/i);
    assert.match(es, /compounders de calidad/);
    assert.doesNotMatch(knowledge, /ingestar/i);
    assert.doesNotMatch(insider, /Rhino/);
    assert.match(insider, /CEO,?\s*CFO u otro C-suite/);
});
