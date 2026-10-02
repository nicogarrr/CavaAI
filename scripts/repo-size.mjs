/**
 * E6: repository size report.
 *
 * Clone cost is a real onboarding tax and nobody measures it, so it silently
 * grows until someone complains. This reports where the bytes are: the tracked
 * working tree, the heaviest files and directories, and the `.git` object store
 * (which is what actually dominates a clone and is invisible in a file listing).
 *
 * Read-only. `node scripts/repo-size.mjs [--json] [--top 20]`
 */
import { execFileSync } from 'node:child_process';
import { readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = resolve(fileURLToPath(new URL('..', import.meta.url)));

const args = process.argv.slice(2);
const asJson = args.includes('--json');
const topIdx = args.indexOf('--top');
const TOP = topIdx === -1 ? 20 : Number(args[topIdx + 1] ?? 20);

const IGNORED_DIRS = new Set(['.git', 'node_modules', '.venv', 'venv', '.next', '.next-e2e']);
function human(bytes) {
  const units = ['B', 'kB', 'MB', 'GB'];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

function dirSize(dir) {
  let total = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (IGNORED_DIRS.has(entry.name)) continue;
    const p = join(dir, entry.name);
    total += entry.isDirectory() ? dirSize(p) : statSync(p).size;
  }
  return total;
}

/** Per tracked file, using git's index so build output is never counted. */
function trackedEntries() {
  const list = execFileSync('git', ['ls-files', '-z'], {
    cwd: REPO,
    encoding: 'utf8',
    maxBuffer: 128 * 1024 * 1024,
  })
    .split('\0')
    .filter(Boolean);
  const out = [];
  for (const f of list) {
    try {
      out.push([statSync(join(REPO, f)).size, f]);
    } catch {
      /* symlink or removed between ls-files and stat */
    }
  }
  return out;
}

/** Aggregate tracked bytes by top-level and second-level directory. */
function dirTotals(entries) {
  const totals = new Map();
  for (const [size, path] of entries) {
    const parts = path.split('/');
    const key = parts.length > 1 ? parts.slice(0, 2).join('/') : parts[0];
    totals.set(key, (totals.get(key) ?? 0) + size);
  }
  return [...totals].sort((a, b) => b[1] - a[1]);
}

function gitPath(...args) {
  return execFileSync('git', ['rev-parse', ...args], { cwd: REPO, encoding: 'utf8' }).trim();
}

/**
 * In a linked worktree `.git` is a FILE containing `gitdir: <path>`, so walking
 * `.git` from the worktree root finds nothing. The object store a clone actually
 * transfers lives in the COMMON dir, which is what this measures.
 */
function gitDirSize() {
  try {
    const common = gitPath('--path-format=absolute', '--git-common-dir');
    return dirSize(common);
  } catch {
    return null;
  }
}

/** Pack the object store: `git gc` is what a clone actually transfers. */
function gitCountObjects() {
  try {
    const out = execFileSync('git', ['count-objects', '-vH'], {
      cwd: REPO,
      encoding: 'utf8',
      // In a linked worktree git warns about a stale `refs` entry on stderr.
      // It is not this report's business and would drown the output.
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    const parse = (k) => {
      const m = new RegExp(`^${k}:\\s*(\\S+)`, 'm').exec(out);
      return m ? m[1] : null;
    };
    return {
      sizePack: parse('size-pack'),
      size: parse('size'),
      count: parse('count'),
      inPack: parse('in-pack'),
      garbage: parse('garbage'),
    };
  } catch {
    return null;
  }
}

const entries = trackedEntries();
const files = [...entries].sort((a, b) => b[0] - a[0]);
const trackedTotal = entries.reduce((a, [s]) => a + s, 0);

const report = {
  trackedFiles: entries.length,
  trackedBytes: trackedTotal,
  trackedHuman: human(trackedTotal),
  gitDirBytes: gitDirSize(),
  gitDirHuman: human(gitDirSize() ?? 0),
  gitObjects: gitCountObjects(),
  topFiles: files.slice(0, TOP).map(([size, path]) => ({ path, size, human: human(size) })),
  topDirs: dirTotals(entries)
    .slice(0, TOP)
    .map(([dir, bytes]) => ({ dir, bytes, human: human(bytes) })),
  // Files above the hygiene guard's budget, so the report predicts the failure.
  overBudget: files.filter(([s]) => s > 5 * 1024 * 1024).map(([s, p]) => ({ path: p, human: human(s) })),
};

if (asJson) {
  console.log(JSON.stringify(report, null, 2));
} else {
  console.log(`E6 repo size  (${REPO})`);
  console.log(`  versionados: ${report.trackedFiles} ficheros, ${report.trackedHuman}`);
  console.log(`  .git:        ${report.gitDirHuman}${report.gitObjects?.sizePack ? ` (pack ${report.gitObjects.sizePack})` : ''}`);
  const cloneRatio =
    report.gitDirBytes && trackedTotal ? (report.gitDirBytes / trackedTotal).toFixed(1) : '?';
  console.log(`  ratio .git/working tree: ${cloneRatio}x  <- esto es lo que paga un clone`);
  console.log(`\n  Top ${TOP} ficheros:`);
  for (const f of report.topFiles) console.log(`    ${f.human.padStart(9)}  ${f.path}`);
  console.log(`\n  Top ${TOP} directorios:`);
  for (const d of report.topDirs) console.log(`    ${d.human.padStart(9)}  ${d.dir}`);
  if (report.overBudget.length) {
    console.log(`\n  POR ENCIMA DEL PRESUPUESTO DE 5 MB (los guarda repo-hygiene):`);
    for (const o of report.overBudget) console.log(`    ${o.human}  ${o.path}`);
  } else {
    console.log(`\n  ningun fichero versionado pasa de 5 MB`);
  }
}