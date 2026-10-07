import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(root)/propicks/page.tsx', 'utf8');
const state = readFileSync('components/proPicks/ProPicksLoadError.tsx', 'utf8');

test('ProPicks no declara desconectado el motor por un fallo local', () => {
    assert.doesNotMatch(page, /BackendOffline|isBackendUnavailableError/);
    assert.match(page, /EXTERNAL_API_ERROR/);
    assert.match(page, /RESEARCH_API_ERROR/);
    assert.match(page, /throw error;/);
    assert.doesNotMatch(state, /Motor de análisis desconectado/);
    assert.match(state, /statusCode === 429/);
    assert.match(state, /statusCode === 401 \|\| statusCode === 403/);
    assert.match(state, /statusCode >= 400 && statusCode < 500/);
    assert.match(state, /fallo temporal de esta lectura/);
    assert.match(state, /href="\/propicks"/);
});
