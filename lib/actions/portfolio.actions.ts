'use server';

import { connectToDatabase } from '@/database/mongoose';
import { PortfolioTransaction } from '@/database/models/portfolio.model';

const FINNHUB_BASE_URL = 'https://finnhub.io/api/v1';
const FINNHUB_API_KEY = process.env.FINNHUB_API_KEY ?? process.env.NEXT_PUBLIC_FINNHUB_API_KEY;

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

export async function addTransaction(
    userId: string,
    symbol: string,
    type: 'buy' | 'sell',
    quantity: number,
    price: number,
    date: Date,
    notes?: string
): Promise<{ success: boolean; error?: string }> {
    try {
        await connectToDatabase();

        await PortfolioTransaction.create({
            userId,
            symbol: symbol.toUpperCase(),
            type,
            quantity,
            price,
            date,
            notes,
        });

        return { success: true };
    } catch (error) {
        console.error('Error adding transaction:', error);
        return { success: false, error: 'Failed to add transaction' };
    }
}

export async function getPortfolioTransactions(userId: string) {
    try {
        await connectToDatabase();

        const transactions = await PortfolioTransaction.find({ userId })
            .sort({ date: -1 })
            .lean();

        return transactions.map(t => ({
            ...t,
            _id: String(t._id),
            date: t.date.toISOString(),
            createdAt: t.createdAt.toISOString(),
            updatedAt: t.updatedAt.toISOString(),
        }));
    } catch (error) {
        console.error('Error getting transactions:', error);
        return [];
    }
}

export async function getPortfolioSummary(userId: string): Promise<PortfolioSummary> {
    try {
        await connectToDatabase();

        const transactions = await PortfolioTransaction.find({ userId }).lean();

        // Calculate holdings
        const holdingsMap = new Map<string, { quantity: number; totalCost: number }>();

        transactions.forEach(tx => {
            const symbol = tx.symbol;
            const existing = holdingsMap.get(symbol) || { quantity: 0, totalCost: 0 };

            if (tx.type === 'buy') {
                existing.quantity += tx.quantity;
                existing.totalCost += tx.quantity * tx.price;
            } else {
                // Sell: reduce quantity proportionally and cost
                const avgCost = existing.quantity > 0 ? existing.totalCost / existing.quantity : 0;
                existing.quantity -= tx.quantity;
                existing.totalCost -= tx.quantity * avgCost;
            }

            holdingsMap.set(symbol, existing);
        });

        // Remove zero or negative holdings
        for (const [symbol, data] of holdingsMap.entries()) {
            if (data.quantity <= 0) {
                holdingsMap.delete(symbol);
            }
        }

        // Fetch current prices
        const holdings: PortfolioHolding[] = [];
        let totalValue = 0;
        let totalCost = 0;

        for (const [symbol, data] of holdingsMap.entries()) {
            const quote = await getQuote(symbol);
            const currentPrice = quote?.c || 0;
            const value = data.quantity * currentPrice;
            const avgPrice = data.quantity > 0 ? data.totalCost / data.quantity : 0;
            const gain = value - data.totalCost;
            const gainPercent = data.totalCost > 0 ? (gain / data.totalCost) * 100 : 0;

            holdings.push({
                symbol,
                quantity: data.quantity,
                avgPrice,
                currentPrice,
                value,
                cost: data.totalCost,
                gain,
                gainPercent,
            });

            totalValue += value;
            totalCost += data.totalCost;
        }

        const totalGain = totalValue - totalCost;
        const totalGainPercent = totalCost > 0 ? (totalGain / totalCost) * 100 : 0;

        return {
            totalValue,
            totalCost,
            totalGain,
            totalGainPercent,
            holdings: holdings.sort((a, b) => b.value - a.value),
        };
    } catch (error) {
        console.error('Error getting portfolio summary:', error);
        return {
            totalValue: 0,
            totalCost: 0,
            totalGain: 0,
            totalGainPercent: 0,
            holdings: [],
        };
    }
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
    try {
        await connectToDatabase();

        const result = await PortfolioTransaction.updateOne(
            { _id: transactionId, userId },
            {
                symbol: symbol.toUpperCase(),
                type,
                quantity,
                price,
                date,
                notes,
            }
        );

        if (result.matchedCount === 0) {
            return { success: false, error: 'Transaction not found' };
        }

        return { success: true };
    } catch (error) {
        console.error('Error updating transaction:', error);
        return { success: false, error: 'Failed to update transaction' };
    }
}

export async function deleteTransaction(userId: string, transactionId: string): Promise<{ success: boolean; error?: string }> {
    try {
        await connectToDatabase();

        const result = await PortfolioTransaction.deleteOne({
            _id: transactionId,
            userId
        });

        if (result.deletedCount === 0) {
            return { success: false, error: 'Transaction not found' };
        }

        return { success: true };
    } catch (error) {
        console.error('Error deleting transaction:', error);
        return { success: false, error: 'Failed to delete transaction' };
    }
}

// Eliminar todas las transacciones de un símbolo (eliminar posición)
export async function deleteHolding(userId: string, symbol: string): Promise<{ success: boolean; error?: string }> {
    try {
        await connectToDatabase();

        const result = await PortfolioTransaction.deleteMany({
            symbol: symbol.toUpperCase(),
            userId
        });

        if (result.deletedCount === 0) {
            return { success: false, error: 'Holding not found' };
        }

        return { success: true };
    } catch (error) {
        console.error('Error deleting holding:', error);
        return { success: false, error: 'Failed to delete holding' };
    }
}

// ============================================
// Funciones adicionales para Portfolio
// ============================================

// Obtener puntuaciones agregadas del portfolio
export async function getPortfolioScores(userId: string) {
    try {
        const summary = await getPortfolioSummary(userId);
        const holdingsCount = summary.holdings.length;

        if (holdingsCount === 0) {
            return {
                quality: 0,
                growth: 0,
                value: 0,
                dividend: 0,
                cagr3y: 0
            };
        }

        // Puntuaciones basadas en performance del portfolio
        const avgGainPercent = summary.totalGainPercent;

        return {
            quality: Math.min(100, Math.max(0, 70 + avgGainPercent * 0.5)),
            growth: Math.min(100, Math.max(0, 60 + avgGainPercent * 0.8)),
            value: Math.min(100, Math.max(0, 55 + avgGainPercent * 0.4)),
            dividend: Math.min(100, Math.max(0, 20 + holdingsCount * 5)),
            cagr3y: Math.min(50, Math.max(-20, avgGainPercent * 0.3))
        };
    } catch (error) {
        console.error('Error getting portfolio scores:', error);
        return {
            quality: 0,
            growth: 0,
            value: 0,
            dividend: 0,
            cagr3y: 0
        };
    }
}

// Añadir posición rápida desde buscador
export async function quickAddPosition(
    userId: string,
    symbol: string,
    shares: number,
    price: number
): Promise<{ success: boolean; error?: string }> {
    return addTransaction(userId, symbol, 'buy', shares, price, new Date());
}

// Obtener holdings con peso de portfolio
export async function getPortfolioWithWeights(userId: string) {
    const summary = await getPortfolioSummary(userId);

    return summary.holdings.map(h => ({
        ...h,
        weight: summary.totalValue > 0 ? (h.value / summary.totalValue) * 100 : 0
    }));
}

// Actualizar precios de holdings existentes (para refresco cliente)
export async function refreshPortfolioHoldings(holdings: PortfolioHolding[]): Promise<PortfolioHolding[]> {
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
