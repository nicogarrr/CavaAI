/**
 * F394: el motor valora por acción ORDINARIA; el precio cotizado de un ADR es
 * por ADR. Cuando el motor informa adr_ratio (ordinarias por ADR), los
 * escenarios se convierten a la misma base que el precio (misma conversión
 * que listed_share_values del backend y que el margen de seguridad).
 */
export function adrRatioFromTrace(trace: Record<string, unknown> | null | undefined): number | null {
  const raw = trace?.adr_ratio;
  const ratio = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw) : NaN;
  return Number.isFinite(ratio) && ratio > 0 ? ratio : null;
}

export function toListedShareValue(
  value: number | string | null | undefined,
  ratio: number | null,
): number | string | null {
  if (value === null || value === undefined || value === '') return null;
  if (ratio === null) return value;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric * ratio : null;
}

export function scenarioBasisLabel(ratio: number | null): string {
  return ratio === null ? '' : ` (por ADR, ×${ratio})`;
}
