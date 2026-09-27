import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync('app/(public)/page.tsx', 'utf8');

test('la raiz redirige al panel solo cuando hay sesion (semantica del helper)', async () => {
    // @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
    const { landingTargetForSession } = await import('../lib/public/landing-target.ts');
    assert.equal(landingTargetForSession(true), '/inicio');
    assert.equal(landingTargetForSession(false), null);
});

test('la landing resuelve la sesion en servidor y usa el helper', () => {
    assert.match(page, /getSession\(\{ headers: await headers\(\) \}\)/);
    assert.match(page, /landingTargetForSession\(Boolean\(session\?\.user\)\)/);
    assert.match(page, /if \(target\) redirect\(target\)/);
});

test('sin sesion resoluble nunca hay redirect (cookie caducada o auth caida)', () => {
    // la sesion se resuelve con .catch(() => null): auth caida => landing
    assert.match(page, /getAuth\(\)\.catch\(\(\) => null\)/);
    assert.match(page, /getSession\([\s\S]*?\.catch\(\(\) => null\)/);
    // y el bypass e2e mantiene la landing alcanzable en los tests de navegador
    assert.match(page, /E2E_AUTH_BYPASS === '1'/);
});
