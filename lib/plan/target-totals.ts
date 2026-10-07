export type TargetDimension = 'ticker' | 'sector' | 'asset_class';

/** Each dimension describes the same portfolio, not additional capital. */
export function overallocatedDimension(
    targets: readonly { kind: TargetDimension; target_pct: number }[],
): { kind: TargetDimension; total: number } | null {
    const totals: Record<TargetDimension, number> = { ticker: 0, sector: 0, asset_class: 0 };
    for (const target of targets) totals[target.kind] += target.target_pct;
    for (const kind of ['ticker', 'sector', 'asset_class'] as const) {
        if (totals[kind] > 100 + 1e-9) return { kind, total: totals[kind] };
    }
    return null;
}
