/** Only a continuous, complete, return-qualified suffix. Never bridge a missing return
 * or turn empty/partial snapshots into a chart of losses. Read-only, no backfill. */
export type PortfolioSnapshotPoint = {
    snapshot_date: string;
    base_currency: string;
    total_value_base: number;
    pricing_coverage: number;
    net_external_flow_base: number;
    daily_return: number | null;
    cumulative_twr: number | null;
};

export function verifiedPortfolioHistory(rows: readonly PortfolioSnapshotPoint[], currency: string) {
    const sorted = [...rows].sort((a, b) => a.snapshot_date.localeCompare(b.snapshot_date));
    let valid: PortfolioSnapshotPoint[] = [];
    const seen = new Set<string>();
    for (const row of sorted) {
        if (seen.has(row.snapshot_date)) return undefined;
        seen.add(row.snapshot_date);
        if (row.base_currency !== currency || row.pricing_coverage !== 1 ||
            !Number.isFinite(row.total_value_base) || row.total_value_base <= 0 ||
            !Number.isFinite(row.net_external_flow_base) ||
            row.daily_return === null || !Number.isFinite(row.daily_return) ||
            row.cumulative_twr === null || !Number.isFinite(row.cumulative_twr) ||
            !/^\d{4}-\d{2}-\d{2}$/.test(row.snapshot_date)) {
            valid = [];
            continue;
        }
        const prior = valid.at(-1);
        if (prior) {
            const impliedReturn = (row.total_value_base - row.net_external_flow_base) / prior.total_value_base - 1;
            const impliedTwr = (1 + (prior.cumulative_twr as number)) * (1 + row.daily_return) - 1;
            if (Math.abs(impliedReturn - row.daily_return) > 1e-7 ||
                Math.abs(impliedTwr - row.cumulative_twr) > 1e-7) valid = [];
        }
        valid.push(row);
    }
    if (valid.length < 2) return undefined;
    return {
        dates: valid.map((r) => r.snapshot_date), nav: valid.map((r) => r.total_value_base),
        daily_returns: valid.map((r) => r.daily_return as number),
        twr: valid.at(-1)?.cumulative_twr as number,
        start_date: valid[0].snapshot_date, end_date: valid.at(-1)?.snapshot_date as string,
    };
}
