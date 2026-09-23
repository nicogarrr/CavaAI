'use server';

/**
 * Digest mensual de rebalanceo de CavaAI Propicks → Telegram.
 *
 * CÓMO PROGRAMARLA EL DÍA 1 (sin infraestructura nueva en este cambio):
 * - Esta función es una server action: hay que invocarla el día 1 de cada mes
 *   desde un programador EXTERNO ya disponible en tu despliegue, por ejemplo:
 *     a) cron del sistema que llame a una ruta/thin-wrapper interno que a su vez
 *        invoque sendMonthlyRebalanceDigest(),
 *     b) GitHub Actions con `schedule: cron: '0 8 1 * *'` que dispare esa misma
 *        llamada autenticada,
 *     c) el scheduler del backend de research, si ya programa otras tareas.
 * - No se crea aquí ningún cron, worker ni tabla: este fichero solo calcula,
 *   compara, compone y envía. El programador lo pone el despliegue.
 * - Requiere usuario autenticado: reutiliza generateProPicksForStrategy(), que
 *   exige sesión (requireAuthenticatedUser). La invocación programada debe
 *   ejecutarse con un contexto autenticado o fallará con error explícito.
 *
 * ENVÍO (reutiliza la infraestructura de alertas existente, sin tocarla):
 * - Mismo cliente que lib/actions/alerts.actions.ts: researchRequest/jsonBody
 *   de @/lib/research/client contra el backend de research.
 * - Por cada movimiento del rebalanceo se crea una alerta de tipo "news" con el
 *   motivo trazable, se fija su canal a ["telegram"] (PATCH
 *   /api/alerts/{id}/channels) y se dispara el envío (POST
 *   /api/alerts/{id}/dispatch). El backend entrega a Telegram solo si el usuario
 *   tiene ese canal configurado; si no, el dispatch queda registrado igualmente.
 */

import { generateProPicksForStrategy, getAvailableStrategies } from '@/lib/actions/proPicks.actions';
import { jsonBody, researchRequest } from '@/lib/research/client';
import {
    composeDigestMessage,
    diffSnapshots,
    mergeStrategies,
    monthKey,
    pickReason,
    type MonthlySnapshot,
    type RebalanceDiff,
} from '@/components/proPicks/monthlyRebalance';

export type { MonthlySnapshot, RebalanceDiff };

export interface DigestPerSymbol {
    symbol: string;
    movement: 'entra' | 'sale';
    alertId: number | null;
    dispatched: boolean;
    error?: string;
}

export interface DigestResult {
    ok: boolean;
    month: string;
    strategyId: string;
    strategyName: string;
    entered: string[];
    exited: string[];
    keptCount: number;
    hasPrevious: boolean;
    message: string;
    perSymbol: DigestPerSymbol[];
    error?: string;
}

const MAX_ALERTS_PER_DIGEST = 8;

interface AlertRuleOut {
    id: number;
}

async function dispatchSymbolAlert(
    ticker: string,
    movement: 'entra' | 'sale',
    reasonText: string,
): Promise<{ alertId: number | null; dispatched: boolean; error?: string }> {
    try {
        const symbol = ticker.trim().toUpperCase();
        if (!/^[A-Z0-9.\-]{1,20}$/.test(symbol)) {
            return { alertId: null, dispatched: false, error: `Ticker no válido: ${ticker}` };
        }
        await researchRequest('/api/companies/ensure', {
            method: 'POST',
            body: jsonBody({ ticker: symbol }),
        });
        const rule = await researchRequest<AlertRuleOut>('/api/alerts', {
            method: 'POST',
            body: jsonBody({
                ticker: symbol,
                alert_type: 'news',
                operator: '==',
                value: `Propicks mensual: ${symbol} ${movement} — ${reasonText}`.slice(0, 500),
            }),
        });
        await researchRequest(`/api/alerts/${rule.id}/channels`, {
            method: 'PATCH',
            body: jsonBody({ channels: ['telegram'] }),
        });
        await researchRequest(`/api/alerts/${rule.id}/dispatch`, { method: 'POST' });
        return { alertId: rule.id, dispatched: true };
    } catch (error) {
        return {
            alertId: null,
            dispatched: false,
            error: error instanceof Error ? error.message : String(error),
        };
    }
}

/**
 * Calcula la selección del mes (reutilizando la selección existente), la compara
 * con la del mes anterior, compone el mensaje en español y la envía a Telegram
 * con la infraestructura de alertas existente.
 *
 * @param previousSnapshot Snapshot del mes anterior (el JSON descargado desde la
 *   vista de rebalanceo). Sin él, el digest se envía como primera publicación.
 */
export async function sendMonthlyRebalanceDigest(input?: {
    strategyId?: string;
    previousSnapshot?: MonthlySnapshot | null;
}): Promise<DigestResult> {
    const strategyId = input?.strategyId ?? 'adaptive';
    const month = monthKey();
    try {
        const [serverStrategies, current] = await Promise.all([
            getAvailableStrategies(),
            generateProPicksForStrategy(strategyId, 10),
        ]);
        const merged = mergeStrategies(serverStrategies);
        const entry = merged.find((s) => s.id === strategyId);
        // generateProPicksForStrategy cae al fallback 'adaptive' si el id no existe:
        // no publicar una estrategia como si tuviera datos cuando no los tiene.
        if (!entry?.available) {
            return {
                ok: false,
                month,
                strategyId,
                strategyName: entry?.name ?? strategyId,
                entered: [],
                exited: [],
                keptCount: 0,
                hasPrevious: false,
                message: '',
                perSymbol: [],
                error: `La estrategia ${strategyId} aún no tiene datos publicados`,
            };
        }
        const qualified = current.filter((p) => p.score >= 60);
        const selection = (qualified.length > 0 ? qualified : current).slice(0, 10);
        const diff = diffSnapshots(selection, input?.previousSnapshot ?? null);
        const currBySymbol = new Map(selection.map((p) => [p.symbol, pickReason(p).text]));
        const message = composeDigestMessage(diff, month, entry.name, (s) => currBySymbol.get(s));

        const moves: Array<{ symbol: string; company: string; movement: 'entra' | 'sale'; reason: string }> = [
            ...diff.entered.map((m) => ({
                symbol: m.symbol,
                company: m.company,
                movement: 'entra' as const,
                reason: m.reason.text,
            })),
            ...diff.exited.map((m) => ({
                symbol: m.symbol,
                company: m.company,
                movement: 'sale' as const,
                reason: m.reason.text,
            })),
        ].slice(0, MAX_ALERTS_PER_DIGEST);

        // Sin movimientos y con previo: un latido sobre el primer valor vigente.
        if (moves.length === 0 && selection.length > 0) {
            const first = selection[0];
            moves.push({
                symbol: first.symbol,
                company: first.company,
                movement: 'entra',
                reason: diff.hasPrevious
                    ? 'Sin cambios en el rebalanceo mensual'
                    : 'Primera selección mensual publicada',
            });
        }

        const perSymbol: DigestPerSymbol[] = [];
        for (const move of moves) {
            const sent = await dispatchSymbolAlert(move.symbol, move.movement, move.reason);
            perSymbol.push({
                symbol: move.symbol,
                movement: move.movement,
                alertId: sent.alertId,
                dispatched: sent.dispatched,
                ...(sent.error ? { error: sent.error } : {}),
            });
        }

        const allOk = perSymbol.length > 0 && perSymbol.every((p) => p.dispatched);
        return {
            ok: allOk,
            month,
            strategyId,
            strategyName: entry.name,
            entered: diff.entered.map((m) => m.symbol),
            exited: diff.exited.map((m) => m.symbol),
            keptCount: diff.kept.length,
            hasPrevious: diff.hasPrevious,
            message,
            perSymbol,
            ...(allOk ? {} : { error: 'Algún envío no pudo completarse (ver perSymbol)' }),
        };
    } catch (error) {
        const serverStrategies = await getAvailableStrategies().catch(() => []);
        const name =
            mergeStrategies(serverStrategies).find((s) => s.id === strategyId)?.name ?? strategyId;
        return {
            ok: false,
            month,
            strategyId,
            strategyName: name,
            entered: [],
            exited: [],
            keptCount: 0,
            hasPrevious: false,
            message: '',
            perSymbol: [],
            error: error instanceof Error ? error.message : String(error),
        };
    }
}
