/**
 * Guard F287: FileUploadInput es un compuesto de dos filas (boton
 * «Elegir archivo» + pista «Maximo N MB.»); fijarle una altura fija
 * (h-10/h-11/...) desde el call site hace que la pista desborde la caja
 * y el siguiente elemento del grid la solape (boton «Subir» solapaba 8px
 * la pista en /knowledge?tab=subir).
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const SKIP = new Set(['node_modules', '.next', '.git']);

function* tsxFiles(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    if (SKIP.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      yield* tsxFiles(full);
    } else if (entry.endsWith('.tsx')) {
      yield full;
    }
  }
}

const offenders: string[] = [];
for (const file of tsxFiles(ROOT)) {
  const source: string = readFileSync(file, 'utf8');
  for (const match of source.matchAll(/<FileUploadInput\b[^>]*>/g)) {
    const tag = match[0];
    if (/\bh-\d/.test(tag) || /\bh-\[/.test(tag)) {
      offenders.push(`${file}: ${tag.slice(0, 120)}`);
    }
  }
}

assert.deepEqual(
  offenders,
  [],
  `FileUploadInput no admite altura fija desde el call site (la pista «Maximo N MB.» desborda y el siguiente elemento la solapa):\n${offenders.join('\n')}`,
);

console.log('knowledge-upload-height-guard: ok');
