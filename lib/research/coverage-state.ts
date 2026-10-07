/** Coverage counts stored layers. It never establishes valuation quality. */
export function researchValuability(snapshot: {
  latest_thesis?: { status: string } | null;
  model_summary?: { status: string; publishable: boolean } | null;
  valuation_summary: { status: string };
}): string {
  const thesis = snapshot.latest_thesis;
  const model = snapshot.model_summary;
  const blocked = new Set(['insufficient_data', 'blocked', 'missing_mandatory_drivers', 'preview_only']);
  if (!thesis || !model || blocked.has(thesis.status) || blocked.has(model.status) ||
      blocked.has(snapshot.valuation_summary.status) || !model.publishable) {
    return 'No valorable / falta evidencia';
  }
  return 'Revisar tesis y supuestos';
}

/** A forecast condition is not evidence that the condition was met. */
export function modelConditionState(item: {
  id: string; value: number | null; comparison?: number | null; status: string;
}, hasWaccSource: boolean): string {
  if (item.status === 'out_of_bounds') return 'Fuera de rango';
  if (item.id === 'roic_above_wacc' && (!hasWaccSource || item.comparison == null || !Number.isFinite(item.comparison))) {
    return 'Pendiente: WACC sin datos';
  }
  if (item.id === 'fcf_margin' && item.value != null && item.value < -1) {
    return 'No cumplida: margen FCF fuera de rango';
  }
  if (item.value == null || !Number.isFinite(item.value) || item.status.startsWith('blocked')) {
    return 'Pendiente: falta evidencia';
  }
  return 'Pendiente de contrastar';
}
