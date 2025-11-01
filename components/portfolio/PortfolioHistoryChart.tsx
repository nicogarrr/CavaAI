'use client';

import React, { useMemo, useState } from 'react';

type Series = { t: number[]; v: number[] };

function formatCurrency(n: number): string {
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function compress(series: Series, maxPoints = 200): Series {
  const { t, v } = series;
  if (t.length <= maxPoints) return series;
  const step = Math.ceil(t.length / maxPoints);
  const tt: number[] = [];
  const vv: number[] = [];
  for (let i = 0; i < t.length; i += step) {
    tt.push(t[i]);
    vv.push(v[i]);
  }
  return { t: tt, v: vv };
}

export default function PortfolioHistoryChart({ data }: { data: Series }) {
  const ranges = [
    { key: '1M', days: 30 },
    { key: '3M', days: 90 },
    { key: '6M', days: 180 },
    { key: '1Y', days: 365 },
    { key: 'MAX', days: 365 * 5 },
  ] as const;
  const [active, setActive] = useState<typeof ranges[number]['key']>('6M');

  const filtered = useMemo(() => {
    if (!data.t.length) return { t: [], v: [] };
    const days = ranges.find((r) => r.key === active)!.days;
    const cutoff = Math.floor(Date.now() / 1000) - days * 24 * 60 * 60;
    const idx = data.t.findIndex((x) => x >= cutoff);
    const sliced = idx <= 0 ? data : { t: data.t.slice(idx), v: data.v.slice(idx) };
    return compress(sliced);
  }, [data, active]);

  const min = Math.min(...filtered.v, Number.MAX_SAFE_INTEGER) || 0;
  const max = Math.max(...filtered.v, 0) || 1;

  const points = filtered.t.map((ts, i) => {
    const x = (i / Math.max(filtered.t.length - 1, 1)) * 100;
    const y = 100 - ((filtered.v[i] - min) / Math.max(max - min, 1)) * 100;
    return `${x},${y}`;
  });

  const last = filtered.v.at(-1) ?? 0;
  const first = filtered.v[0] ?? last;
  const pct = first > 0 ? ((last - first) / first) * 100 : 0;

  return (
    <section className="w-full bg-[#0F0F0F] rounded-lg border border-gray-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-semibold">Histórico de Rentabilidad</h2>
        <div className="flex gap-2">
          {ranges.map((r) => (
            <button
              key={r.key}
              onClick={() => setActive(r.key)}
              className={`px-2 py-1 text-sm rounded border ${active === r.key ? 'border-[#0FEDBE] text-white' : 'border-gray-700 text-gray-400'}`}
            >
              {r.key}
            </button>
          ))}
        </div>
      </div>

      {filtered.t.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-gray-500">Sin datos suficientes</div>
      ) : (
        <div>
          <div className="flex items-baseline gap-3 mb-3">
            <div className={`text-lg font-semibold ${pct >= 0 ? 'text-[#0FEDBE]' : 'text-red-400'}`}>{pct.toFixed(2)}%</div>
            <div className="text-gray-400">Valor actual: {formatCurrency(last)}</div>
          </div>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-48">
            <polyline fill="none" stroke="#0FEDBE" strokeWidth="1" points={points.join(' ')} />
          </svg>
        </div>
      )}
    </section>
  );
}
