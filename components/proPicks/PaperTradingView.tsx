import { useEffect, useState } from 'react';
import { getPaperTrading, type PaperState } from '@/lib/actions/paper-trading.actions';

const number = (value: string | number | null) => value === null ? 'Sin datos' : Number(value).toLocaleString('es-ES', { maximumFractionDigits: 2 });
const horizon = (value: string) => value === 'five_years' ? 'Tesis 5 años' : 'Trade 30 días';
const stateLabel: Record<string, string> = { pending: 'Pendiente de entrada', open: 'Abierta', closed: 'Cerrada' };
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleString('es-ES') : 'Sin datos';

export function PaperTradingContent({ data }: { data: PaperState }) {
    if (data.error) return <p role="alert" className="text-red-300">{data.error}</p>;
    return <section className="min-w-0 space-y-4" aria-label="Cartera simulada LLM">
        <h2 className="text-xl font-semibold text-gray-100">Paper trading · LLM</h2>
        <div className="grid gap-3 sm:grid-cols-2">
            {data.score.groups.map(group => <article key={`${group.horizon}-${group.currency}`} className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                <h3 className="font-medium text-teal-300">{horizon(group.horizon)} · {group.currency === 'sin_datos' ? 'Sin divisa' : group.currency}</h3>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-sm text-gray-300">
                    <dt>Aciertos / cerradas</dt><dd>{group.wins} / {group.closed}</dd>
                    <dt>Tasa de acierto</dt><dd>{group.hit_rate === null ? 'Sin datos' : `${number(group.hit_rate * 100)} %`}</dd>
                    <dt>Errores / neutras</dt><dd>{group.losses} / {group.flat}</dd>
                    <dt>P&amp;L bruto cerrado</dt><dd>{number(group.realized_pnl)}</dd>
                    <dt>P&amp;L bruto abierto</dt><dd>{number(group.unrealized_pnl)}</dd>
                    <dt>Abiertas sin precio</dt><dd>{group.missing_marks}</dd>
                </dl>
            </article>)}
        </div>
        {data.trades.length === 0 && <p className="text-gray-400">Sin propuestas LLM registradas.</p>}
        {data.trades.map(trade => <article key={trade.id} className="min-w-0 space-y-3 rounded-lg border border-gray-700 p-4 text-sm text-gray-300">
            <div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold text-gray-100">{trade.ticker} · {trade.direction === 'long' ? 'Largo' : 'Corto'} · {horizon(trade.horizon)}</h3><span>{stateLabel[trade.status] ?? trade.status}</span></div>
            <p className="break-words whitespace-pre-wrap">{trade.thesis}</p>
            <p>Inferencia LLM: convicción {number(Number(trade.conviction) * 100)} % · entrada {number(trade.proposed_entry)} · stop {number(trade.stop)} · objetivo {number(trade.target)}</p>
            <p className="break-words">Base: {trade.inference_basis}</p>
            <p>Dato de mercado · {trade.currency ?? 'Sin divisa'}: entrada {number(trade.entry_price)} · último precio {number(trade.mark_price)} · cierre {number(trade.exit_price)}</p>
            <p>P&amp;L bruto simulado: {number(trade.status === 'closed' ? trade.realized_pnl : trade.unrealized_pnl)}</p>
            <p className="text-xs text-gray-400">Propuesta: {dateLabel(trade.created_at)} · precio: {dateLabel(trade.mark_at)}</p>
        </article>)}
        <details className="text-xs text-gray-400"><summary>Base de medición</summary><p className="mt-2">Acierto = P&amp;L bruto positivo al cerrar. Divisas separadas. Sin comisiones, dividendos, financiación ni ajustes por splits. Una salida anticipada no valida una tesis a 5 años. Cantidad simulada: supuesto.</p></details>
    </section>;
}

export default function PaperTradingView() {
    const [data, setData] = useState<PaperState | null>(null);
    useEffect(() => { let alive = true; getPaperTrading().then(result => { if (alive) setData(result); }).catch(() => { if (alive) setData({ trades: [], score: { groups: [] }, error: 'No se pudo cargar la cartera simulada.' }); }); return () => { alive = false; }; }, []);
    return data ? <PaperTradingContent data={data} /> : <p role="status" className="text-gray-400">Cargando cartera simulada…</p>;
}
