// @ts-expect-error TS5097
import { formatMoney, NA } from '../format.ts';

/**
 * F311: los importes de «Posiciones Fiscales» llegaban crudos a la tabla
 * («3589.265983») porque RecordList renderiza con String(value). Las tres
 * columnas monetarias se formatean en es-ES con la divisa de la PROPIA fila
 * (una cartera puede mezclar EUR y USD); sin divisa válida se asume EUR,
 * que es la base del informe fiscal.
 */
export const TAX_HOLDING_MONEY_COLUMNS = ['cost_basis', 'market_value', 'unrealized_pnl'] as const;

export function formatHoldingMoney(value: unknown, currency: unknown): string {
    if (value === null || value === undefined || value === '') return NA;
    const cur = typeof currency === 'string' && /^[A-Za-z]{3}$/.test(currency.trim())
        ? currency.trim().toUpperCase()
        : 'EUR';
    return formatMoney(value as number | string, cur);
}
