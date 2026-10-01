/**
 * F391: aprobar/rechazar una tesis debe refrescar memo e historial.
 * Ejecución: node --experimental-strip-types --test scripts/thesis-approve-refresh-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const button = readFileSync(join(root, 'components/research/ThesisApproveButton.tsx'), 'utf8');

describe('ThesisApproveButton', () => {
    it('refresca la ruta tras decidir con éxito', () => {
        assert.match(button, /useRouter\(\)/);
        const successAt = button.indexOf('toast.success');
        const refreshAt = button.indexOf('router.refresh()');
        assert.ok(refreshAt > successAt && successAt > 0);
        assert.ok(refreshAt < button.indexOf('} catch'));
    });
});
