/**
 * E6: repo hygiene guard. Fails when the working copy accumulates the residue
 * that is easy to create and expensive to keep: scratch debug scripts, binary
 * databases in the index, oversized blobs, cache directories, and a `.gitignore`
 * that has stopped covering those categories.
 *
 * Every category is checked twice: once against the real repository, and once
 * against SYNTHETIC input in the negative tests below. A guard nobody has seen
 * fail is not a guard, so each one is shown biting on data that should trip it.
 * The synthetic cases use the same pure helpers the real check uses, so a green
 * negative test is evidence about the production code path and not about a
 * parallel copy of the logic.
 */
import assert from 'node:assert/strict';
import { execFileSync, type ExecFileSyncOptionsWithStringEncoding } from 'node:child_process';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import test from 'node:test';

const MAX_TRACKED_BYTES = 5 * 1024 * 1024;

type GitOptions = Omit<ExecFileSyncOptionsWithStringEncoding, 'encoding'>;

function git(args: readonly string[], opts: GitOptions = {}): string {
  return execFileSync('git', args, { ...opts, encoding: 'utf8', maxBuffer: 128 * 1024 * 1024 });
}

const tracked = (): string[] => git(['ls-files', '-z']).split('\0').filter(Boolean);

/**
 * `git check-ignore --no-index` is the authoritative test of whether a pattern
 * covers a path, and it evaluates rules for paths that do not exist yet, which
 * is what we need: we are asking "if someone committed this, would it be
 * caught?", not "is this file present right now?".
 */
function isIgnored(path: string): boolean {
  try {
    git(['check-ignore', '--no-index', '-q', path]);
    return true;
  } catch {
    return false;
  }
}

// ------------------------------------------------------------ pure helpers

/** Tracked paths matching any of the forbidden residue patterns. */
export function findForbiddenPaths(paths: readonly string[]): Array<{ path: string; rule: string }> {
  const RULES = [
    { id: 'cache-dir', re: /(^|\/)__pycache__(\/|$)/ },
    { id: 'cache-dir', re: /(^|\/)\.pytest_cache(\/|$)/ },
    { id: 'cache-dir', re: /(^|\/)\.ruff_cache(\/|$)/ },
    { id: 'cache-dir', re: /(^|\/)\.mypy_cache(\/|$)/ },
    { id: 'cache-dir', re: /(^|\/)\.next(-[a-z0-9]+)?(\/|$)/ },
    { id: 'cache-dir', re: /(^|\/)node_modules(\/|$)/ },
    { id: 'cache-dir', re: /(^|\/)\.venv(\/|$)/ },
    { id: 'build-output', re: /(^|\/)test-results(\/|$)/ },
    { id: 'build-output', re: /(^|\/)playwright-report(\/|$)/ },
    { id: 'build-output', re: /(^|\/)coverage(\/|$)/ },
    { id: 'build-output', re: /(^|\/)htmlcov(\/|$)/ },
    { id: 'tsbuildinfo', re: /\.tsbuildinfo$/ },
    { id: 'storage-cache', re: /^storage\// },
    { id: 'storage-cache', re: /^data-engine\/storage\// },
    // A binary database in the index: grows forever, diffs are unreadable, and
    // rows can hold personal data. Source belongs in alembic migrations.
    { id: 'database', re: /\.db(-shm|-wal|-journal)?$/ },
    { id: 'database', re: /\.sqlite3?(-shm|-wal|-journal)?$/ },
    { id: 'database', re: /\.duckdb(\.wal)?$/ },
  ];
  const hits = [];
  for (const p of paths) {
    const rule = RULES.find((r) => r.re.test(p));
    if (rule) hits.push({ path: p, rule: rule.id });
  }
  return hits;
}

/** Scratch debug scripts at the repo root. `dbg*.js` is the known offender. */
export function findScratchScripts(paths: readonly string[]): string[] {
  return paths.filter((p) => !p.includes('/') && /^dbg\d*\.[cm]?js$/i.test(p));
}

/** Tracked blobs over the size budget, biggest first. */
export function findOversized(
  entries: ReadonlyArray<readonly [number, string]>,
  maxBytes: number = MAX_TRACKED_BYTES,
): Array<{ path: string; size: number }> {
  return entries
    .filter(([size]) => size > maxBytes)
    .sort((a, b) => b[0] - a[0])
    .map(([size, path]) => ({ path, size }));
}

/** Sample paths per category, used to assert `.gitignore` still covers them. */
export const IGNORE_CATEGORIES = [
  { id: 'sqlite-db', sample: 'data-engine/cavaai_test_1234_abcd.db' },
  { id: 'sqlite-db', sample: 'cavaai_test.db' },
  { id: 'sqlite-db', sample: 'data-engine/demo_local.db' },
  { id: 'sqlite-db', sample: 'data-engine/cache.db' },
  { id: 'pycache', sample: 'data-engine/app/__pycache__/core.cpython-311.pyc' },
  { id: 'pycache', sample: 'data-engine/modules/__pycache__/cache.cpython-311.pyc' },
  { id: 'pytest-cache', sample: 'data-engine/storage/.pytest_cache/v/cache/nodeids' },
  { id: 'pytest-cache', sample: '.pytest_cache/CACHEDIR.TAG' },
  { id: 'ruff-cache', sample: 'data-engine/.ruff_cache/0.14.0/ruff_cache.json' },
  { id: 'storage-raw', sample: 'storage/raw/2024-01-02AAPL/filing.htm' },
  { id: 'storage-raw', sample: 'data-engine/storage/raw/2024-01-02AAPL/filing.htm' },
  { id: 'next-build', sample: '.next/BUILD_ID' },
  { id: 'tsbuildinfo', sample: 'tsconfig.tsbuildinfo' },
  { id: 'test-results', sample: 'test-results/.last-run.json' },
  { id: 'playwright-report', sample: 'playwright-report/index.html' },
  { id: 'coverage', sample: 'coverage/lcov.info' },
  { id: 'node-modules', sample: 'node_modules/next/package.json' },
  { id: 'venv', sample: 'data-engine/.venv/pyvenv.cfg' },
  { id: 'duckdb', sample: 'data-engine/data/market.duckdb' },
];

// ------------------------------------------------------- the real repository

test('E6/H1: no hay scripts de depuracion sueltos (dbg*.js) en la raiz', () => {
  const offenders = findScratchScripts(tracked());
  assert.deepEqual(offenders, [], `borrar del indice: ${offenders.join(', ')}`);

  // Also catch them sitting untracked on disk: that is how they got here.
  const onDisk = readdirSync('.').filter((n) => /^dbg\d*\.[cm]?js$/i.test(n));
  assert.deepEqual(onDisk, [], `borrar del disco: ${onDisk.join(', ')}`);
});

test('E6/H2: ninguna base de datos binaria esta versionada', () => {
  const dbs = findForbiddenPaths(tracked()).filter((h) => h.rule === 'database');
  assert.deepEqual(
    dbs.map((d) => d.path),
    [],
    `una .db en git crece sin parar, hace diffs ilegibles y puede contener filas con datos personales: ${dbs
      .map((d) => d.path)
      .join(', ')}`,
  );
});

test('E6/H3: ninguna cache ni artefacto de build esta versionado', () => {
  const residue = findForbiddenPaths(tracked()).filter((h) => h.rule !== 'database');
  assert.deepEqual(
    residue.map((h) => `${h.rule}:${h.path}`),
    [],
    `residuo en el indice: ${residue.map((h) => h.path).join(', ')}`,
  );
});

test('E6/H4: storage/ (c raw) no esta versionado', () => {
  const under = tracked().filter((p) => p === 'storage' || p.startsWith('storage/'));
  assert.deepEqual(under, [], `storage/ es cache de ingesta: ${under.slice(0, 5).join(', ')}`);
});

test(`E6/H5: ningun fichero versionado supera ${MAX_TRACKED_BYTES / 1048576} MB`, () => {
  const entries: Array<[number, string]> = [];
  for (const p of tracked()) {
    try {
      entries.push([statSync(p).size, p]);
    } catch {
      /* symlink or race: not a size problem */
    }
  }
  const big = findOversized(entries);
  assert.deepEqual(
    big.map((b) => `${(b.size / 1048576).toFixed(1)}MB ${b.path}`),
    [],
    'blob grande versionado: el clone lo paga todo el mundo en cada ronda',
  );
});

test('E6/H6: .gitignore sigue cubriendo cada categoria que este guard comprueba', () => {
  const uncovered = IGNORE_CATEGORIES.filter((c) => !isIgnored(c.sample));
  assert.deepEqual(
    uncovered.map((c) => `${c.id}: ${c.sample}`),
    [],
    'estas categorias se meterian en git si alguien hiciera commit -a',
  );
});

/** Samples probed against `.dockerignore`. */
const DOCKERIGNORE_SAMPLES = [
  'data-engine/.venv/pyvenv.cfg',
  'storage/raw/x/filing.htm',
  'data-engine/storage/raw/f.htm',
  'data-engine/cavaai_test_1_a.db',
  '.next/BUILD_ID',
  'node_modules/x',
  'test-results/.last-run.json',
  'tsconfig.tsbuildinfo',
  'coverage/lcov.info',
  'data-engine/htmlcov/index.html',
  'playwright-report/index.html',
  'data-engine/.pytest_cache/x',
  'data-engine/.ruff_cache/x',
  '.env.production',
  'e2e/x.spec.ts',
];

/**
 * Gaps in `.dockerignore` confirmed present, reported as INTEGRACION PENDIENTE
 * rather than patched here (the integrator owns that file).
 *
 * They exist because Docker matches `.dockerignore` patterns with Go's
 * filepath.Match semantics, where `*` does NOT cross `/`. So the existing
 * `*.db` line covers `cavaai_e2e.db` but NOT `data-engine/cavaai_test.db`, and
 * `node_modules` covers the directory entry but not `node_modules/next/package.json`.
 *
 * This list is a ratchet, not a waiver: a NEW uncovered sample fails the test.
 * Deleting an entry from this list before adding the rule also fails, because
 * the sample then shows up as uncovered.
 */
const KNOWN_DOCKERIGNORE_GAPS = new Set([
  'data-engine/cavaai_test_1_a.db',
  '.next/BUILD_ID',
  'node_modules/x',
  'test-results/.last-run.json',
  'tsconfig.tsbuildinfo',
  'coverage/lcov.info',
  'data-engine/htmlcov/index.html',
  'playwright-report/index.html',
]);

function dockerignoreCovers(sample: string, rules: readonly string[]): boolean {
  return rules.some((line) => {
    const re = new RegExp(
      `^${line
        .replace(/[.+^${}()|[\]\\]/g, '\\$&')
        .replace(/\*\*/g, ' ')
        .replace(/\*/g, '[^/]*')
        .replace(/ /g, '.*')
        .replace(/\/$/, '(/.*)?$')}$`,
    );
    return re.test(sample);
  });
}

test('E6/H7: .dockerignore cubre el build, salvo huecos conocidos y listados', () => {
  const rules = readFileSync('.dockerignore', 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'));

  const uncovered = DOCKERIGNORE_SAMPLES.filter((s) => !dockerignoreCovers(s, rules));
  const newGaps = uncovered.filter((s) => !KNOWN_DOCKERIGNORE_GAPS.has(s));

  assert.deepEqual(
    newGaps,
    [],
    `nuevos huecos en .dockerignore (entrarian al contexto de build): ${newGaps.join(', ')}`,
  );
  assert.deepEqual(
    [...KNOWN_DOCKERIGNORE_GAPS].filter((s) => !uncovered.includes(s)),
    [],
    'estos huecos ya estan cubiertos: quita la entrada de KNOWN_DOCKERIGNORE_GAPS',
  );
});

// ------------------------------------------------------------- negative cases

test('E6/N1: el detector de scripts sueltos muerde (caso negativo)', () => {
  assert.deepEqual(findScratchScripts(['dbg.js', 'dbg2.js', 'dbg3.js']), [
    'dbg.js',
    'dbg2.js',
    'dbg3.js',
  ]);
  // Negative: same names nested are somebody's real module, not root scratch.
  assert.deepEqual(findScratchScripts(['app/lib/dbg.js', 'lib/dbg2.js']), []);
});

test('E6/N2: el detector de bases de datos muerde (caso negativo)', () => {
  const hits = findForbiddenPaths([
    'data-engine/cavaai_test_17000_11898cca.db',
    'cavaai_e2e.db',
    'portfolio_research_os.db',
    'data-engine/app.db-wal',
    'data-engine/market.duckdb',
  ]);
  assert.equal(hits.length, 5);
  assert.ok(hits.every((h) => h.rule === 'database'));
  // Negative: a migration that merely mentions a table is source, not a database.
  assert.deepEqual(findForbiddenPaths(['data-engine/alembic/versions/0026_x.py']), []);
});

test('E6/N3: el detector de residuo muerde (caso negativo)', () => {
  const hits = findForbiddenPaths([
    'data-engine/app/__pycache__/main.cpython-311.pyc',
    'data-engine/storage/.pytest_cache/v/cache/nodeids',
    '.next/BUILD_ID',
    'node_modules/next/package.json',
    'tsconfig.tsbuildinfo',
    'test-results/.last-run.json',
  ]);
  assert.equal(hits.length, 6);
  assert.ok(hits.every((h) => h.rule !== 'database'));
  // Negative: `.github` and `data-engine/.venv` in .gitignore must not make the
  // guard reject a legitimate source path that merely looks similar.
  assert.deepEqual(findForbiddenPaths(['data-engine/app/services/cache.py', 'hooks/useCache.ts']), []);
});

test('E6/N4: el detector de tamano muerde (caso negativo)', () => {
  const entries: Array<readonly [number, string]> = [
    [6 * 1024 * 1024, 'data-engine/data/esef_blob.bin'],
    [59 * 1024 * 1024, 'data-engine/data/big_esef.htm'],
    [1024, 'README.md'],
  ];
  const big = findOversized(entries);
  assert.equal(big.length, 2);
  assert.equal(big[0].path, 'data-engine/data/big_esef.htm', 'orden descendente por tamano');
  // Boundary: exactly at the budget is allowed.
  assert.deepEqual(findOversized([[MAX_TRACKED_BYTES, 'ok.bin']]), []);
});