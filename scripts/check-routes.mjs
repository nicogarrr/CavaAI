/**
 * Lightweight route/link integrity check.
 *
 * 1. Every href in NAV_ITEMS must map to a real app route.
 * 2. Key content routes that are intentionally outside the nav
 *    (currently /metodologia) must be discoverable: at least one
 *    inbound link from another page or component.
 *
 * Runs in CI (npm run test:routes) — no browser needed.
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const failures = [];

// --- 1. NAV_ITEMS hrefs -> real routes -------------------------------------
const constantsSrc = readFileSync(join(root, 'lib/constants.ts'), 'utf8');
const navHrefs = [...constantsSrc.matchAll(/href:\s*'([^']+)'/g)].map((m) => m[1]);

function routeExists(href) {
  if (href === '/') return existsSync(join(root, 'app/(root)/page.tsx'));
  const segment = href.replace(/^\//, '');
  return (
    existsSync(join(root, 'app/(root)', segment, 'page.tsx')) ||
    existsSync(join(root, 'app', segment, 'page.tsx'))
  );
}

for (const href of navHrefs) {
  if (!routeExists(href)) failures.push(`NAV_ITEMS links to ${href} but no page exists for that route`);
}

// --- 2. Non-nav routes must be discoverable --------------------------------
const OFF_NAV_ROUTES = ['/metodologia'];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry.startsWith('.')) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (/\.(tsx|ts)$/.test(entry)) yield full;
  }
}

const sources = [
  ...walk(join(root, 'app')),
  ...walk(join(root, 'components')),
].map((file) => [file, readFileSync(file, 'utf8')]);

for (const route of OFF_NAV_ROUTES) {
  const ownPage = join(root, 'app/(root)', route.replace(/^\//, ''), 'page.tsx');
  const inbound = sources.filter(([file, content]) => file !== ownPage && content.includes(`href="${route}"`));
  if (inbound.length === 0) {
    failures.push(`${route} has no inbound links — it is unreachable in the UI (add a contextual link or remove the route)`);
  }
}

if (failures.length) {
  console.error('Route/link check failed:');
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`Route/link check OK: ${navHrefs.length} nav routes resolve, off-nav routes are discoverable.`);
