// F34: una ficha sin cotización vigente no puede mostrar salud 0/100 como dato.
const STALE_DAYS = 30;

function esDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

export type ListingStatus = { stale: true; message: string } | { stale: false };

export function listingStatus(
  exchange: string | null | undefined,
  priceAsOf: string | null | undefined,
  now: Date,
): ListingStatus {
  const unknownExchange = !exchange || ['UNKNOWN', 'UNKNOWN_EXCHANGE'].includes(exchange.trim().toUpperCase());
  const asOf = priceAsOf && /^\d{4}-\d{2}-\d{2}/.test(priceAsOf) ? priceAsOf : null;
  const ageDays = asOf ? (now.getTime() - Date.parse(`${asOf.slice(0, 10)}T00:00:00Z`)) / 86_400_000 : null;
  const old = ageDays !== null && ageDays > STALE_DAYS;
  if (!unknownExchange && !old) return { stale: false };
  return {
    stale: true,
    message: asOf
      ? `Ticker sin cotización vigente (último cierre ${esDate(asOf)})`
      : 'Ticker sin cotización vigente (sin cierre conocido)',
  };
}

export function healthText(score: number | null | undefined, status: ListingStatus): string {
  if (status.stale || score === null || score === undefined) return 'Sin datos';
  return `${score}/100`;
}
