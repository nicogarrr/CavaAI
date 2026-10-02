/**
 * Medicion del waterfall de /research/[ticker] modelando la pagina real.
 * Cada lectura cuesta LATENCY_MS. Cuenta fases (round-trip groups)
 * y peticiones totales por vista.
 */
const LATENCY_MS = Number(process.env.LATENCY_MS ?? 120);

let clock = 0;
let phases = 0;
let requests = 0;
let lastStart = -1;

function reset() { clock = 0; phases = 0; requests = 0; lastStart = -1; }

function read(endpoint, latency = LATENCY_MS) {
  requests++;
  if (lastStart < 0 || clock - lastStart >= LATENCY_MS - 1) { phases++; lastStart = clock; }
  const startedAt = clock;
  return new Promise((resolve) => {
    setTimeout(() => {
      clock = Math.max(clock, startedAt + latency);
      resolve(endpoint);
    }, latency);
  });
}

/**
 * getCompanyMarketSnapshot: waterfall REAL de 2 fases dentro de la funcion
 * (el master primero -> luego profile+quote+candles en paralelo).
 */
function marketSnapshot() {
  const a = read('master');
  return a.then(() => Promise.all([read('profile'), read('quote'), read('candles')]));
}

const watchlist = () => read('watchlist');

const VIEWS = {
  overview: () => { const p = read('moat-score'); return Promise.resolve(p); },
  thesis: () => Promise.all(Array.from({ length: 7 }, (_, i) => read(`thesis-${i}`))),
  changes: () => Promise.all(Array.from({ length: 5 }, (_, i) => read(`changes-${i}`))),
  financials: () => Promise.all([read('facts'), read('metrics')]),
  model: () => read('long-term-model'),
  'market-opportunity': () => read('long-term-model'),
  moat: () => read('moat-workspace'),
  peers: () => Promise.all([read('peers-cmp'), read('peers-analysis')]),
  valuation: () => read('valuation'),
  documents: () => read('documents'),
  sources: () => read('audits'),
};

// ---- ANTES: snapshot -> market -> watchlist -> workspace, en serie ----
async function before(view) {
  reset();
  await read('snapshot');
  await marketSnapshot();
  await watchlist();
  await VIEWS[view]();
  return { phases, requests, wall: clock };
}

// ---- DESPUES: las cuatro lecturas salen a la vez ----
async function after(view) {
  reset();
  await Promise.all([read('snapshot'), marketSnapshot(), watchlist(), VIEWS[view]()]);
  return { phases, requests, wall: clock };
}

const rows = [];
for (const view of Object.keys(VIEWS)) {
  const b = await before(view);
  const a = await after(view);
  rows.push({ view, b, a });
}

console.log(`\n=== LATENCIA SINTETICA POR LLAMADA: ${LATENCY_MS} ms ===`);
console.log(`=== SNAPSHOT es la unica lectura dura: no degrada, la pagina no se pinta sin el ===\n`);
console.log('vista                 ANTES(fases/reqs/ms)   DESPUES(fases/reqs/ms)   fases  ms');
for (const r of rows) {
  console.log(
    `${r.view.padEnd(22)} ${String(r.b.phases).padStart(2)}/${String(r.b.requests).padStart(2)}/${String(r.b.wall).padEnd(5)}` +
    `          ${String(r.a.phases).padStart(2)}/${String(r.a.requests).padStart(2)}/${String(r.a.wall).padEnd(5)}` +
    `        -${r.b.phases - r.a.phases}    -${r.b.wall - r.a.wall}`,
  );
}
// Peor caso = la vista con mas round-trips (la tesis: 7 llamadas en su
// workspace). Es la que manda sobre el presupuesto.
const worstB = rows.reduce((a, r) => (r.b.requests > a.requests ? r.b : a), rows[0].b);
const worstA = rows.reduce((a, r) => (r.a.requests > a.requests ? r.a : a), rows[0].a);
console.log(`\npeor caso ANTES:   ${worstB.phases} fases, ${worstB.requests} round-trips, ${worstB.wall} ms`);
console.log(`peor caso DESPUES: ${worstA.phases} fases, ${worstA.requests} round-trips, ${worstA.wall} ms`);
console.log(`\nCon latencia realista de red+backend L, la ficha pasa de ${worstB.phases}*L a ${worstA.phases}*L:`);
for (const L of [150, 300, 500, 1000]) {
  const b = worstB.phases * L;
  const a = worstA.phases * L;
  console.log(`  L=${String(L).padStart(4)}ms -> antes ${String(b).padStart(5)}ms (${(b / 1000).toFixed(1)}s) | despues ${String(a).padStart(5)}ms (${(a / 1000).toFixed(1)}s) | margen sobre 60s: ${(60 - a / 1000).toFixed(1)}s`);
}