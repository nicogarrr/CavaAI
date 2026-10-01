/**
 * F388: parseInt truncaba "30,5" a 30 y lo guardaba en silencio.
 * Ejecución: node --experimental-strip-types --test scripts/plan-horizon-parse-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dialog = readFileSync(join(root, 'components/plan/PlanSetupDialog.tsx'), 'utf8');

describe('horizonte del plan', () => {
    it('no usa parseInt (trunca decimales en silencio)', () => {
        assert.ok(!dialog.includes('Number.parseInt(horizon'));
        assert.match(dialog, /\/\^\\d\+\$\/\.test\(horizon\.trim\(\)\)/);
    });
});
