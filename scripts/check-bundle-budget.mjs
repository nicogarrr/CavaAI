/**
 * T2: frontend bundle budget — fail CI on runaway JS growth.
 *
 * Ceilings are intentionally generous at introduction (they catch accidents,
 * not force optimization): any single chunk > 600 kB uncompressed or total
 * .next/static chunks > 12 MB fails the build. Tighten deliberately later.
 */
import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const STATIC_DIR = new URL('../.next/static', import.meta.url).pathname;
const MAX_SINGLE_BYTES = 600 * 1024;
const MAX_TOTAL_BYTES = 12 * 1024 * 1024;

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else if (entry.name.endsWith('.js')) yield path;
  }
}

let total = 0;
const offenders = [];
const files = [];
for (const path of walk(STATIC_DIR)) {
  const size = statSync(path).size;
  total += size;
  files.push([size, path]);
  if (size > MAX_SINGLE_BYTES) offenders.push([size, path]);
}

files.sort((a, b) => b[0] - a[0]);
console.log(`bundle-budget: ${files.length} chunks, total ${(total / 1024 / 1024).toFixed(2)} MB`);
console.log('top 5 chunks:');
for (const [size, path] of files.slice(0, 5)) {
  console.log(`  ${(size / 1024).toFixed(0)} kB  ${path.replace(STATIC_DIR, '')}`);
}

let failed = false;
if (offenders.length > 0) {
  failed = true;
  console.error(`FAIL: ${offenders.length} chunk(s) over ${MAX_SINGLE_BYTES / 1024} kB:`);
  for (const [size, path] of offenders) {
    console.error(`  ${(size / 1024).toFixed(0)} kB  ${path.replace(STATIC_DIR, '')}`);
  }
}
if (total > MAX_TOTAL_BYTES) {
  failed = true;
  console.error(`FAIL: total ${(total / 1024 / 1024).toFixed(2)} MB over ${MAX_TOTAL_BYTES / 1024 / 1024} MB budget`);
}
process.exit(failed ? 1 : 0);
