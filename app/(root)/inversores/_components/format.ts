import { form13fValueToUsd } from '@/lib/form13f-value';
import { formatDate, formatMarketCapUsd, NA } from '@/lib/format';

/** Valor 13F (dolares desde 2023, miles antes; se normaliza por fecha del informe): "$4.87B". */
export function usd(raw: number | null | undefined, reportDate: string | null | undefined): string {
    const dollars = form13fValueToUsd(raw, reportDate);
    return dollars === null ? NA : formatMarketCapUsd(dollars);
}

/** Periodo del informe ("2026-06-30") en español: "30 jun 2026". */
export function periodLabel(value: string | null | undefined): string {
    return value ? formatDate(value, { day: 'numeric', month: 'short', year: 'numeric' }, value) : NA;
}
