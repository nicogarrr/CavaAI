/** Read-time quarantine. The persisted fact is preserved for source repair. */
export function factDisplayAudit(ticker: string, fact: {
  metric: string; unit: string; period: string; value: string;
}): string | null {
  if (fact.metric !== 'eps_diluted' && fact.metric !== 'eps') return null;
  // EPS is currency per share. A currency total or a share count is not EPS.
  if (!/^[A-Z]{3}\/(?:share|shares)$/.test(fact.unit)) {
    return 'BPA pendiente de auditoría: unidad no verificada';
  }
  // Production audit 2026-10-07: ASTS fact 2892290 (SEC document 3) has
  // 17,600,000 USD/share in Q1 2020, but no accession/concept lineage proving
  // that value. Do not divide by millions or substitute an inferred EPS.
  if (ticker.toUpperCase() === 'ASTS' && fact.metric === 'eps_diluted' &&
      fact.period === '2020-03-31:Q1' && Number(fact.value) === 17600000) {
    return 'BPA pendiente de auditoría: valor sin linaje de filing verificable';
  }
  return null;
}
