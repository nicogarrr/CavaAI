// F26: formato honesto de comparables. Un valor ausente es "Sin datos", nunca 0.
const MULTIPLE_METRICS = new Set(['net_debt_to_ebitda']);

export function formatPeerValue(value: string | null | undefined, metric: string): string {
  if (value === null || value === undefined || value === '') return 'Sin datos';
  const number = Number(value);
  if (!Number.isFinite(number)) return 'Sin datos';
  if (MULTIPLE_METRICS.has(metric)) {
    return `${number.toLocaleString('es-ES', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}x`;
  }
  return `${(number * 100).toLocaleString('es-ES', { maximumFractionDigits: 1, minimumFractionDigits: 1 })} %`;
}

export function peerMedianText(
  benchmark: { peer_median: string | null; note?: string | null; insufficient_sample?: boolean },
  metric: string,
): string {
  if (benchmark.peer_median === null || benchmark.insufficient_sample) {
    return benchmark.note ?? 'Sin datos';
  }
  return formatPeerValue(benchmark.peer_median, metric);
}
