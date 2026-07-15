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
};

export type PortfolioSummary = {
    totalValue: number;
    totalCost: number;
    totalGain: number;
    totalGainPercent: number;
    holdings: PortfolioHolding[];
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
};

export async function addTransaction(
    userId: string,
    symbol: string,
    type: 'buy' | 'sell',
    quantity: number,
    price: number,
    date: Date,
    notes?: string
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
            currency: 'USD',
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
        createdAt: transaction.created_at,
        updatedAt: transaction.updated_at,
    }));
}

export async function getPortfolioSummary(userId: string): Promise<PortfolioSummary> {
    await resolveUserId(userId);
    const positions = await researchRequest<ResearchPortfolioPosition[]>('/api/portfolio/positions');
    const holdings = await Promise.all(positions.map(async (position): Promise<PortfolioHolding> => {
        const quote = await getQuote(position.ticker);
        const currentPrice = quote?.c || position.market_price;
        const cost = position.quantity * position.average_cost;
        const value = position.quantity * currentPrice;
        const gain = value - cost;
        return {
            symbol: position.ticker,
            quantity: position.quantity,
            avgPrice: position.average_cost,
            currentPrice,
            value,
            cost,
            gain,
            gainPercent: cost > 0 ? (gain / cost) * 100 : 0,
        };
    }));
    const totalValue = holdings.reduce((sum, holding) => sum + holding.value, 0);
    const totalCost = holdings.reduce((sum, holding) => sum + holding.cost, 0);
    const totalGain = totalValue - totalCost;
    return {
        totalValue,
        totalCost,
        totalGain,
        totalGainPercent: totalCost > 0 ? (totalGain / totalCost) * 100 : 0,
        holdings: holdings.sort((a, b) => b.value - a.value),
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
    notes?: string
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
                currency: 'USD',
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
    await requireAuthenticatedUser();
    try {
        const updatedHoldings = await Promise.all(holdings.map(async (h) => {
            const quote = await getQuote(h.symbol);
            const currentPrice = quote?.c || h.currentPrice; // Use old price if fetch fails

            const value = h.quantity * currentPrice;
            const gain = value - h.cost; // h.cost is totalCost
            const gainPercent = h.cost > 0 ? (gain / h.cost) * 100 : 0;

            return {
                ...h,
                currentPrice,
                value,
                gain,
                gainPercent
            };
        }));

        return updatedHoldings;
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

// ============================================
// Sincronización Inteligente de Cartera (Diffing)
// ============================================

type ExtractedPosition = {
    symbol: string;
    currentPriceUSD: number;
    changePercent: number;
    currency: 'EUR' | 'USD';
    shares?: number;
    marketValue?: number;
};

export async function syncPortfolioHoldings(
    userId: string,
    extractedPositions: ExtractedPosition[]
): Promise<{ success: boolean; actions: string[]; error?: string }> {
    await resolveUserId(userId);
    try {
        const actions: string[] = [];

        // Estrategia: "Snapshot Replacement" (Reemplazo por Captura)
        // Para cada símbolo detectado en la captura, eliminamos la posición antigua y creamos una nueva
        // que refleje EXACTAMENTE la captura. Esto evita duplicados y drift.

        for (const pos of extractedPositions) {
            const symbol = pos.symbol.toUpperCase();

            // 1. Convertir todo a USD si es necesario (el extractor ya hace parte, pero aseguramos)
            const isEur = pos.currency === 'EUR';
            const rate = isEur ? 1.05 : 1.0; // Rate fijo por ahora, idealmente dinámico

            // Precio Actual en USD
            let currentPriceUSD = pos.currentPriceUSD;
            if (!currentPriceUSD || currentPriceUSD === 0) {
                const quote = await getQuote(symbol);
                currentPriceUSD = quote?.c || 0;
            }

            // Valor de Mercado en USD
            // Si pos.marketValue viene en EUR, convertir.
            let marketValueUSD = pos.marketValue || 0; // Default to 0 if undefined
            if (isEur) {
                marketValueUSD = (pos.marketValue || 0) * rate;
            }

            // 2. Calcular Acciones (Shares)
            // Si viene en la imagen, genial. Si no, MarketValue / Precio
            let shares = pos.shares || 0;
            if (shares === 0 && currentPriceUSD > 0 && marketValueUSD > 0) {
                shares = marketValueUSD / currentPriceUSD;
            }
            // Redondear a 4 decimales
            shares = Math.round(shares * 10000) / 10000;

            if (shares <= 0) continue; // No podemos importar 0 acciones

            // 3. Calcular Precio de Compra Original (Cost Basis)
            // Usamos el ChangePercent para ingeniería inversa:
            // CurrentValue = CostBasis * (1 + Change%)
            // CostBasis = CurrentValue / (1 + Change%)
            // BuyPrice = CostBasis / Shares

            // ChangePercent viene como -18.25 para -18.25%
            const changeFactor = 1 + (pos.changePercent / 100);

            let totalCostUSD = 0;
            if (changeFactor !== 0) {
                totalCostUSD = marketValueUSD / changeFactor;
            } else {
                totalCostUSD = marketValueUSD; // Fallback si error math
            }

            const buyPriceUSD = totalCostUSD / shares;

            // 4. ELIMINAR posición existente para este símbolo (Wipe)
            await deleteHolding(userId, symbol);

            // 5. CREAR nueva posición (Recreate)
            await addTransaction(
                userId,
                symbol,
                'buy',
                shares,
                buyPriceUSD,
                new Date(), // Fecha hoy
                `Importado desde captura de pantalla (Snapshot). Rentabilidad preservada: ${pos.changePercent}%`
            );

            actions.push(`SYNC: ${symbol} -> ${shares} acciones @ $${buyPriceUSD.toFixed(2)} (Calc)`);
        }

        return { success: true, actions };
    } catch (error) {
        console.error('Error syncing portfolio holdings:', error);
        return { success: false, actions: [], error: 'Failed to sync holdings' };
    }
}
