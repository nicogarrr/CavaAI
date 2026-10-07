import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const page = readFileSync('app/(root)/research/workflows/page.tsx', 'utf8');
const summaries = readFileSync('lib/research/workflow-summary.ts', 'utf8');
test('el catálogo conserva alcance técnico sin volcarlo por defecto', () => {
    assert.match(page, /workflowSummary\(workflow\.name\)/);
    const details = page.slice(page.indexOf('<details'), page.indexOf('</details>'));
    assert.match(details, /Detalles técnicos/);
    assert.match(details, /workflow\.truth/);
    assert.match(details, /workflow\.steps\.map/);
    assert.doesNotMatch(details, /<details[^>]*\bopen\b/);
    assert.doesNotMatch(page, /invoca al resto vía POST|POST \/api\/workflows/);
    assert.match(page, /aria-label="Ticker de la empresa"/);
    assert.match(summaries, /No publica ni modifica la tesis/);
    assert.match(summaries, /no publica por sí sola una tesis nueva/);
});
