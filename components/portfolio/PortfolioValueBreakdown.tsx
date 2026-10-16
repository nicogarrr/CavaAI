import type { PortfolioSummary } from '@/lib/actions/portfolio.actions';
import { formatMoney } from '@/lib/format';

/** El saldo deudor no se netea contra la caja antes de mostrarlo. */
export function PortfolioValueBreakdown({ summary }: { summary: PortfolioSummary }) {
    const { equityValue, totalValue, cash, cashAssets, marginDebt, baseCurrency, status } = summary;
    const splitAvailable = cashAssets !== undefined && marginDebt !== undefined;
    return (
        <div className="rounded-xl border border-gray-700/50 bg-gray-900/60 p-4">
            <dl className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2">
                <div className="min-w-0">
                    <dt className="text-sm text-gray-400">Posiciones (bruto)</dt>
                    <dd className="mt-1 break-words text-lg font-semibold text-gray-100">{formatMoney(equityValue, baseCurrency)}</dd>
                </div>
                {splitAvailable ? <>
                    <div className="min-w-0">
                        <dt className="text-sm text-gray-400">Caja (saldos positivos)</dt>
                        <dd className="mt-1 break-words text-lg font-semibold text-gray-100">{formatMoney(cashAssets, baseCurrency)}</dd>
                    </div>
                    <div className="min-w-0">
                        <dt className="text-sm text-gray-400">Deuda de margen</dt>
                        <dd className="mt-1 break-words text-lg font-semibold text-amber-300">{formatMoney(marginDebt, baseCurrency)}</dd>
                    </div>
                </> : <div className="min-w-0">
                    <dt className="text-sm text-gray-400">Caja / margen neto</dt>
                    <dd className="mt-1 break-words text-lg font-semibold text-gray-100">{formatMoney(cash, baseCurrency)}</dd>
                </div>}
                <div className="min-w-0">
                    <dt className="text-sm text-gray-400">Patrimonio neto{status === 'incomplete_fx' ? ' (parcial)' : ''}</dt>
                    <dd className="mt-1 break-words text-xl font-bold text-white sm:text-2xl">{formatMoney(totalValue, baseCurrency)}</dd>
                </div>
            </dl>
            {status === 'incomplete_fx' && <p className="mt-3 text-xs text-amber-300">Faltan tipos de cambio. El desglose excluye esos saldos y posiciones.</p>}
        </div>
    );
}
