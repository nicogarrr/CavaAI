'use server';

import { requireAuthenticatedUser } from '@/lib/auth/require-user';
import { researchIdentityHeaders } from '@/lib/auth/research-identity';
import { jsonBody, researchRequest } from '@/lib/research/client';
import { AuthorizationError, ValidationError } from '@/lib/types/errors';

const FINNHUB_BASE_URL = 'https://finnhub.io/api/v1';
const FINNHUB_API_KEY = process.env.FINNHUB_API_KEY ?? process.env.NEXT_PUBLIC_FINNHUB_API_KEY;

async function resolveUserId(requestedUserId?: string): Promise<string> {
    const user = await requireAuthenticatedUser();
    if (requestedUserId && requestedUserId !== user.id) {
        throw new AuthorizationError('Cannot access another user portfolio');
    }
    return user.id;
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
    await resolveUserId(userId);
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
    return { success: true };
}

export async function getPortfolioTransactions(userId: string) {
    await resolveUserId(userId);
    const transactions = await researchRequest<ResearchPortfolioTransaction[]>('/api/portfolio/transactions');
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
    await resolveUserId(userId);
    const [positions, backendSummary] = await Promise.all([
        researchRequest<ResearchPortfolioPosition[]>('/api/portfolio/positions'),
        researchRequest<ResearchPortfolioSummaryResponse>('/api/portfolio/summary'),
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
    await resolveUserId(userId);
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
    return { success: true };
}

export async function deleteTransaction(userId: string, transactionId: string): Promise<{ success: boolean; error?: string }> {
    await resolveUserId(userId);
    await researchRequest<void>(`/api/portfolio/transactions/${encodeURIComponent(transactionId)}`, {
        method: 'DELETE',
    });
    return { success: true };
}

// Eliminar todas las transacciones de un símbolo (eliminar posición)
export async function deleteHolding(userId: string, symbol: string): Promise<{ success: boolean; error?: string }> {
    await resolveUserId(userId);
    await researchRequest<void>(`/api/portfolio/holdings/${encodeURIComponent(symbol.toUpperCase())}`, {
        method: 'DELETE',
    });
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

const BACKEND_URL = process.env.FMP_BACKEND_URL ?? 'http://localhost:8000';

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
    await resolveUserId(userId);
    const empty = { quality: 0, growth: 0, value: 0, dividend: 0, cagr3y: 0 };

    try {
        const summary = await getPortfolioSummary(userId);
        if (summary.holdings.length === 0) return empty;

        const symbols = summary.holdings.map(h => h.symbol);

        const totalValue = summary.totalValue;
        const weights = totalValue > 0
            ? summary.holdings.map(h => h.value / totalValue)
            : undefined;

        const transactions = await getPortfolioTransactions(userId);
        const identityHeaders = await researchIdentityHeaders();

        let history: PortfolioPerformanceHistory | undefined;
        try {
            const historyRes = await fetch(`${BACKEND_URL}/analytics/portfolio/returns`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...identityHeaders },
                body: JSON.stringify({
                    symbols,
                    transactions: transactions.map(tx => ({
                        symbol: tx.symbol,
                        type: tx.type,
                        quantity: tx.quantity,
                        price: tx.price,
                        date: tx.date,
                    })),
                    period: '2y',
                }),
                next: { revalidate: 300 },
            });

            history = historyRes.ok ? await historyRes.json() : undefined;
        } catch (error) {
            console.error('Portfolio returns endpoint error:', error);
        }

        const res = await fetch(`${BACKEND_URL}/analytics/portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...identityHeaders },
            body: JSON.stringify({ symbols, weights, period: '2y' }),
            next: { revalidate: 300 },
        });

        if (!res.ok) {
            console.error('Portfolio analytics endpoint error:', res.status);
            return empty;
        }

        const data: PortfolioAnalyticsResult = await res.json();

        return {
            quality: data.score_quality ?? 0,
            growth: data.score_growth ?? 0,
            value: data.score_value ?? 0,
            // Dividend score stays 0 until we have a real dividend-yield engine
            dividend: 0,
            cagr3y: history?.twr != null
                ? Math.round(history.twr * 10000) / 100
                : data.score_cagr3y != null ? Math.round(data.score_cagr3y * 100) / 100 : 0,
            analytics: data,
            history,
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
