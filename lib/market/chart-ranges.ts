export const CHART_RANGES = ['1D', '5D', '1M', '6M', 'YTD', '1A', '5A', 'Máx'] as const;
export type CompanyChartRange = typeof CHART_RANGES[number];
export function isChartRange(value: unknown): value is CompanyChartRange {
    return typeof value === 'string' && (CHART_RANGES as readonly string[]).includes(value);
}
export function chartRequestWindow(range: CompanyChartRange, now: number) {
    const day = 86400;
    // Fetch enough hourly data to cover the last session over holidays/weekends.
    const days = range === '1D' || range === '5D' ? 10 : range === '5A' ? 5 * 366 : 366;
    return { from: range === 'Máx' ? 0 : Math.floor(now) - days * day, to: Math.floor(now), resolution: range === '1D' || range === '5D' ? '60' as const : 'D' as const };
}
export function intradayWindow<T extends { timestamp?: number }>(bars: T[], range: '1D' | '5D'): T[] {
    if (!bars.length) return [];
    const end = bars.at(-1)?.timestamp;
    if (!end || !Number.isFinite(end)) return [];
    // Ranges are rolling elapsed time, not a claim of complete trading sessions.
    const seconds = (range === '1D' ? 1 : 5) * 86400;
    return bars.filter((bar) => typeof bar.timestamp === 'number' && bar.timestamp > end - seconds);
}
