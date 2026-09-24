'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { jsonBody, researchRequest } from '@/lib/research/client';
import { cachedFetch } from '@/lib/cache/memoryTTL';
import { requestCache } from '@/lib/cache/requestCache';
import { AuthorizationError, ValidationError } from '@/lib/types/errors';

const FINNHUB_BASE_URL = 'https://finnhub.io/api/v1';
const FINNHUB_API_KEY = process.env.FINNHUB_API_KEY;

async function resolveUserId(requestedUserId?: string): Promise<string> {
    const user = await requireAuthenticatedUser();
    if (requestedUserId && requestedUserId !== user.id) {
        throw new AuthorizationError('Cannot access another user portfolio');
    }
    return user.id;
}

function invalidatePortfolioReads(userId: string): void {
    for (const suffix of ['positions', 'summary', 'transactions', 'scores', 'tearsheet', 'dividends']) {
        requestCache.invalidate(`portfolio:${userId}:${suffix}`);
    }
}

async function getQuote(symbol: string): Promise<{ c: number } | null> {
    try {
        if (!FINNHUB_API_KEY) return null;
        const response = await fetch(
            `${FINNHUB_BASE_URL}/quote?symbol=${encodeURIComponent(symbol)}&token=${FINNHUB_API_KEY}`,
            { next: { revalidate: 60 } }
        );
        if (!response.ok) return null;
        return await response.json();
    } catch (error) {
        console.error(`Error fetching quote for ${symbol}:`, error);
        return null;
    }
}

export type PortfolioHolding = {
    symbol: string;
    quantity: number;
    avgPrice: number;
    currentPrice: number;
    value: number;
    cost: number;
    gain: number;
    gainPercent: number;
    nativeCurrency: string;
    baseCurrency: string;
    fxMissing: boolean;
    firstBuyDate: string | null;
    holdingDays: number | null;
    fiscalBucket: 'corto_plazo' | 'largo_plazo' | null;
};

export type PortfolioSummary = {
    totalValue: number;
    totalCost: number;
    totalGain: number;
    totalGainPercent: number;
    holdings: PortfolioHolding[];
    baseCurrency: string;
    status: 'ok' | 'incomplete_fx';
    missingFx: Array<Record<string, unknown>>;
};

type ResearchPortfolioTransaction = {
    id: number;
    ticker: string;
    action: 'buy' | 'sell';
    quantity: number;
    price: number;
    fees: number;
    currency: string;
    trade_date: string;
    notes?: string | null;
    created_at: string;
    updated_at: string;
};

type ResearchPortfolioPosition = {
    ticker: string;
    quantity: number;
    average_cost: number;
    market_price: number;
    market_value: number;
    unrealized_pnl: number;
    currency: string;
    native_currency: string;
    base_currency: string;
    realized_pnl: number;
    cost_basis: number;
    as_of: string;
    market_value_native: number;
    market_value_base: number | null;
    cost_basis_native: number;
    cost_basis_base: number | null;
    unrealized_pnl_base: number | null;
    realized_pnl_base: number | null;
    fx_rate: number | null;
    first_buy_date: string | null;
    holding_days: number | null;
    fiscal_bucket: 'corto_plazo' | 'largo_plazo' | null;
};

type ResearchPortfolioSummaryResponse = {
    total_value: number;
    equity_value: number;
    status: 'ok' | 'incomplete_fx';
    base_currency: string;
    missing_fx: Array<Record<string, unknown>>;
};

export async function addTransaction(
    userId: string,
    symbol: string,
    type: 'buy' | 'sell',
    quantity: number,
    price: number,
    date: Date,
    notes?: string,
    currency = 'USD',
): Promise<{ success: boolean; error?: string }> {
    const canonicalUserId = await resolveUserId(userId);
    if (!Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(price) || price < 0) {
        throw new ValidationError('Quantity must be positive and price cannot be negative');
    }
    await researchRequest<ResearchPortfolioTransaction>('/api/portfolio/transactions', {
        method: 'POST',
        body: jsonBody({
            ticker: symbol.toUpperCase(),
            action: type,
            quantity,
            price,
            trade_date: date.toISOString().slice(0, 10),
            notes: notes || null,
            currency: currency.toUpperCase(),
            fees: 0,
        }),
    });
    invalidatePortfolioReads(canonicalUserId);
    return { success: true };
}

export async function getPortfolioTransactions(userId: string) {
    const canonicalUserId = await resolveUserId(userId);
    const transactions = await cachedFetch(
        `portfolio:${canonicalUserId}:transactions`,
        () => researchRequest<ResearchPortfolioTransaction[]>('/api/portfolio/transactions', { fast: true }),
        15,
    );
    return transactions.map((transaction) => ({
        _id: String(transaction.id),
        symbol: transaction.ticker,
        type: transaction.action,
        quantity: transaction.quantity,
        price: transaction.price,
        date: transaction.trade_date,
        notes: transaction.notes ?? undefined,
        currency: transaction.currency,
        createdAt: transaction.created_at,
        updatedAt: transaction.updated_at,
    }));
}

export async function getPortfolioSummary(userId: string): Promise<PortfolioSummary> {
    const canonicalUserId = await resolveUserId(userId);
    const [positions, backendSummary] = await Promise.all([
        cachedFetch(
            `portfolio:${canonicalUserId}:positions`,
            () => researchRequest<ResearchPortfolioPosition[]>('/api/portfolio/positions', { fast: true }),
            15,
        ),
        cachedFetch(
            `portfolio:${canonicalUserId}:summary`,
            () => researchRequest<ResearchPortfolioSummaryResponse>('/api/portfolio/summary', { fast: true }),
            15,
        ),
    ]);
    const holdings = positions.map((position): PortfolioHolding => {
        const currentPrice = position.market_price;
        const cost = position.cost_basis_base ?? 0;
        const value = position.market_value_base ?? 0;
        const gain = position.unrealized_pnl_base ?? 0;
        return {
            symbol: position.ticker,
            quantity: position.quantity,
            avgPrice: position.average_cost,
            currentPrice,
            value,
            cost,
            gain,
            gainPercent: cost > 0 ? (gain / cost) * 100 : 0,
            nativeCurrency: position.native_currency,
            baseCurrency: position.base_currency,
            fxMissing: position.market_value_base === null || position.cost_basis_base === null,
            firstBuyDate: position.first_buy_date ?? null,
            holdingDays: position.holding_days ?? null,
            fiscalBucket: position.fiscal_bucket ?? null,
        };
    });
    const totalValue = backendSummary.total_value;
    const totalCost = holdings.reduce((sum, holding) => sum + holding.cost, 0);
    const totalGain = holdings.reduce((sum, holding) => sum + holding.gain, 0);
    return {
        totalValue,
        totalCost,
        totalGain,
        totalGainPercent: totalCost > 0 ? (totalGain / totalCost) * 100 : 0,
        holdings: holdings.sort((a, b) => b.value - a.value),
        baseCurrency: backendSummary.base_currency,
        status: backendSummary.status,
        missingFx: backendSummary.missing_fx,
    };
}

// Actualizar transacción existente
export async function updateTransaction(
    userId: string,
    transactionId: string,
    symbol: string,
    type: 'buy' | 'sell',
    quantity: number,
    price: number,
    date: Date,
    notes?: string,
    currency = 'USD',
): Promise<{ success: boolean; error?: string }> {
    const canonicalUserId = await resolveUserId(userId);
    if (!Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(price) || price < 0) {
        throw new ValidationError('Quantity must be positive and price cannot be negative');
    }
    await researchRequest<ResearchPortfolioTransaction>(
        `/api/portfolio/transactions/${encodeURIComponent(transactionId)}`,
        {
            method: 'PUT',
            body: jsonBody({
                ticker: symbol.toUpperCase(),
                action: type,
                quantity,
                price,
                trade_date: date.toISOString().slice(0, 10),
                notes: notes || null,
                currency: currency.toUpperCase(),
                fees: 0,
            }),
        },
    );
    invalidatePortfolioReads(canonicalUserId);
    return { success: true };
}

export async function deleteTransaction(userId: string, transactionId: string): Promise<{ success: boolean; error?: string }> {
    const canonicalUserId = await resolveUserId(userId);
    await researchRequest<void>(`/api/portfolio/transactions/${encodeURIComponent(transactionId)}`, {
        method: 'DELETE',
    });
    invalidatePortfolioReads(canonicalUserId);
    return { success: true };
}

// Eliminar todas las transacciones de un símbolo (eliminar posición)
export async function deleteHolding(userId: string, symbol: string): Promise<{ success: boolean; error?: string }> {
    const canonicalUserId = await resolveUserId(userId);
    await researchRequest<void>(`/api/portfolio/holdings/${encodeURIComponent(symbol.toUpperCase())}`, {
        method: 'DELETE',
    });
    invalidatePortfolioReads(canonicalUserId);
    return { success: true };
}

// ============================================
// Funciones adicionales para Portfolio
// ============================================

export type PortfolioAnalyticsResult = {
    cagr: number | null;
    volatility_ann: number | null;
    max_drawdown: number | null;
    sharpe: number | null;
    sortino: number | null;
    var_95: number | null;
    cvar_95: number | null;
    win_rate: number | null;
    calmar: number | null;
    score_quality: number;
    score_growth: number;
    score_value: number;
    score_cagr3y: number | null;
    trading_days: number;
    start_date: string;
    end_date: string;
    alpha?: number | null;
    beta?: number | null;
    information_ratio?: number | null;
};

export type PortfolioPerformanceHistory = {
    dates: string[];
    nav: number[];
    daily_returns: number[];
    twr: number;
    start_date: string;
    end_date: string;
};

// Obtener métricas reales del portfolio via quantstats-pro
export async function getPortfolioScores(userId: string): Promise<{
    quality: number;
    growth: number;
    value: number;
    dividend: number;
    cagr3y: number;
    analytics?: PortfolioAnalyticsResult;
    history?: PortfolioPerformanceHistory;
}> {
    const canonicalUserId = await resolveUserId(userId);
    const empty = { quality: 0, growth: 0, value: 0, dividend: 0, cagr3y: 0 };

    try {
        const summary = await getPortfolioSummary(canonicalUserId);
        if (summary.holdings.length === 0) return empty;

        // Scores 0-100 derivados de métricas reales del tearsheet
        // (GET /api/portfolio/tearsheet): bandas documentadas, sin inventos.
        // quality = consistencia (Sharpe/win_rate), growth = acumulado,
        // value = resiliencia (drawdown). Dividend queda en 0 hasta tener
        // motor de yield real.
        const clamp100 = (v: number) => Math.max(0, Math.min(100, Math.round(v)));
        const sheet = await getPortfolioTearsheet(canonicalUserId);
        // Real dividend score: trailing-12M declared-dividend yield from
        // GET /api/portfolio/dividends (FMP-ingested records, provenance
        // attached). Linear band documented here: 0% yield -> 0, 6% -> 100.
        // When no position has ingested dividend records the score stays 0
        // (same honest empty state as before, no fabricated yield).
        let dividendScore = 0;
        try {
            const dividends = await cachedFetch<{
                portfolio_yield: number | null;
                coverage: { positions_with_dividend_data: number };
            }>(
                `portfolio:${canonicalUserId}:dividends`,
                () => researchRequest<{
                    portfolio_yield: number | null;
                    coverage: { positions_with_dividend_data: number };
                }>('/api/portfolio/dividends', { fast: true }),
                30,
            );
            if (
                dividends.coverage.positions_with_dividend_data > 0 &&
                dividends.portfolio_yield != null
            ) {
                dividendScore = clamp100((dividends.portfolio_yield / 0.06) * 100);
            }
        } catch {
            // Endpoint unavailable: keep the honest zero state.
            dividendScore = 0;
        }
        const m = sheet?.metrics ?? null;
        const sharpe = m?.sharpe ?? null;
        const winRate = m?.win_rate ?? null;
        const maxDD = m?.max_drawdown ?? null;
        const cumulative = m?.cumulative_return ?? null;
        const quality = sharpe == null ? 0 : clamp100(50 + sharpe * 25);
        const growth = cumulative == null ? 0 : clamp100(50 + cumulative * 200);
        const value = maxDD == null ? 0 : clamp100(100 + maxDD * 200);
        const consistency = winRate == null ? quality : clamp100(quality * 0.7 + winRate * 100 * 0.3);
        const data: PortfolioAnalyticsResult = {
            cagr: cumulative,
            volatility_ann: null,
            max_drawdown: maxDD,
            sharpe,
            sortino: m?.sortino ?? null,
            var_95: null,
            cvar_95: null,
            win_rate: winRate,
            calmar: null,
            score_quality: consistency,
            score_growth: growth,
            score_value: value,
            score_cagr3y: null,
            trading_days: m?.periods_per_year ?? 252,
            start_date: '',
            end_date: '',
        };

        return {
            quality: data.score_quality ?? 0,
            growth: data.score_growth ?? 0,
            value: data.score_value ?? 0,
            dividend: dividendScore,
            cagr3y: data.cagr != null ? Math.round(data.cagr * 10000) / 100 : 0,
            analytics: data,
            history: undefined,
        };
    } catch (error) {
        console.error('Error getting portfolio scores:', error);
        return empty;
    }
}

// Añadir posición rápida desde buscador
export async function quickAddPosition(
    userId: string,
    symbol: string,
    shares: number,
    price: number
): Promise<{ success: boolean; error?: string }> {
    await resolveUserId(userId);
    return addTransaction(userId, symbol, 'buy', shares, price, new Date());
}

// Obtener holdings con peso de portfolio
export async function getPortfolioWithWeights(userId: string) {
    await resolveUserId(userId);
    const summary = await getPortfolioSummary(userId);

    return summary.holdings.map(h => ({
        ...h,
        weight: summary.totalValue > 0 ? (h.value / summary.totalValue) * 100 : 0
    }));
}

// Actualizar precios de holdings existentes (para refresco cliente)
export async function refreshPortfolioHoldings(holdings: PortfolioHolding[]): Promise<PortfolioHolding[]> {
    const user = await requireAuthenticatedUser();
    try {
        await Promise.all(holdings.map(async (h) => {
            const quote = await getQuote(h.symbol);
            if (!quote?.c) return;
            await researchRequest('/api/portfolio/prices', {
                method: 'PATCH',
                body: jsonBody({ ticker: h.symbol, price: quote.c }),
            });
        }));
        invalidatePortfolioReads(user.id);
        return (await getPortfolioSummary(user.id)).holdings;
    } catch (error) {
        console.error('Error refreshing portfolio holdings:', error);
        return holdings;
    }
}

// Actualizar TODO el portfolio: posiciones + KPIs (para botón de refresco completo)
export async function updateAllPortfolioPrices(userId: string): Promise<{
    summary: PortfolioSummary;
    scores: { quality: number; growth: number; value: number; dividend: number; cagr3y: number }
}> {
    await resolveUserId(userId);
    // Force fresh fetch of everything - no cache
    const [summary, scores] = await Promise.all([
        getPortfolioSummary(userId),
        getPortfolioScores(userId)
    ]);

    return { summary, scores };
}

export type IBKRImportResult = {
    status: string;
    positions_imported: number;
    cash_imported: number;
    trades_imported: number;
    dividends_imported: number;
    fees_imported: number;
    cash_transactions_imported: number;
    rows_skipped?: number;
    row_errors?: string[];
    portfolio_snapshot_id: number | null;
};

/**
 * Dispara la descarga del Flex statement de IBKR (via IBKR_FLEX_TOKEN /
 * IBKR_FLEX_QUERY_ID) y la importación en el research backend.
 */
export async function importFromIBKR(userId: string): Promise<IBKRImportResult> {
    const canonicalUserId = await resolveUserId(userId);
    const result = await researchRequest<IBKRImportResult>('/api/portfolio/import/ibkr', {
        method: 'POST',
    });
    invalidatePortfolioReads(canonicalUserId);
    return result;
}

/**
 * Importa un Flex XML crudo (por si el usuario lo descarga a mano).
 */
export async function importIBKRXml(userId: string, xml: string): Promise<IBKRImportResult> {
    const canonicalUserId = await resolveUserId(userId);
    const result = await researchRequest<IBKRImportResult>('/api/portfolio/import/ibkr/xml', {
        method: 'POST',
        body: jsonBody({ xml }),
    });
    invalidatePortfolioReads(canonicalUserId);
    return result;
}

/**
 * Importa un CSV de actividad de IBKR (symbol, quantity, price, date + action/fees/currency opcionales).
 */
export async function importIBKRCsv(userId: string, csv: string): Promise<IBKRImportResult> {
    const canonicalUserId = await resolveUserId(userId);
    const result = await researchRequest<IBKRImportResult>('/api/portfolio/import/ibkr/csv', {
        method: 'POST',
        body: jsonBody({ csv }),
    });
    invalidatePortfolioReads(canonicalUserId);
    return result;
}

export type PortfolioTearsheetMetrics = {
    status: string;
    n_observations: number;
    cumulative_return: number | null;
    sharpe: number | null;
    sortino: number | null;
    max_drawdown: number | null;
    win_rate: number | null;
    best_day: number | null;
    worst_day: number | null;
    periods_per_year: number;
};

export type PortfolioTearsheet = {
    status: string;
    metrics: PortfolioTearsheetMetrics | null;
    exposure: {
        snapshot_date: string;
        base_currency: string;
        total_value_base: number;
        equity_weight: number | null;
        cash_weight: number | null;
        n_positions: number;
        top_1_weight: number | null;
        top_5_weight: number | null;
    } | null;
};

/**
 * Tearsheet del portfolio (Sharpe, drawdown, win rate) desde los snapshots persistidos.
 * Degrada a null sin historial; nunca lanza por falta de datos.
 */
export async function getPortfolioTearsheet(userId: string): Promise<PortfolioTearsheet | null> {
    const canonicalUserId = await resolveUserId(userId);
    try {
        return await cachedFetch(
            `portfolio:${canonicalUserId}:tearsheet`,
            () => researchRequest<PortfolioTearsheet>('/api/portfolio/tearsheet', { fast: true }),
            15,
        );
    } catch (error) {
        console.error('Error getting portfolio tearsheet:', error);
        return null;
    }
}
