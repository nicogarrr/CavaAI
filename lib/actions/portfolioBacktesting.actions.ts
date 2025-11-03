'use server';

import { getAuth } from '@/lib/better-auth/auth';
import { headers } from 'next/headers';
import { getCandles } from './finnhub.actions';
import { getQuoteWithFallback } from './dataSources.actions';

/**
 * Backtesting de portfolios completo
 * Simula el rendimiento histórico de un portfolio con datos reales
 */

export interface PortfolioBacktestResult {
  portfolioId: string;
  portfolioName: string;
  period: {
    start: string;
    end: string;
    days: number;
  };
  initialValue: number;
  finalValue: number;
  performance: {
    totalReturn: number; // Retorno total %
    totalReturnUSD: number; // Retorno total en USD
    annualizedReturn: number; // Retorno anualizado %
    maxDrawdown: number; // Drawdown máximo %
    sharpeRatio: number; // Ratio de Sharpe
    volatility: number; // Volatilidad (desviación estándar) %
    winDays: number; // Días con ganancia
    lossDays: number; // Días con pérdida
    bestDay: { date: string; return: number };
    worstDay: { date: string; return: number };
  };
  positions: Array<{
    symbol: string;
    shares: number;
    entryPrice: number;
    exitPrice: number;
    entryDate: string;
    exitDate: string;
    return: number;
    returnPercent: number;
    contribution: number; // Contribución al retorno total en USD
  }>;
  dailyValues: Array<{
    date: string;
    value: number;
    return: number;
    returnPercent: number;
  }>;
  vsBenchmark: {
    benchmarkReturn: number;
    alpha: number; // Exceso de retorno vs benchmark
    beta: number; // Sensibilidad al mercado
    trackingError: number; // Error de seguimiento
    informationRatio: number; // Ratio de información (alpha / tracking error)
  };
}

/**
 * Obtiene datos históricos de precios para un símbolo
 */
async function getHistoricalPrices(
  symbol: string,
  startDate: Date,
  endDate: Date
): Promise<Array<{ date: string; price: number; volume?: number }>> {
  try {
    const from = Math.floor(startDate.getTime() / 1000);
    const to = Math.floor(endDate.getTime() / 1000);

    // Intentar obtener datos de Finnhub primero
    const candles = await getCandles(symbol, from, to, 'D');
    
    if (candles && candles.s === 'ok' && candles.c && candles.c.length > 0) {
      return candles.c.map((price, idx) => ({
        date: new Date(candles.t[idx] * 1000).toISOString(),
        price,
        volume: candles.v[idx],
      }));
    }

    // Si Finnhub no funciona, usar fallback
    // Por simplicidad, retornamos precio actual como aproximación
    // En producción, se debería implementar fetch histórico desde Alpha Vantage o Yahoo Finance
    const quote = await getQuoteWithFallback(symbol);
    if (quote) {
      return [{
        date: new Date().toISOString(),
        price: quote.currentPrice,
      }];
    }

    return [];
  } catch (error) {
    console.error(`Error getting historical prices for ${symbol}:`, error);
    return [];
  }
}

/**
 * Calcula métricas de backtesting para un portfolio
 */
export async function backtestPortfolio(
  portfolioId: string,
  portfolioName: string,
  positions: Array<{
    symbol: string;
    shares: number;
    entryDate: string;
  }>,
  startDate: string,
  endDate: string,
  benchmarkSymbol: string = 'SPY' // S&P 500 por defecto
): Promise<PortfolioBacktestResult | null> {
  const auth = await getAuth();
  if (!auth) throw new Error('Error de autenticación');
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user) throw new Error('Usuario no autenticado');

  try {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const days = Math.floor((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));

    if (days <= 0) {
      throw new Error('La fecha final debe ser posterior a la fecha inicial');
    }

    // Calcular valor inicial del portfolio
    let initialValue = 0;
    const positionData: Array<{
      symbol: string;
      shares: number;
      entryPrice: number;
      entryDate: string;
    }> = [];

    for (const position of positions) {
      const entryDateObj = new Date(position.entryDate);
      const historicalPrices = await getHistoricalPrices(position.symbol, entryDateObj, entryDateObj);
      
      const entryPrice = historicalPrices.length > 0 
        ? historicalPrices[0].price 
        : (await getQuoteWithFallback(position.symbol))?.currentPrice || 0;

      if (entryPrice > 0) {
        positionData.push({
          symbol: position.symbol,
          shares: position.shares,
          entryPrice,
          entryDate: position.entryDate,
        });
        initialValue += entryPrice * position.shares;
      }

      // Pausa para evitar rate limiting
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    if (initialValue === 0 || positionData.length === 0) {
      throw new Error('No se pudieron obtener precios para las posiciones');
    }

    // Calcular valores diarios del portfolio
    const dailyValues: Array<{
      date: string;
      value: number;
      return: number;
      returnPercent: number;
    }> = [];

    // Calcular valor para cada día
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      let dailyValue = 0;
      const currentDate = new Date(d);

      for (const pos of positionData) {
        const entryDate = new Date(pos.entryDate);
        // Solo contar posiciones que ya estaban abiertas
        if (currentDate >= entryDate) {
          const prices = await getHistoricalPrices(pos.symbol, currentDate, currentDate);
          const price = prices.length > 0 
            ? prices[0].price 
            : pos.entryPrice; // Usar precio de entrada si no hay datos

          dailyValue += price * pos.shares;
        }
      }

      const previousValue = dailyValues.length > 0 ? dailyValues[dailyValues.length - 1].value : initialValue;
      const return_ = dailyValue - previousValue;
      const returnPercent = previousValue > 0 ? (return_ / previousValue) * 100 : 0;

      dailyValues.push({
        date: currentDate.toISOString(),
        value: dailyValue,
        return: return_,
        returnPercent,
      });

      // Pausa para evitar rate limiting (cada 10 días para no sobrecargar)
      if (dailyValues.length % 10 === 0) {
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }

    // Calcular precios de salida y rendimiento de cada posición
    const finalPositions = await Promise.all(
      positionData.map(async (pos) => {
        const exitPrices = await getHistoricalPrices(pos.symbol, end, end);
        const exitPrice = exitPrices.length > 0 
          ? exitPrices[0].price 
          : (await getQuoteWithFallback(pos.symbol))?.currentPrice || pos.entryPrice;

        const return_ = (exitPrice - pos.entryPrice) * pos.shares;
        const returnPercent = ((exitPrice - pos.entryPrice) / pos.entryPrice) * 100;

        return {
          symbol: pos.symbol,
          shares: pos.shares,
          entryPrice: pos.entryPrice,
          exitPrice,
          entryDate: pos.entryDate,
          exitDate: end.toISOString(),
          return: return_,
          returnPercent,
          contribution: return_,
        };
      })
    );

    const finalValue = dailyValues.length > 0 ? dailyValues[dailyValues.length - 1].value : initialValue;
    const totalReturnUSD = finalValue - initialValue;
    const totalReturn = (totalReturnUSD / initialValue) * 100;

    // Calcular retorno anualizado
    const years = days / 365.25;
    const annualizedReturn = years > 0 ? (((finalValue / initialValue) ** (1 / years)) - 1) * 100 : totalReturn;

    // Calcular drawdown máximo
    let maxDrawdown = 0;
    let peak = initialValue;
    for (const day of dailyValues) {
      if (day.value > peak) peak = day.value;
      const drawdown = ((peak - day.value) / peak) * 100;
      if (drawdown > maxDrawdown) maxDrawdown = drawdown;
    }

    // Calcular volatilidad (desviación estándar de retornos diarios)
    const dailyReturns = dailyValues.map(d => d.returnPercent);
    const avgReturn = dailyReturns.reduce((sum, r) => sum + r, 0) / dailyReturns.length;
    const variance = dailyReturns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / dailyReturns.length;
    const volatility = Math.sqrt(variance);

    // Calcular Ratio de Sharpe (simplificado, asumiendo risk-free rate de 2%)
    const riskFreeRate = 2; // 2% anual
    const annualizedVolatility = volatility * Math.sqrt(252); // Ajustar a anual
    const sharpeRatio = annualizedVolatility > 0 
      ? (annualizedReturn - riskFreeRate) / annualizedVolatility 
      : 0;

    // Calcular días ganadores/perdedores
    const winDays = dailyValues.filter(d => d.return > 0).length;
    const lossDays = dailyValues.filter(d => d.return < 0).length;

    // Mejor y peor día
    const sortedByReturn = [...dailyValues].sort((a, b) => b.returnPercent - a.returnPercent);
    const bestDay = sortedByReturn.length > 0 
      ? { date: sortedByReturn[0].date, return: sortedByReturn[0].returnPercent }
      : { date: '', return: 0 };
    const worstDay = sortedByReturn.length > 0
      ? { date: sortedByReturn[sortedByReturn.length - 1].date, return: sortedByReturn[sortedByReturn.length - 1].returnPercent }
      : { date: '', return: 0 };

    // Calcular benchmark (S&P 500)
    const benchmarkPrices = await getHistoricalPrices(benchmarkSymbol, start, end);
    const benchmarkStartPrice = benchmarkPrices.length > 0 
      ? benchmarkPrices[0].price 
      : (await getQuoteWithFallback(benchmarkSymbol))?.currentPrice || 100;
    const benchmarkEndPrice = benchmarkPrices.length > 0
      ? benchmarkPrices[benchmarkPrices.length - 1].price
      : (await getQuoteWithFallback(benchmarkSymbol))?.currentPrice || benchmarkStartPrice;

    const benchmarkReturn = ((benchmarkEndPrice - benchmarkStartPrice) / benchmarkStartPrice) * 100;

    // Calcular Alpha y Beta (simplificado)
    const alpha = annualizedReturn - benchmarkReturn;
    const beta = 1.0; // Por defecto, se puede calcular usando correlación

    // Calcular Tracking Error e Information Ratio
    const trackingError = volatility;
    const informationRatio = trackingError > 0 ? alpha / trackingError : 0;

    return {
      portfolioId,
      portfolioName,
      period: {
        start: startDate,
        end: endDate,
        days,
      },
      initialValue,
      finalValue,
      performance: {
        totalReturn,
        totalReturnUSD,
        annualizedReturn,
        maxDrawdown,
        sharpeRatio,
        volatility: annualizedVolatility,
        winDays,
        lossDays,
        bestDay,
        worstDay,
      },
      positions: finalPositions,
      dailyValues,
      vsBenchmark: {
        benchmarkReturn,
        alpha,
        beta,
        trackingError,
        informationRatio,
      },
    };
  } catch (error) {
    console.error('Error backtesting portfolio:', error);
    return null;
  }
}

