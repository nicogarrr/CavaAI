import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const source = readFileSync('lib/actions/investors.actions.ts', 'utf8');
test('las lecturas 13F usan timeout común y no convierten 4xx a caída de motor', () => {
    assert.match(source, /import \{ researchRequest \} from '@\/lib\/research\/client'/);
    assert.match(source, /return researchRequest<T>\(path, \{ fast: true \}\)/);
    assert.doesNotMatch(source, /await fetch\(|ExternalAPIError|researchIdentityHeaders/);
});
test('solo un 404 de API convierte una ficha en no encontrada', () => {
    assert.match(source, /error instanceof AppError && error\.code === 'RESEARCH_API_ERROR' && error\.statusCode === 404\) return null/);
    assert.match(source, /throw error;/);
    assert.doesNotMatch(source, /error\.message\.startsWith\('Not found:'/);
});
