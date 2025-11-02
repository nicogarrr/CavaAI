'use server';

import { connectToDatabase } from '@/database/mongoose';
import { PortfolioModel, type Portfolio, type PortfolioPosition } from '@/database/models/portfolio.model';
import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';

export type PortfolioPositionWithData = PortfolioPosition & {
    currentPrice: number;
    invested: number;
    currentValue: number;
    profitLoss: number;
    profitLossPercent: number;
};

export type PortfolioPerformance = {
    portfolio: { id: string; name: string; description?: string };
    positions: PortfolioPositionWithData[];
    summary: {
        totalInvested: number;
        totalCurrentValue: number;
        totalProfitLoss: number;
        totalProfitLossPercent: number;
        positionCount: number;
    };
    status: {
        hasApiKey: boolean;
        isOnline: boolean;
        mockDataCount: number;
        totalPositions: number;
    };
};

async function fetchWithRetry(url: string, options: RequestInit, maxRetries = 2): Promise<Response> {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);
            
            const response = await fetch(url, {
                ...options,
                signal: controller.signal,
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                return response;
            }
            
            if (response.status === 429 && attempt < maxRetries - 1) {
                await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
                continue;
            }
            
            throw new Error(`HTTP error! status: ${response.status}`);
        } catch (error: any) {
            if (error.name === 'AbortError' && attempt < maxRetries - 1) {
                await new Promise(resolve => setTimeout(resolve, 1000));
                continue;
            }
            throw error;
        }
    }
    throw new Error('Max retries reached');
}

export async function getUserPortfolios(): Promise<Portfolio[]> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            return [];
        }

        const portfolios = await PortfolioModel.find({ userId: session.user.id }).sort({ createdAt: -1 });
        return JSON.parse(JSON.stringify(portfolios));
    } catch (error) {
        console.error('Error getting user portfolios:', error);
        return [];
    }
}

export async function getPortfolioById(portfolioId: string): Promise<Portfolio | null> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            return null;
        }

        const portfolio = await PortfolioModel.findOne({
            _id: portfolioId,
            userId: session.user.id,
        });

        if (!portfolio) {
            return null;
        }

        return JSON.parse(JSON.stringify(portfolio));
    } catch (error) {
        console.error('Error getting portfolio by id:', error);
        return null;
    }
}

export async function getPortfolioPerformance(portfolioId: string): Promise<PortfolioPerformance | null> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            return null;
        }

        const portfolio = await PortfolioModel.findOne({
            _id: portfolioId,
            userId: session.user.id,
        });

        if (!portfolio) {
            return null;
        }

        if (portfolio.positions.length === 0) {
            return {
                portfolio: { id: String((portfolio as any)._id), name: portfolio.name, description: portfolio.description },
                positions: [],
                summary: {
                    totalInvested: 0,
                    totalCurrentValue: 0,
                    totalProfitLoss: 0,
                    totalProfitLossPercent: 0,
                    positionCount: 0,
                },
                status: {
                    hasApiKey: !!process.env.FINNHUB_API_KEY,
                    isOnline: true,
                    mockDataCount: 0,
                    totalPositions: 0,
                },
            };
        }

        // Procesar posiciones secuencialmente con delay para evitar rate limiting
        const positions: (PortfolioPositionWithData & { isRealData?: boolean })[] = [];
        const apiKey = process.env.FINNHUB_API_KEY || process.env.NEXT_PUBLIC_FINNHUB_API_KEY;
        
        for (let i = 0; i < portfolio.positions.length; i++) {
            const pos = portfolio.positions[i];
            
            // Delay entre peticiones (excepto la primera)
            if (i > 0) {
                await new Promise(resolve => setTimeout(resolve, 500)); // 500ms entre peticiones
            }
            
            let result: PortfolioPositionWithData & { isRealData?: boolean };
            
            if (!apiKey) {
                // Sin API key, usar datos mock
                const mockPrice = pos.avgPurchasePrice * (0.95 + Math.random() * 0.1);
                const invested = pos.shares * pos.avgPurchasePrice;
                const currentValue = pos.shares * mockPrice;
                const profitLoss = currentValue - invested;
                const profitLossPercent = invested > 0 ? (profitLoss / invested) * 100 : 0;

                result = {
                    ...pos,
                    currentPrice: mockPrice,
                    invested,
                    currentValue,
                    profitLoss,
                    profitLossPercent,
                    isRealData: false,
                } as PortfolioPositionWithData & { isRealData: boolean };
            } else {
                // Intentar obtener datos reales
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 segundos timeout

                    // Intentar con Finnhub primero
                    let response = await fetch(
                        `https://finnhub.io/api/v1/quote?symbol=${pos.symbol}&token=${apiKey}`,
                        {
                            method: 'GET',
                            headers: { 'Accept': 'application/json' },
                            signal: controller.signal,
                            cache: 'no-store',
                        }
                    );

                    // Si Finnhub falla (403, 429), intentar con fallback
                    if (!response.ok || response.status === 403 || response.status === 429) {
                        // Intentar Alpha Vantage como fallback
                        const alphaKey = process.env.ALPHA_VANTAGE_API_KEY;
                        if (alphaKey) {
                            try {
                                response = await fetch(
                                    `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${pos.symbol}&apikey=${alphaKey}`,
                                    {
                                        method: 'GET',
                                        headers: { 'Accept': 'application/json' },
                                        signal: controller.signal,
                                        cache: 'no-store',
                                    }
                                );
                            } catch (e) {
                                // Si Alpha Vantage también falla, intentar Yahoo Finance (sin API key)
                                response = await fetch(
                                    `https://query1.finance.yahoo.com/v8/finance/chart/${pos.symbol}?interval=1d&range=1d`,
                                    {
                                        method: 'GET',
                                        headers: { 'Accept': 'application/json' },
                                        signal: controller.signal,
                                        cache: 'no-store',
                                    }
                                );
                            }
                        } else {
                            // Sin Alpha Vantage, usar Yahoo Finance directamente
                            response = await fetch(
                                `https://query1.finance.yahoo.com/v8/finance/chart/${pos.symbol}?interval=1d&range=1d`,
                                {
                                    method: 'GET',
                                    headers: { 'Accept': 'application/json' },
                                    signal: controller.signal,
                                    cache: 'no-store',
                                }
                            );
                        }
                    }

                    clearTimeout(timeoutId);

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const quoteData = await response.json();
                    let currentPrice: number;

                    // Parsear respuesta según la fuente
                    if (quoteData['Global Quote']) {
                        // Alpha Vantage
                        const quote = quoteData['Global Quote'];
                        currentPrice = parseFloat(quote['05. price'] || '0');
                    } else if (quoteData.chart?.result?.[0]?.meta) {
                        // Yahoo Finance
                        const meta = quoteData.chart.result[0].meta;
                        currentPrice = meta.regularMarketPrice || meta.previousClose || 0;
                    } else {
                        // Finnhub (formato original)
                        if (quoteData.error || !quoteData.c || quoteData.c === 0) {
                            throw new Error('Invalid price data');
                        }
                        currentPrice = quoteData.c;
                    }

                    if (!currentPrice || currentPrice === 0) {
                        throw new Error('Invalid price data');
                    }
                    const invested = pos.shares * pos.avgPurchasePrice;
                    const currentValue = pos.shares * currentPrice;
                    const profitLoss = currentValue - invested;
                    const profitLossPercent = invested > 0 ? (profitLoss / invested) * 100 : 0;

                    result = {
                        ...pos,
                        currentPrice,
                        invested,
                        currentValue,
                        profitLoss,
                        profitLossPercent,
                        isRealData: true, // Marcar como datos reales
                    } as PortfolioPositionWithData & { isRealData: boolean };
                } catch (fetchError) {
                    // Si falla, intentar retry una vez
                    try {
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        // Retry con fallback
                        let retryResponse: Response | null = null;
                        
                        // Intentar Alpha Vantage
                        const alphaKey = process.env.ALPHA_VANTAGE_API_KEY;
                        if (alphaKey) {
                            retryResponse = await fetch(
                                `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${pos.symbol}&apikey=${alphaKey}`,
                                {
                                    method: 'GET',
                                    headers: { 'Accept': 'application/json' },
                                    cache: 'no-store',
                                }
                            ).catch(() => null);
                        }
                        
                        // Si Alpha Vantage falla, intentar Yahoo Finance
                        if (!retryResponse || !retryResponse.ok) {
                            retryResponse = await fetch(
                                `https://query1.finance.yahoo.com/v8/finance/chart/${pos.symbol}?interval=1d&range=1d`,
                                {
                                    method: 'GET',
                                    headers: { 'Accept': 'application/json' },
                                    cache: 'no-store',
                                }
                            ).catch(() => null);
                        }
                        
                        if (retryResponse && retryResponse.ok) {
                            const retryData = await retryResponse.json();
                            let retryPrice: number = 0;
                            
                            // Parsear según fuente
                            if (retryData['Global Quote']) {
                                retryPrice = parseFloat(retryData['Global Quote']['05. price'] || '0');
                            } else if (retryData.chart?.result?.[0]?.meta) {
                                const meta = retryData.chart.result[0].meta;
                                retryPrice = meta.regularMarketPrice || meta.previousClose || 0;
                            } else if (retryData.c && retryData.c > 0) {
                                retryPrice = retryData.c;
                            }
                            
                            if (retryPrice > 0) {
                                const invested = pos.shares * pos.avgPurchasePrice;
                                const currentValue = pos.shares * retryPrice;
                                const profitLoss = currentValue - invested;
                                const profitLossPercent = invested > 0 ? (profitLoss / invested) * 100 : 0;
                                
                                result = {
                                    ...pos,
                                    currentPrice: retryPrice,
                                    invested,
                                    currentValue,
                                    profitLoss,
                                    profitLossPercent,
                                    isRealData: true,
                                } as PortfolioPositionWithData & { isRealData: boolean };
                            } else {
                                throw new Error('Invalid retry data');
                            }
                        } else {
                            throw new Error('Retry failed');
                        }
                    } catch {
                        // Si el retry falla, usar datos mock
                        const mockPrice = pos.avgPurchasePrice * (0.95 + Math.random() * 0.1);
                        const invested = pos.shares * pos.avgPurchasePrice;
                        const currentValue = pos.shares * mockPrice;
                        const profitLoss = currentValue - invested;
                        const profitLossPercent = invested > 0 ? (profitLoss / invested) * 100 : 0;

                        result = {
                            ...pos,
                            currentPrice: mockPrice,
                            invested,
                            currentValue,
                            profitLoss,
                            profitLossPercent,
                            isRealData: false,
                        } as PortfolioPositionWithData & { isRealData: boolean };
                    }
                }
            }
            
            positions.push(result);
        }

        const totalInvested = positions.reduce((s, p) => s + p.invested, 0);
        const totalCurrentValue = positions.reduce((s, p) => s + p.currentValue, 0);
        const totalProfitLoss = totalCurrentValue - totalInvested;
        const totalProfitLossPercent = totalInvested > 0 ? (totalProfitLoss / totalInvested) * 100 : 0;

        const summary = {
            totalInvested,
            totalCurrentValue,
            totalProfitLoss,
            totalProfitLossPercent,
            positionCount: positions.length,
        };

        // Contar cuántas posiciones están usando datos mock
        const mockDataCount = positions.filter(p => 
            !('isRealData' in p) || !(p as any).isRealData
        ).length;

        return {
            portfolio: { id: String((portfolio as any)._id), name: portfolio.name, description: portfolio.description },
            positions,
            summary,
            status: {
                hasApiKey: !!apiKey,
                isOnline: true,
                mockDataCount,
                totalPositions: positions.length,
            },
        } as PortfolioPerformance;
    } catch (error) {
        console.error('Error getting portfolio performance:', error);
        throw error;
    }
}

// Historial de cartera: suma ponderada de valores diarios por símbolo
export async function getPortfolioHistory(portfolioId: string, days = 365): Promise<{ t: number[]; v: number[] }> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            return { t: [], v: [] };
        }

        const portfolio = await PortfolioModel.findOne({
            _id: portfolioId,
            userId: session.user.id,
        });

        if (!portfolio || portfolio.positions.length === 0) {
            return { t: [], v: [] };
        }

        // Por ahora, retornar datos vacíos (se puede implementar con datos históricos reales)
        // TODO: Obtener datos históricos reales de Finnhub para cada símbolo
        return { t: [], v: [] };
    } catch (error) {
        console.error('Error getting portfolio history:', error);
        return { t: [], v: [] };
    }
}

export async function createPortfolio(name: string, description?: string): Promise<Portfolio> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            throw new Error('Usuario no autenticado');
        }

        const portfolio = new PortfolioModel({
            userId: session.user.id,
            name,
            description,
            positions: [],
        });

        await portfolio.save();
        return JSON.parse(JSON.stringify(portfolio));
    } catch (error) {
        console.error('Error creating portfolio:', error);
        throw error;
    }
}

export async function deletePortfolio(portfolioId: string): Promise<void> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            throw new Error('Usuario no autenticado');
        }

        await PortfolioModel.deleteOne({
            _id: portfolioId,
            userId: session.user.id,
        });
    } catch (error) {
        console.error('Error deleting portfolio:', error);
        throw error;
    }
}

export async function addPosition(
    portfolioId: string,
    position: Omit<PortfolioPosition, 'purchaseDate'>
): Promise<void> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            throw new Error('Usuario no autenticado');
        }

        const portfolio = await PortfolioModel.findOne({
            _id: portfolioId,
            userId: session.user.id,
        });

        if (!portfolio) {
            throw new Error('Cartera no encontrada');
        }

        portfolio.positions.push({
            ...position,
            purchaseDate: new Date(),
        });

        portfolio.updatedAt = new Date();
        await portfolio.save();
    } catch (error) {
        console.error('Error adding position:', error);
        throw error;
    }
}

export async function removePosition(portfolioId: string, positionIndex: number): Promise<void> {
    try {
        await connectToDatabase();
        const auth = await getAuth();
        const session = await auth.api.getSession({ headers: await headers() });
        
        if (!session?.user) {
            throw new Error('Usuario no autenticado');
        }

        const portfolio = await PortfolioModel.findOne({
            _id: portfolioId,
            userId: session.user.id,
        });

        if (!portfolio) {
            throw new Error('Cartera no encontrada');
        }

        if (positionIndex < 0 || positionIndex >= portfolio.positions.length) {
            throw new Error('Índice de posición inválido');
        }

        portfolio.positions.splice(positionIndex, 1);
        portfolio.updatedAt = new Date();
        await portfolio.save();
    } catch (error) {
        console.error('Error removing position:', error);
        throw error;
    }
}
