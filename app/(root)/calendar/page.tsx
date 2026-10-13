import type { Metadata } from 'next';
import { CalendarDays } from 'lucide-react';
import BackendOffline from '@/components/system/BackendOffline';
import { getCatalystCalendar, type CatalystCalendar, type CatalystEvent } from '@/lib/actions/catalysts.actions';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import { formatMarketDate, formatNumber } from '@/lib/format';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
    title: 'Calendario de catalizadores',
    description: 'Resultados, dividendos y acciones corporativas de tus posiciones abiertas en un solo calendario.',
};

const TYPE_LABEL: Record<CatalystEvent['type'], string> = {
    earnings: 'Resultados',
    dividend_ex: 'Ex-dividendo',
    corporate_action: 'Acción corporativa',
};

function groupByDate(events: CatalystEvent[]): [string, CatalystEvent[]][] {
    const groups = new Map<string, CatalystEvent[]>();
    for (const event of events) {
        groups.set(event.date, [...(groups.get(event.date) ?? []), event]);
    }
    return [...groups.entries()];
}

export default async function CalendarPage() {
    let calendar: CatalystCalendar;
    try {
        calendar = await getCatalystCalendar();
    } catch (error) {
        if (isBackendUnavailableError(error)) {
            return <BackendOffline feature="Calendario de catalizadores" retryHref="/calendar" />;
        }
        throw error;
    }

    const groups = groupByDate(calendar.events);
    const degraded = calendar.status !== 'ok';

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex max-w-4xl flex-col gap-6">
            <header className="flex flex-col gap-3 border-b border-gray-800 pb-5 sm:flex-row sm:items-end sm:justify-between">
                <div>
                    <p className="text-sm font-semibold uppercase text-teal-300">Cartera</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-100">Calendario de catalizadores</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-400">
                        Resultados, dividendos y acciones corporativas de tus posiciones abiertas, del{' '}
                        {formatMarketDate(calendar.desde)} al {formatMarketDate(calendar.hasta)}.
                    </p>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-surface-1 px-3 py-2 text-sm text-gray-300">
                    <CalendarDays aria-hidden="true" className="h-4 w-4 text-teal-300" />
                    {formatNumber(calendar.count, { maximumFractionDigits: 0 })} eventos
                </div>
            </header>

            {degraded ? (
                <p role="status" className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-sm text-amber-200">
                    {calendar.status === 'unavailable'
                        ? 'El calendario público de NASDAQ no responde: no se pueden mostrar resultados ni dividendos. Esto no significa que no haya eventos.'
                        : 'El calendario público de NASDAQ falló para algunos días: la lista puede estar incompleta.'}
                </p>
            ) : null}

            {calendar.held_count === 0 ? (
                <p className="rounded-lg border border-gray-800 p-4 text-sm text-gray-400">
                    No tienes posiciones abiertas, así que no hay catalizadores que seguir.
                </p>
            ) : groups.length === 0 && !degraded ? (
                <p className="rounded-lg border border-gray-800 p-4 text-sm text-gray-400">
                    Sin eventos en este rango para tus {formatNumber(calendar.held_count, { maximumFractionDigits: 0 })} posiciones abiertas.
                </p>
            ) : (
                <ol className="flex flex-col gap-4">
                    {groups.map(([day, events]) => (
                        <li key={day} className="rounded-lg border border-gray-800 bg-surface-1 p-4">
                            <h2 className="text-sm font-semibold capitalize text-gray-200">
                                {formatMarketDate(day, { weekday: 'long', day: 'numeric', month: 'long' })}
                            </h2>
                            <ul className="mt-3 flex flex-col gap-2">
                                {events.map((event) => (
                                    <li
                                        key={`${event.type}-${event.ticker}-${event.date}`}
                                        className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm"
                                    >
                                        <span className="font-mono font-semibold text-teal-300">{event.ticker}</span>
                                        <span className="text-gray-100">{TYPE_LABEL[event.type] ?? event.title}</span>
                                        {event.detail ? <span className="text-gray-400">{event.detail}</span> : null}
                                        <span className="ml-auto text-xs text-gray-500">Fuente: {event.source}</span>
                                    </li>
                                ))}
                            </ul>
                        </li>
                    ))}
                </ol>
            )}
        </main>
    );
}
