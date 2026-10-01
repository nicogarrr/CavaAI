/**
 * F387: guardar el plan no actualizaba la tarjeta (estado copiado una vez y
 * router.refresh conserva el estado de cliente). RecordDetail debe sincronizar
 * su estado con la prop `record`.
 * Ejecución: node --experimental-strip-types --test scripts/record-detail-sync-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const views = readFileSync(join(root, 'components/data/RecordViews.tsx'), 'utf8');

describe('RecordDetail', () => {
    it('sincroniza el estado con la prop record', () => {
        assert.match(views, /useEffect\(\(\) => \{\s*setData\(record\);\s*\}, \[record\]\)/);
    });
});
