import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, FileSearch, Library, Newspaper, Settings, Workflow } from 'lucide-react';

import { getResearchCompanySnapshot, getResearchDashboard } from '@/lib/actions/research.actions';
import BackendOffline from '@/components/system/BackendOffline';
import { isBackendUnavailableError } from '@/lib/backend-offline';
import WorkProductButton from '@/components/work-products/WorkProductButton';
import { formatDate, formatMoney, formatNumber, formatPercent } from '@/lib/format';
import { Badge } from '@/components/ui/badge';
import { EmptyLink, EmptyState } from '@/components/ui/empty-state';
import { PageHeader } from '@/components/ui/page-header';
import { Panel } from '@/components/ui/panel';
import { Stat } from '@/components/ui/stat';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
    title: 'Índice de research',
    description:
        'Índice de las empresas con research en CavaAI: salud de su research, rating de la última tesis y fecha de la última versión.',
};

/**
 * El registro de empresas (`/api/companies`) solo trae la ficha de la empresa,
 * así que el rating y la fecha de la última tesis salen de su snapshot. Se
 * piden en paralelo (uno por empresa) y con tope: por encima de este número se
 * listan todas las empresas pero solo las primeras llevan detalle de tesis, y
 * se dice en pantalla en lugar de cortar en silencio.
 */
const THESIS_DETAIL_LIMIT = 40;

// Cada snapshot toca varias tablas del motor: pedir 40 a la vez en un solo
// Promise.all es una estampida contra el backend (y contra el pool de
// conexiones). 6 concurrentes mantiene el indice agil sin ahogarlo.
const SNAPSHOT_CONCURRENCY = 6;

async function mapWithConcurrency<T, R>(
    items: T[],
    limit: number,
    fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
    const results: R[] = new Array(items.length) as R[];
    let next = 0;
    async function worker() {
        while (next < items.length) {
            const index = next;
            next += 1;
            results[index] = await fn(items[index], index);
        }
    }
    await Promise.all(
        Array.from({ length: Math.min(limit, items.length) }, () => worker()),
    );
    return results;
}

/** Ratings persistidos por el backend, en español (mismo mapa que la ficha). */
const RATING_LABELS: Record<string, string> = {
    buy: 'compra',
    accumulate: 'acumular',
    overweight: 'sobreponderar',
    hold: 'mantener',
    underweight: 'infraponderar',
    trim: 'recortar',
    sell: 'venta',
    avoid: 'evitar',
    watch: 'seguimiento',
};

const HEALTH_LABELS: Record<string, string> = {
    healthy: 'research completo',
    review_required: 'requiere revisión',
    incomplete: 'incompleto',
    empty: 'sin datos',
};

const HEALTH_TONES: Record<string, string> = {
    healthy: 'text-good',
    review_required: 'text-warn',
    incomplete: 'text-warn',
    empty: 'text-gray-400',
};

/**
 * Las cuatro subrutas del grupo Research. Se enlazan desde el propio índice
 * para no obligar a entrar al menú lateral (o a saber la URL) para llegar a
 * la herramienta que se usa a diario.
 */
const TOOLS = [
    {
        href: '/research/news',
        label: 'Noticias',
        icon: Newspaper,
        description: 'Eventos clasificados por materialidad e impacto sobre tus posiciones.',
    },
    {
        href: '/research/sources',
        label: 'Fuentes',
        icon: Library,
        description: 'Documentos, transcripts y auditorías que alimentan tesis, RAG y valoraciones.',
    },
    {
        href: '/research/workflows',
        label: 'Workflows',
        icon: Workflow,
        description: 'Flujos de investigación del motor Python y su estado real de implementación.',
    },
    {
        href: '/research/settings',
        label: 'Ajustes',
        icon: Settings,
        description: 'Conectores externos, presupuesto del modelo de lenguaje y runtime del backend.',
    },
];

type Dashboard = Awaited<ReturnType<typeof getResearchDashboard>>;
type Company = Dashboard['companies'][number];
type CompanySnapshot = Awaited<ReturnType<typeof getResearchCompanySnapshot>>;

type CompanyRow = {
    company: Company;
    /** null = la empresa existe en el registro pero aún no tiene research. */
    snapshot: CompanySnapshot | null;
    /** true = el snapshot no se pudo leer (backend intermitente). */
    unreadable: boolean;
    /** true = más allá del tope de detalle de esta visita. */
    pendiente: boolean;
};

function money(value: number) {
    return formatMoney(value, 'USD', { maximumFractionDigits: 0 });
}

function pct(value: number) {
    return formatPercent(value, { fromRatio: true, digits: 1 });
}

function ratingLabel(value: string | null | undefined): string {
    if (!value) return 'Sin rating';
    return RATING_LABELS[value] ?? value.replaceAll('_', ' ');
}

/** Una fila del índice: ticker, nombre, salud del research y última tesis. */
function CompanyCard({ row }: { row: CompanyRow }) {
    const { company, snapshot, unreadable, pendiente } = row;
    const health = snapshot?.research_health;
    const thesis = snapshot?.latest_thesis ?? null;

    return (
        <li>
            <Link
                className="block rounded-xl border border-gray-700/50 bg-surface-1 p-4 transition hover:border-teal-700"
                href={`/research/${encodeURIComponent(company.ticker)}`}
            >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="text-base font-semibold text-gray-100">{company.ticker}</span>
                    <span className="min-w-0 truncate text-sm text-gray-400">{company.name}</span>
                </div>
                <p className="mt-1 truncate text-xs text-gray-500">
                    {company.sector || 'Sector sin dato'}
                    {company.industry ? ` · ${company.industry}` : ''}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                    {unreadable ? (
                        <span className="text-xs text-warn">No se pudo leer su research</span>
                    ) : pendiente ? (
                        <span className="text-xs text-gray-500">Detalle de tesis no cargado en esta visita</span>
                    ) : !snapshot ? (
                        <span className="text-xs text-gray-500">Sin research generado</span>
                    ) : (
                        <>
                            <span className={`text-xs font-semibold ${HEALTH_TONES[health?.status ?? 'empty'] ?? 'text-gray-400'}`}>
                                Salud {formatNumber(health?.score)}/100
                            </span>
                            <Badge variant="outline">{HEALTH_LABELS[health?.status ?? ''] ?? 'estado sin dato'}</Badge>
                        </>
                    )}
                    {thesis ? (
                        <>
                            <Badge>{ratingLabel(thesis.rating)}</Badge>
                            <span className="text-xs text-gray-500">
                                v{formatNumber(thesis.version)} · {formatDate(thesis.created_at)}
                            </span>
                        </>
                    ) : null}
                </div>
            </Link>
        </li>
    );
}

export default async function ResearchPage() {
    let dashboard: Dashboard;
    try {
        dashboard = await getResearchDashboard();
    } catch (error) {
        if (isBackendUnavailableError(error)) {
            return <BackendOffline feature="Research" retryHref="/research" />;
        }
        throw error;
    }
    const { companies, portfolio } = dashboard;

    // Orden estable por ticker: el índice no debe reordenar solo entre renders.
    const ordered = [...companies].sort((left, right) => left.ticker.localeCompare(right.ticker, 'es'));
    const rows: CompanyRow[] = await mapWithConcurrency(
        ordered,
        SNAPSHOT_CONCURRENCY,
        async (company, index): Promise<CompanyRow> => {
            if (index >= THESIS_DETAIL_LIMIT) {
                // Se listan todas las empresas del registro; pasado el tope, la
                // ficha se abre sin pedir su snapshot en esta visita.
                return { company, snapshot: null, unreadable: false, pendiente: true };
            }
            try {
                return { company, snapshot: await getResearchCompanySnapshot(company.ticker), unreadable: false, pendiente: false };
            } catch {
                // Un snapshot que falla no puede tirar el índice entero: la
                // empresa se lista igual y se marca como no leída.
                return { company, snapshot: null, unreadable: true, pendiente: false };
            }
        },
    );
    const pendingCount = rows.filter((row) => row.pendiente).length;

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex max-w-7xl flex-col gap-6">
            <PageHeader
                actions={<WorkProductButton />}
                description="Todas las empresas con research en CavaAI, con la salud de su research, el rating de la última tesis y cuándo se generó. Abre una ficha para ver la tesis, los financieros, el modelo y la evidencia."
                kicker="Research OS"
                title="Índice de research"
            />

            <Panel
                description={
                    rows.length
                        ? 'Cada ficha agrupa su análisis en seis etapas: resumen, tesis, financieros, modelo, evidencia y seguimiento.'
                        : 'El registro se crea al generar el primer análisis de una empresa.'
                }
                title="Empresas con research"
            >
                {rows.length ? (
                    <ul className="grid gap-3 sm:grid-cols-2">
                        {rows.map((row) => (
                            <CompanyCard key={row.company.ticker} row={row} />
                        ))}
                    </ul>
                ) : (
                    <EmptyState
                        action={
                            <div className="flex flex-wrap justify-center gap-3">
                                <EmptyLink href="/search">Buscar una empresa</EmptyLink>
                                <EmptyLink href="/watchlist">Ver mi watchlist</EmptyLink>
                            </div>
                        }
                        description="Busca una empresa y genera su research desde su ficha: el motor reúne evidencia con fuentes trazables y construye la tesis paso a paso. También puedes empezar por tu watchlist."
                        icon={FileSearch}
                        title="Todavía no hay ninguna empresa con research."
                    />
                )}
                {pendingCount > 0 ? (
                    <p className="mt-4 text-xs text-gray-500">
                        El detalle de tesis (salud, rating y fecha) se pide al motor como mucho para {THESIS_DETAIL_LIMIT}{' '}
                        empresas por visita. Aquí se listan las {ordered.length}: las {pendingCount} últimas salen sin ese
                        detalle, y lo verás al abrir su ficha.
                    </p>
                ) : null}
            </Panel>

            {/*
                Las cuatro cifras de cartera que se pintaban aquí eran un
                mini-portfolio dentro de un índice de research, y las alertas de
                concentración vivían aquí y en /risk. Se quedan como bloque
                secundario con salida explícita a los dos sitios que las
                explican de verdad: la cartera y las concentraciones.
            */}
            <Panel
                actions={
                    <div className="flex flex-wrap items-center gap-2">
                        <Link
                            className="inline-flex items-center gap-1 text-sm text-teal-300 hover:text-teal-200"
                            href="/portfolio"
                        >
                            Ver la cartera <ArrowRight aria-hidden="true" className="h-4 w-4" />
                        </Link>
                        <Link
                            className="inline-flex items-center gap-1 text-sm text-teal-300 hover:text-teal-200"
                            href="/risk"
                        >
                            Ver concentraciones <ArrowRight aria-hidden="true" className="h-4 w-4" />
                        </Link>
                    </div>
                }
                description="Cuatro cifras para saber por dónde empezar. El detalle de posiciones está en la cartera y las concentraciones con sus alertas, en Exposiciones."
                density="compact"
                title="Contexto de cartera"
            >
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <Stat label="Valor total" size="sm" value={money(portfolio.total_value)} />
                    <Stat label="Renta variable" size="sm" value={money(portfolio.equity_value)} />
                    <Stat label="Top 1" size="sm" tone="warn" value={pct(portfolio.top_1_weight)} />
                    <Stat
                        label="Alertas de concentración"
                        size="sm"
                        tone={portfolio.alerts.length ? 'bad' : 'good'}
                        value={String(portfolio.alerts.length)}
                    />
                </div>
            </Panel>

            <Panel
                description="Las cuatro herramientas de research. También están en el menú lateral, dentro del grupo Research."
                title="Herramientas de research"
            >
                <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {TOOLS.map((tool) => (
                        <li key={tool.href}>
                            <Link
                                className="flex h-full flex-col gap-2 rounded-xl border border-gray-700/50 bg-surface-1 p-4 transition hover:border-teal-700"
                                href={tool.href}
                            >
                                <span className="flex items-center gap-2 text-sm font-semibold text-gray-100">
                                    <tool.icon aria-hidden="true" className="h-4 w-4 text-teal-300" />
                                    {tool.label}
                                </span>
                                <span className="text-xs leading-5 text-gray-500">{tool.description}</span>
                            </Link>
                        </li>
                    ))}
                </ul>
            </Panel>
        </main>
    );
}
