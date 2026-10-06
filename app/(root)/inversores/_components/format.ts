import { formatDate, formatMarketCapUsd, NA } from '@/lib/format';

/** `value_usd_thousands` viene en miles de dólares (13F): "$4.87B". */
export function usd(thousands: number | null | undefined): string {
    if (thousands === null || thousands === undefined) return NA;
    return formatMarketCapUsd(thousands * 1000);
}

/** Periodo del informe ("2026-06-30") en español: "30 jun 2026". */
export function periodLabel(value: string | null | undefined): string {
    return value ? formatDate(value, { day: 'numeric', month: 'short', year: 'numeric' }, value) : NA;
}
