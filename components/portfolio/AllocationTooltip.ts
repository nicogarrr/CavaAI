/**
 * Tooltip del donut de distribución. Módulo .ts sin JSX para que las
 * guardas puedan montarlo con react-dom/server y verificar el resultado
 * (moneda, ausencia de enlace y de G/P para la caja).
 */
import { createElement as h, type ReactNode } from 'react';
import Link from 'next/link.js';
// @ts-expect-error TS5097
import { formatMoney, formatPercent } from '../../lib/format.ts';
// @ts-expect-error TS5097
import { CASH_SLICE_SYMBOL, type AllocationSliceData } from '../../lib/portfolio-allocation.ts';

export type AllocationTooltipProps = {
    active?: boolean;
    payload?: Array<{ payload: AllocationSliceData }>;
    /** Moneda base de la cartera: sin ella formatMoney caería en USD. */
    currency?: string;
};

const line = (label: string, value: ReactNode, className = 'font-semibold text-white') =>
    h('p', { className: 'text-gray-300 text-sm' }, `${label}: `, h('span', { className }, value));

export function AllocationTooltip({ active, payload, currency }: AllocationTooltipProps) {
    if (!active || !payload || payload.length === 0) {
        return null;
    }
    const data = payload[0].payload;
    const isCash = data.symbol === CASH_SLICE_SYMBOL;
    const title = isCash
        ? h('span', { className: 'font-bold text-gray-200 mb-1 block' }, CASH_SLICE_SYMBOL)
        : h(Link, { href: `/research/${data.symbol}`, className: 'font-bold text-teal-400 hover:text-teal-300 mb-1 block' }, data.symbol);
    const children: ReactNode[] = [
        title,
        line('Valor', formatMoney(data.value, currency)),
        line('Peso', formatPercent(data.percentage, { fromRatio: false, digits: 1 })),
    ];
    if (!isCash) {
        const isPositive = data.gain >= 0;
        children.push(line(
            'G/P',
            formatPercent(data.gainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' }),
            `font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`,
        ));
    }
    return h('div', { className: 'bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl' }, ...children);
}
