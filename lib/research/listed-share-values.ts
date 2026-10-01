/**
 * F394: el motor valora por acción ORDINARIA; el precio cotizado de un ADR es
 * por ADR. El backend entrega los escenarios ya convertidos (listed_share_values)
 * y cada tesis persiste SU propia base al generarse. El cliente nunca multiplica:
 * solo elige qué valores mostrar y cómo rotularlos.
 */
export type ScenarioKey = 'bear' | 'base' | 'bull' | 'expected';
export type ScenarioValues = Record<ScenarioKey, number | string | null | undefined>;

export type ValuationBasis = {
  value_per_share_basis?: string | null;
  adr_ratio?: number | null;
  listed_share_values?: Partial<Record<ScenarioKey, number>> | null;
} | null | undefined;

export type ScenarioDisplay = {
  values: ScenarioValues;
  /** Sufijo para las etiquetas de escenario; vacío si la base no necesita aviso. */
  label: string;
};

function pickListed(
  listed: Partial<Record<ScenarioKey, number>> | null | undefined,
): ScenarioValues | null {
  if (!listed || typeof listed !== 'object') return null;
  const out = {} as ScenarioValues;
  for (const key of ['bear', 'base', 'bull', 'expected'] as const) {
    const value = listed[key];
    out[key] = typeof value === 'number' && Number.isFinite(value) ? value : null;
  }
  return out;
}

function adrLabel(ratio: number | null | undefined): string {
  return typeof ratio === 'number' && Number.isFinite(ratio) && ratio > 0
    ? ` (por ADR, ×${ratio})`
    : ' (por ADR)';
}

/**
 * Tesis persistida. Sin evidencia de base (tesis anterior) no se escala nada:
 * se etiqueta "por acción ordinaria".
 */
export function thesisScenarioDisplay(
  original: ScenarioValues,
  basis: ValuationBasis,
): ScenarioDisplay {
  if (!basis) return { values: original, label: ' (por acción ordinaria)' };
  const listed = pickListed(basis.listed_share_values);
  if (listed) return { values: listed, label: adrLabel(basis.adr_ratio) };
  return { values: original, label: '' };
}

/** Valoración en vivo: usa los campos de su propia respuesta. */
export function valuationScenarioDisplay(
  original: ScenarioValues,
  basis: ValuationBasis,
): ScenarioDisplay {
  const listed = pickListed(basis?.listed_share_values);
  if (listed) return { values: listed, label: adrLabel(basis?.adr_ratio) };
  return { values: original, label: '' };
}
