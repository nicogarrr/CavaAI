/**
 * F384/F385: el snapshot «anterior» debe ser válido, de la misma estrategia y
 * de un mes anterior; un pick null ya no pasa el guard (rompía diffSnapshots).
 * Ejecución: node --experimental-strip-types --test scripts/propicks-snapshot-validation-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { isMonthlySnapshot, previousSnapshotError } from '../components/proPicks/snapshotValidation.ts';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const base: any = {
    kind: 'cavaai-propicks-monthly-snapshot',
    version: 1,
    month: '2026-08',
    strategyId: 'adaptive',
    generatedAt: '2026-08-31T00:00:00Z',
    picks: [{ symbol: 'AAA', company: 'A' }],
};

describe('validación de snapshots mensuales', () => {
    it('acepta un snapshot bien formado', () => {
        assert.equal(isMonthlySnapshot(base), true);
    });
    it('F385: picks con null o sin símbolo no pasan el guard', () => {
        assert.equal(isMonthlySnapshot({ ...base, picks: [null] }), false);
        assert.equal(isMonthlySnapshot({ ...base, picks: [{ company: 'x' }] }), false);
        assert.equal(isMonthlySnapshot({ ...base, picks: [{ symbol: '' }] }), false);
    });
    it('mes mal formado o sin estrategia no pasa', () => {
        assert.equal(isMonthlySnapshot({ ...base, month: 'agosto' }), false);
        assert.equal(isMonthlySnapshot({ ...base, strategyId: undefined }), false);
    });
    it('F384: otra estrategia se rechaza', () => {
        assert.match(previousSnapshotError(base, 'value', '2026-09') ?? '', /otra estrategia/);
    });
    it('F384: mes actual o futuro se rechaza como anterior', () => {
        assert.match(previousSnapshotError({ ...base, month: '2026-09' }, 'adaptive', '2026-09') ?? '', /mes anterior/);
        assert.match(previousSnapshotError({ ...base, month: '2026-10' }, 'adaptive', '2026-09') ?? '', /mes anterior/);
    });
    it('mismo strategy y mes anterior es válido', () => {
        assert.equal(previousSnapshotError(base, 'adaptive', '2026-09'), null);
    });
});
