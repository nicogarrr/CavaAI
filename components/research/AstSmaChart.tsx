import type { AstOrbitSample } from '@/lib/actions/asts-orbits.actions';
import { formatNumber, formatUserDateTime } from '@/lib/format';

/** A bounded SVG series of stored orbital epochs, not inferred telemetry. */
export function AstSmaChart({ history, name }: { history: AstOrbitSample[]; name: string }) {
  const samples = history.filter((sample) => Number.isFinite(sample.sma_km) && Number.isFinite(Date.parse(sample.epoch)));
  if (samples.length < 2) return <p className="mt-3 rounded-md border border-gray-800 p-3 text-sm text-gray-400">Sin historial suficiente para la gráfica.</p>;
  const ordered = [...samples].sort((a, b) => Date.parse(a.epoch) - Date.parse(b.epoch));
  const minTime = Date.parse(ordered[0].epoch);
  const maxTime = Date.parse(ordered[ordered.length - 1].epoch);
  if (maxTime === minTime) return <p className="mt-3 text-sm text-gray-400">Sin épocas distintas para la gráfica.</p>;
  const lows = ordered.map((sample) => sample.sma_km);
  const min = Math.min(...lows);
  const max = Math.max(...lows);
  const padding = Math.max((max - min) * .12, .2);
  const lower = min - padding;
  const upper = max + padding;
  const position = (sample: AstOrbitSample) => ({
    x: 48 + (Date.parse(sample.epoch) - minTime) / (maxTime - minTime) * 268,
    y: 14 + (upper - sample.sma_km) / (upper - lower) * 120,
  });
  return <figure className="mt-4 min-w-0 rounded-lg border border-gray-800 bg-[#0b1414] p-3" aria-label={`Histórico del semieje mayor de ${name}`}>
    <figcaption className="mb-2 text-xs font-medium text-gray-200">Semieje mayor por época orbital (km)</figcaption>
    <svg className="block h-auto w-full" viewBox="0 0 340 176" role="img" aria-label={`${name}: ${ordered.length} épocas, de ${formatUserDateTime(ordered[0].epoch)} a ${formatUserDateTime(ordered[ordered.length - 1].epoch)}`}>
      <line x1="48" x2="316" y1="14" y2="14" stroke="#374151" />
      <line x1="48" x2="316" y1="134" y2="134" stroke="#374151" />
      <text x="2" y="18" fill="#9ca3af" fontSize="10">{formatNumber(max, { maximumFractionDigits: 1 })}</text>
      <text x="2" y="137" fill="#9ca3af" fontSize="10">{formatNumber(min, { maximumFractionDigits: 1 })}</text>
      <polyline fill="none" stroke="#5eead4" strokeWidth="2" strokeLinejoin="round" points={ordered.map((sample) => { const { x, y } = position(sample); return `${x},${y}`; }).join(' ')} />
      {ordered.map((sample) => { const { x, y } = position(sample); return <circle key={sample.epoch} cx={x} cy={y} r="2.5" fill="#99f6e4"><title>{`${formatUserDateTime(sample.epoch)}: ${formatNumber(sample.sma_km, { maximumFractionDigits: 2 })} km`}</title></circle>; })}
      <text x="48" y="161" fill="#9ca3af" fontSize="10">{formatUserDateTime(ordered[0].epoch).split(',')[0]}</text>
      <text x="316" y="161" textAnchor="end" fill="#9ca3af" fontSize="10">{formatUserDateTime(ordered[ordered.length - 1].epoch).split(',')[0]}</text>
    </svg>
    <p className="mt-1 text-xs text-gray-400">{ordered.length} épocas guardadas. La gráfica no confirma despliegue.</p>
  </figure>;
}
