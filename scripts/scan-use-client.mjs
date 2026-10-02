/**
 * D2c: escaner de `'use client'` — inventario y clasificacion A/B/C/D.
 *
 * La deteccion vive en `scripts/use-client-audit.mjs`, que es el MISMO modulo
 * que usa el guard permanente `scripts/no-useless-use-client.test.ts`. Este
 * fichero solo anade encima la capa de lectura humana: clases, tabla y motivos.
 *
 * Clases:
 *   A  `'use client'` justificado (senal propia o depende de un modulo cliente)
 *   B  `'use client'` innecesario -> candidato a Server Component
 *   C  ambiguo: la unica justificacion es que un Client Component lo importa,
 *      asi que ya es cliente por herencia y quitarla no ahorra un byte
 *   D  ya es Server Component (sin directiva)
 *
 * Uso: node scripts/scan-use-client.mjs [--json] [--verbose] [--only=B]
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { auditRepo } from './use-client-audit.mjs';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SCAN_ROOTS = ['components', 'app', 'hooks', 'lib'];

const rows = auditRepo(REPO_ROOT, SCAN_ROOTS).map((r) => {
  let cls;
  let why;
  if (r.hasUseClient) {
    // La decision A/C sale de `justified` del modulo compartido, el MISMO
    // campo que lee el guard. Si aqui se recalculara con otro criterio, el
    // inventario de la revision y el guard dejarian de decir lo mismo.
    if (r.justified) {
      cls = 'A';
      why = r.reasons.join(', ');
    } else if (r.inheritedFromClient) {
      cls = 'C';
      why = 'sin senal propia; ya es cliente por herencia (importado por un Client Component)';
    } else {
      cls = 'B';
      why = 'ninguna senal cliente';
    }
  } else {
    cls = 'D';
    why = 'sin directiva (ya servidor)';
    if (r.hardSignals.length) why += ` — ojo: usa ${r.hardSignals.join(', ')} pero no declara 'use client' (hereda de un padre)`;
  }
  return { ...r, cls, why };
});

rows.sort((a, b) => a.rel.localeCompare(b.rel));

const args = process.argv.slice(2);
if (args.includes('--json')) {
  console.log(
    JSON.stringify(
      rows.map((r) => ({ rel: r.rel, cls: r.cls, why: r.why, signals: [...r.signals], justified: r.justified })),
      null,
      2,
    ),
  );
  process.exit(0);
}

const counts = { A: 0, B: 0, C: 0, D: 0 };
for (const r of rows) counts[r.cls]++;
console.log(`\n== ${counts.A} justificados (A) | ${counts.B} innecesarios (B) | ${counts.C} ambiguos (C) | ${counts.D} ya-servidor (D) ==\n`);

if (args.includes('--verbose')) {
  const uc = rows.filter((r) => r.hasUseClient);
  console.log(`--- TODOS los 'use client' (${uc.length}) ---`);
  for (const r of uc) {
    console.log(`[${r.cls}] ${r.rel}`);
    console.log(`    razon: ${r.why}`);
    console.log(`    senales: ${r.signals.size ? [...r.signals].join(', ') : '(ninguna)'}`);
  }
  console.log('');
  process.exit(0);
}

const only = args.find((a) => a.startsWith('--only='))?.slice('--only='.length);
for (const cls of ['B', 'C', 'A']) {
  const list = rows.filter((r) => r.cls === cls && (!only || only === cls));
  if (list.length === 0) continue;
  console.log(`--- (${cls}) ${list.length} ---`);
  for (const r of list) console.log(`${r.rel}\n    ${r.why}`);
  console.log('');
}
