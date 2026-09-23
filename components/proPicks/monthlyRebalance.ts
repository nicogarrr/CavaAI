/**
 * Ayudas puras (sin React ni servidor) para el rebalanceo mensual de CavaAI Propicks.
 *
 * - Catálogo canónico de las 4 estrategias públicas. Si el servidor aún no provee
 *   alguna (las añaden otros agentes en lib/utils/proPicksStrategies.ts), se marca
 *   como no disponible y la UI muestra un estado «sin datos» honesto.
 * - Snapshot mensual JSON descargable + diff entra/sale con motivo trazable.
 * - Acceso a campos de otros agentes (overlays, snapshots, métricas netas) siempre
 *   con optional chaining y fallbacks, para no romper si aún no existen.
 */

import type { ProPick } from '@/lib/actions/proPicks.actions';

export interface StrategyCatalogEntry {
    id: string;
    name: string;
    description: string;
}

/** Catálogo público de las 4 estrategias. Nombres y textos en español. */
export const STRATEGY_CATALOG: StrategyCatalogEntry[] = [
    {
        id: 'adaptive',
        name: 'Selección Adaptativa IA',
        description:
            'La IA reparte el peso entre valor, crecimiento y rentabilidad según el momento de mercado.',
    },
    {
        id: 'value',
        name: 'Value',
        description:
            'Prioriza acciones baratas por fundamentales frente a su sector y con balance sólido.',
    },
    {
        id: 'momentum',
        name: 'Momentum',
        description:
            'Prioriza acciones con tendencia alcista sostenida y fuerza relativa frente al mercado.',
    },
    {
        id: 'defensiva',
        name: 'Defensiva',
        description:
            'Prioriza baja volatilidad, dividendos estables y salud financiera para capear caídas.',
    },
];

export interface ServerStrategy {
    id: string;
    name: string;
    description: string;
}

export interface MergedStrategy extends StrategyCatalogEntry {
    /** true si el servidor la provee (hay selección y backtest reales). */
    available: boolean;
}

/**
 * Fusiona las estrategias del servidor con el catálogo público.
 * Las que el servidor aún no provee quedan como available: false («sin datos»).
 */
export function mergeStrategies(serverStrategies: ServerStrategy[]): MergedStrategy[] {
    const byId = new Map(serverStrategies.map((s) => [s.id, s]));
    return STRATEGY_CATALOG.map((entry) => {
        const server = byId.get(entry.id);
        if (!server) return { ...entry, available: false };
        return {
            id: entry.id,
            name: server.name || entry.name,
            description: server.description || entry.description,
            available: true,
        };
    });
}

/** Motivo trazable de un pick: texto visible + métrica y valor verificables. */
export interface TraceableReason {
    text: string;
    metric?: string;
    value?: number | string;
}

/**
 * Overlay aportado por el pipeline de señales (ver lib/utils/propicksSignals.ts,
 * tipo SignalOverlay: { factor, impact, detail, metric, value, asOf }).
 * Aquí se usa una forma estructural mínima con todo opcional: se accede con
 * optional chaining para no romper si el shape evoluciona. No se importa el
 * módulo de señales porque es solo-uso-en-servidor.
 */
interface OverlayLike {
    detail?: unknown;
    text?: unknown;
    reason?: unknown;
    label?: unknown;
    metric?: unknown;
    value?: unknown;
    factor?: unknown;
}

function overlaysOf(pick: ProPick): OverlayLike[] {
    const raw = (pick as { overlays?: unknown }).overlays;
    return Array.isArray(raw) ? (raw as OverlayLike[]) : [];
}

function overlayText(o: OverlayLike): string | undefined {
    for (const key of ['detail', 'text', 'reason', 'label'] as const) {
        const v = o[key];
        if (typeof v === 'string' && v.length > 0) return v;
    }
    return undefined;
}

/**
 * Motivo principal de un valor: primer confidenceReason (trazable a facts),
 * complementado con overlays si el pipeline los aporta.
 * Ningún número sin fuente: todo sale de confidenceReasons/overlays/facts.
 */
export function pickReason(pick: ProPick): TraceableReason {
    const overlay = overlaysOf(pick).find((o) => overlayText(o));
    if (overlay) {
        const metric = typeof overlay.metric === 'string' ? overlay.metric : undefined;
        const value =
            typeof overlay.value === 'number' || typeof overlay.value === 'string'
                ? overlay.value
                : undefined;
        const text = overlayText(overlay);
        if (text) return { text, metric, value };
    }
    const first = pick.confidenceReasons?.[0];
    if (first?.text) {
        return { text: first.text, metric: first.metric, value: first.value };
    }
    return { text: `Score ${pick.score}/100 con confianza ${pick.confidenceLevel}` };
}

/** Todos los motivos trazables de un pick (para la vista de rebalanceo). */
export function pickReasons(pick: ProPick): TraceableReason[] {
    const reasons: TraceableReason[] = (pick.confidenceReasons ?? [])
        .filter((r) => r?.text)
        .map((r) => ({ text: r.text, metric: r.metric, value: r.value }));
    for (const o of overlaysOf(pick)) {
        const text = overlayText(o);
        if (text && !reasons.some((r) => r.text === text)) {
            const metric = typeof o.metric === 'string' ? o.metric : undefined;
            const value =
                typeof o.value === 'number' || typeof o.value === 'string' ? o.value : undefined;
            reasons.push({ text, metric, value });
        }
    }
    return reasons.slice(0, 4);
}

export interface SnapshotPick {
    symbol: string;
    company: string;
    score: number;
    confidence: number;
    confidenceLevel: string;
    reasons: TraceableReason[];
    facts: Record<string, number | string>;
    asOf: string;
}

export interface MonthlySnapshot {
    kind: 'cavaai-propicks-monthly-snapshot';
    version: 1;
    /** Mes en formato YYYY-MM. */
    month: string;
    strategyId: string;
    generatedAt: string;
    picks: SnapshotPick[];
}

/** Clave de mes YYYY-MM para una fecha. */
export function monthKey(date: Date = new Date()): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    return `${y}-${m}`;
}

/** Etiqueta de mes en español («septiembre de 2026»). */
export function monthLabelEs(month: string): string {
    const [y, m] = month.split('-').map(Number);
    if (!y || !m) return month;
    return new Date(y, m - 1, 1).toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });
}

export function toSnapshotPick(pick: ProPick): SnapshotPick {
    return {
        symbol: pick.symbol,
        company: pick.company,
        score: pick.score,
        confidence: pick.confidence,
        confidenceLevel: pick.confidenceLevel,
        reasons: pickReasons(pick),
        facts: { ...(pick.facts ?? {}) },
        asOf: pick.asOf,
    };
}

export function buildMonthlySnapshot(
    picks: ProPick[],
    strategyId: string,
    month: string = monthKey(),
    generatedAt: string = new Date().toISOString(),
): MonthlySnapshot {
    return {
        kind: 'cavaai-propicks-monthly-snapshot',
        version: 1,
        month,
        strategyId,
        generatedAt,
        picks: picks.map(toSnapshotPick),
    };
}

export interface RebalanceMove {
    symbol: string;
    company: string;
    reason: TraceableReason;
}

export interface RebalanceDiff {
    entered: RebalanceMove[];
    exited: RebalanceMove[];
    kept: string[];
}

/**
 * Diff entra/sale entre la selección actual y el snapshot del mes anterior.
 * Sin snapshot previo: todo es «entra» respecto a vacío y `hasPrevious` es false,
 * para que la UI lo diga honestamente en lugar de inventar un mes anterior.
 */
export function diffSnapshots(
    current: ProPick[],
    previous: MonthlySnapshot | null | undefined,
): RebalanceDiff & { hasPrevious: boolean } {
    if (!previous || !Array.isArray(previous.picks)) {
        return {
            entered: current.map((p) => ({
                symbol: p.symbol,
                company: p.company,
                reason: pickReason(p),
            })),
            exited: [],
            kept: [],
            hasPrevious: false,
        };
    }
    const prevBySymbol = new Map(previous.picks.map((p) => [p.symbol, p]));
    const currBySymbol = new Map(current.map((p) => [p.symbol, p]));
    const entered: RebalanceMove[] = [];
    const exited: RebalanceMove[] = [];
    const kept: string[] = [];
    for (const pick of current) {
        if (prevBySymbol.has(pick.symbol)) kept.push(pick.symbol);
        else entered.push({ symbol: pick.symbol, company: pick.company, reason: pickReason(pick) });
    }
    for (const prev of previous.picks) {
        if (!currBySymbol.has(prev.symbol)) {
            const reason = prev.reasons?.[0] ?? { text: 'Estaba en la selección del mes anterior' };
            exited.push({ symbol: prev.symbol, company: prev.company, reason });
        }
    }
    return { entered, exited, kept, hasPrevious: true };
}

/** Type guard para snapshots cargados desde un archivo JSON. */
export function isMonthlySnapshot(value: unknown): value is MonthlySnapshot {
    if (typeof value !== 'object' || value === null) return false;
    const v = value as Record<string, unknown>;
    return (
        v.kind === 'cavaai-propicks-monthly-snapshot' &&
        Array.isArray(v.picks) &&
        typeof v.month === 'string'
    );
}

function movementLine(
    symbol: string,
    company: string,
    movement: 'entra' | 'sale',
    reasonText: string,
): string {
    const icon = movement === 'entra' ? '🟢' : '🔴';
    return `${icon} ${symbol} (${company}) ${movement === 'entra' ? 'entra' : 'sale'}: ${reasonText}`;
}

/**
 * Compone el mensaje Telegram del digest en español (entra/sale/motivo).
 * Cada motivo viene de confidenceReasons/overlays: ningún número sin fuente.
 * `reasonOf` resuelve el motivo de un símbolo vigente (p. ej. desde el ProPick).
 */
export function composeDigestMessage(
    diff: RebalanceDiff & { hasPrevious: boolean },
    month: string,
    strategyName: string,
    reasonOf?: (symbol: string) => string | undefined,
): string {
    const lines: string[] = [
        `📊 CavaAI Propicks — rebalanceo de ${monthLabelEs(month)}`,
        `Estrategia: ${strategyName}`,
        '',
    ];
    if (!diff.hasPrevious) {
        lines.push('Primera selección publicada (aún sin mes anterior con el que comparar).');
        lines.push('');
    }
    if (diff.entered.length > 0) {
        lines.push(`🟢 Entran (${diff.entered.length}):`);
        for (const m of diff.entered) {
            lines.push(`· ${movementLine(m.symbol, m.company, 'entra', reasonOf?.(m.symbol) ?? m.reason.text)}`);
        }
        lines.push('');
    }
    if (diff.exited.length > 0) {
        lines.push(`🔴 Salen (${diff.exited.length}):`);
        for (const m of diff.exited) {
            lines.push(`· ${movementLine(m.symbol, m.company, 'sale', m.reason.text)}`);
        }
        lines.push('');
    }
    if (diff.entered.length === 0 && diff.exited.length === 0 && diff.hasPrevious) {
        lines.push('Sin cambios: la selección se mantiene igual que el mes anterior.');
        lines.push('');
    }
    if (diff.kept.length > 0) {
        lines.push(`Se mantienen (${diff.kept.length}): ${diff.kept.join(', ')}.`);
    }
    lines.push('');
    lines.push('Datos al cierre usados en cada ficha. No es asesoramiento de inversión.');
    return lines.join('\n');
}
