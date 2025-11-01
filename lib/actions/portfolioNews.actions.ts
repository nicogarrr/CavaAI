'use server';

import { getPortfolioById } from './portfolio.actions';
import { getCompanyNews } from './finnhub.actions';

export async function getPortfolioNews(portfolioId: string, limit: number = 20): Promise<Array<{
    article: any;
    symbol: string;
    company: string;
}>> {
    try {
        // Usar getPortfolioById para obtener solo los datos básicos del portfolio (sin cálculos pesados)
        const portfolio = await getPortfolioById(portfolioId);
        if (!portfolio || !portfolio.positions || portfolio.positions.length === 0) {
            return [];
        }

        // Obtener símbolos únicos del portfolio
        const uniqueSymbols = [...new Set(portfolio.positions.map(p => p.symbol))];

        // Obtener noticias para cada símbolo
        const newsPromises = uniqueSymbols.map(async (symbol) => {
            try {
                const articles = await getCompanyNews(symbol, Math.ceil(limit / uniqueSymbols.length));
                return articles.map(article => ({
                    article,
                    symbol,
                    company: portfolio.positions.find(p => p.symbol === symbol)?.company || symbol,
                }));
            } catch (error) {
                console.error(`Error fetching news for ${symbol}:`, error);
                return [];
            }
        });

        const newsResults = await Promise.all(newsPromises);
        
        // Flatten y ordenar por fecha
        const allNews = newsResults.flat().sort((a, b) => {
            const dateA = a.article.datetime || 0;
            const dateB = b.article.datetime || 0;
            return dateB - dateA; // Más recientes primero
        });

        return allNews.slice(0, limit);
    } catch (error) {
        console.error('Error getting portfolio news:', error);
        return [];
    }
}

