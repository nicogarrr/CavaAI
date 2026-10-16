import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
// @ts-expect-error TS5097: node --experimental-strip-types requiere extension explicita.
import { readSessionWhenCookies } from '../lib/anonymous-session.ts';

for (const cookie of [null, '', '   ']) {
  test(`sin Cookie (${JSON.stringify(cookie)}) no inicializa auth/DB`, async () => {
    let reads = 0;
    const result = await readSessionWhenCookies({ get: () => cookie }, async () => {
      reads++;
      throw new Error('Mongo fuera de servicio');
    });
    assert.equal(result, null);
    assert.equal(reads, 0);
  });
}
for (const cookie of ['better-auth.session_token=token', '__Secure-better-auth.session_token=token', 'unknown=1', 'malformed']) {
  test(`cualquier Cookie mantiene validación: ${cookie.split('=')[0]}`, async () => {
    const session = { user: { id: 'fixture-user' } };
    let reads = 0;
    assert.equal(await readSessionWhenCookies({ get: () => cookie }, async () => {
      reads++;
      return session;
    }), session);
    assert.equal(reads, 1);
    await assert.rejects(readSessionWhenCookies({ get: () => cookie }, async () => {
      throw new Error('session check failed');
    }), /session check failed/);
  });
}
test('la optimización solo gobierna los shells público/auth', () => {
  for (const route of ['(public)', '(auth)']) {
    const source = readFileSync(`app/${route}/layout.tsx`, 'utf8');
    assert.match(source, /readSessionWhenCookies\(requestHeaders, async \(\) => \{\s*const auth = await getAuth\(/);
    assert.match(source, /auth\.api\.getSession\(\{ headers: requestHeaders \}\)/);
  }
  const landing = readFileSync('app/(public)/page.tsx', 'utf8');
  assert.match(landing, /readSessionWhenCookies\(requestHeaders, async \(\) =>/);
  assert.match(landing, /landingTargetForSession\(Boolean\(session\?\.user\)\)/);
  const privateLayout = readFileSync('app/(root)/layout.tsx', 'utf8');
  assert.match(privateLayout, /requireAuthenticatedUser\(\)/);
  assert.doesNotMatch(privateLayout, /readSessionWhenCookies/);
});
