/** Disposable Next route for isolated browser regression, never deployed. */
import { mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const directory = 'app/chart-preview';
if (existsSync(directory)) throw new Error('Refusing to overwrite existing route');
mkdirSync(directory);
writeFileSync(`${directory}/page.tsx`, `
import { CompanyHeaderQuote } from '@/components/research/CompanyHeaderQuote';
import { e2eMarketFixture } from '@/lib/e2e-market-fixture';
export default async function Preview({ searchParams }: { searchParams: Promise<{ mode?: string }> }) {
 const {mode} = await searchParams;
 const snapshot = e2eMarketFixture('MSFT');
 snapshot.historySource = 'Fixture local';
 snapshot.history = mode === 'empty' ? [] : mode === 'close' ? snapshot.history : Array.from({ length: 260 }, (_, i) => { const close = 325 + Math.sin(i / 8) * 14 + Math.cos(i / 3) * 5 + i * 0.04; return { date: new Date(Date.UTC(2026, 0, i + 1)).toISOString().slice(0,10), open: close-1, high: close+3, low: close-4, close, volume: 1000000+i*100 }; });
 return <main className="mx-auto max-w-[1500px] p-4 sm:p-6"><h1 className="mb-4 text-2xl text-gray-100">MSFT</h1><CompanyHeaderQuote snapshot={snapshot}/></main>;
}`);
try {
 const result = spawnSync('npx', ['playwright', 'test', '--config', 'e2e/fixtures/technical-chart.config.ts'], { stdio: 'inherit', env: { ...process.env, E2E_CHART_RUN: '1' } });
 process.exitCode = result.status ?? 1;
} finally { rmSync(directory, {recursive:true}); }
