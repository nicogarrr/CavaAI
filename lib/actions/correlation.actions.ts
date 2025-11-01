'use server';

import { cache } from 'react';
import { getCandles } from './finnhub.actions';

export type CorrelationData = {
  symbol1: string;
  symbol2: string;
  correlation: number;
  period: string;
  significance: 'high' | 'medium' | 'low';
};

export type DiversificationAnalysis = {
  sectorAllocation: Array<{
    sector: string;
    percentage: number;
    count: number;
  }>;
  regionAllocation: Array<{
    region: string;
    percentage: number;
    count: number;
  }>;
  concentrationRisk: {
    herfindahlIndex: number;
    maxSingleHolding: number;
    top5Concentration: number;
    riskLevel: 'low' | 'medium' | 'high';
  };
  correlationInsights: Array<{
    type: 'high_correlation' | 'low_correlation' | 'negative_correlation';
    pairs: Array<{ symbol1: string; symbol2: string; correlation: number }>;
    recommendation: string;
  }>;
};

// Calcular correlación entre dos series de precios
function calculateCorrelation(prices1: number[], prices2: number[]): number {
  if (prices1.length !== prices2.length || prices1.length < 2) {
    return 0;
  }

  // Calcular retornos diarios
  const returns1: number[] = [];
  const returns2: number[] = [];

  for (let i = 1; i < prices1.length; i++) {
    returns1.push((prices1[i] - prices1[i-1]) / prices1[i-1]);
    returns2.push((prices2[i] - prices2[i-1]) / prices2[i-1]);
  }

  if (returns1.length < 2) return 0;

  // Calcular medias
  const mean1 = returns1.reduce((sum, val) => sum + val, 0) / returns1.length;
  const mean2 = returns2.reduce((sum, val) => sum + val, 0) / returns2.length;

  // Calcular covarianza y varianzas
  let covariance = 0;
  let variance1 = 0;
  let variance2 = 0;

  for (let i = 0; i < returns1.length; i++) {
    const diff1 = returns1[i] - mean1;
    const diff2 = returns2[i] - mean2;
    
    covariance += diff1 * diff2;
    variance1 += diff1 * diff1;
    variance2 += diff2 * diff2;
  }

  covariance /= returns1.length;
  variance1 /= returns1.length;
  variance2 /= returns2.length;

  // Calcular correlación
  const correlation = variance1 === 0 || variance2 === 0 
    ? 0 
    : covariance / Math.sqrt(variance1 * variance2);

  return Math.max(-1, Math.min(1, correlation)); // Asegurar rango [-1, 1]
}

// Obtener datos históricos para múltiples símbolos
async function getHistoricalData(symbols: string[], days: number = 252) {
  const endTime = Math.floor(Date.now() / 1000);
  const startTime = endTime - (days * 24 * 60 * 60);

  const dataPromises = symbols.map(async (symbol) => {
    try {
      const candles = await getCandles(symbol, startTime, endTime, 'D', 3600);
      if (candles.s === 'ok' && candles.c.length > 0) {
        return {
          symbol,
          prices: candles.c,
          success: true
        };
      }
      return { symbol, prices: [], success: false };
    } catch (error) {
      console.error(`Error fetching data for ${symbol}:`, error);
      return { symbol, prices: [], success: false };
    }
  });

  const results = await Promise.all(dataPromises);
  return results.filter(result => result.success);
}

// Calcular matriz de correlaciones
export const calculateCorrelationMatrix = cache(async (
  symbols: string[], 
  period: number = 252
): Promise<CorrelationData[]> => {
  const historicalData = await getHistoricalData(symbols, period);
  const correlations: CorrelationData[] = [];

  for (let i = 0; i < historicalData.length; i++) {
    for (let j = i + 1; j < historicalData.length; j++) {
      const data1 = historicalData[i];
      const data2 = historicalData[j];
      
      const correlation = calculateCorrelation(data1.prices, data2.prices);
      
      let significance: 'high' | 'medium' | 'low' = 'low';
      if (Math.abs(correlation) > 0.7) significance = 'high';
      else if (Math.abs(correlation) > 0.4) significance = 'medium';

      correlations.push({
        symbol1: data1.symbol,
        symbol2: data2.symbol,
        correlation,
        period: `${period} days`,
        significance
      });
    }
  }

  return correlations;
});

// Análisis de diversificación del portfolio
export const analyzeDiversification = cache(async (
  positions: Array<{
    symbol: string;
    percentage: number;
    sector?: string;
    region?: string;
  }>
): Promise<DiversificationAnalysis> => {
  // Análisis por sectores
  const sectorMap = new Map<string, { percentage: number; count: number }>();
  const regionMap = new Map<string, { percentage: number; count: number }>();

  positions.forEach(position => {
    const sector = position.sector || 'Unknown';
    const region = position.region || 'Unknown';
    
    // Sector
    const sectorData = sectorMap.get(sector) || { percentage: 0, count: 0 };
    sectorData.percentage += position.percentage;
    sectorData.count += 1;
    sectorMap.set(sector, sectorData);

    // Región
    const regionData = regionMap.get(region) || { percentage: 0, count: 0 };
    regionData.percentage += position.percentage;
    regionData.count += 1;
    regionMap.set(region, regionData);
  });

  const sectorAllocation = Array.from(sectorMap.entries()).map(([sector, data]) => ({
    sector,
    percentage: data.percentage,
    count: data.count
  })).sort((a, b) => b.percentage - a.percentage);

  const regionAllocation = Array.from(regionMap.entries()).map(([region, data]) => ({
    region,
    percentage: data.percentage,
    count: data.count
  })).sort((a, b) => b.percentage - a.percentage);

  // Calcular índices de concentración
  const percentages = positions.map(p => p.percentage);
  const herfindahlIndex = percentages.reduce((sum, p) => sum + p * p, 0);
  const maxSingleHolding = Math.max(...percentages);
  const top5Concentration = percentages
    .sort((a, b) => b - a)
    .slice(0, 5)
    .reduce((sum, p) => sum + p, 0);

  let riskLevel: 'low' | 'medium' | 'high' = 'low';
  if (herfindahlIndex > 0.25 || maxSingleHolding > 0.3 || top5Concentration > 0.7) {
    riskLevel = 'high';
  } else if (herfindahlIndex > 0.15 || maxSingleHolding > 0.2 || top5Concentration > 0.5) {
    riskLevel = 'medium';
  }

  // Análisis de correlaciones para insights
  const symbols = positions.map(p => p.symbol);
  const correlations = await calculateCorrelationMatrix(symbols, 90); // 3 meses

  const highCorrelations = correlations.filter(c => Math.abs(c.correlation) > 0.7);
  const lowCorrelations = correlations.filter(c => Math.abs(c.correlation) < 0.3);
  const negativeCorrelations = correlations.filter(c => c.correlation < -0.3);

  const correlationInsights = [];

  if (highCorrelations.length > 0) {
    correlationInsights.push({
      type: 'high_correlation' as const,
      pairs: highCorrelations.map(c => ({
        symbol1: c.symbol1,
        symbol2: c.symbol2,
        correlation: c.correlation
      })),
      recommendation: 'Considera reducir la exposición a activos altamente correlacionados para mejorar la diversificación.'
    });
  }

  if (lowCorrelations.length > 0) {
    correlationInsights.push({
      type: 'low_correlation' as const,
      pairs: lowCorrelations.slice(0, 3).map(c => ({
        symbol1: c.symbol1,
        symbol2: c.symbol2,
        correlation: c.correlation
      })),
      recommendation: 'Excelente diversificación: estos activos tienen baja correlación.'
    });
  }

  if (negativeCorrelations.length > 0) {
    correlationInsights.push({
      type: 'negative_correlation' as const,
      pairs: negativeCorrelations.map(c => ({
        symbol1: c.symbol1,
        symbol2: c.symbol2,
        correlation: c.correlation
      })),
      recommendation: 'Activos con correlación negativa proporcionan excelente diversificación.'
    });
  }

  return {
    sectorAllocation,
    regionAllocation,
    concentrationRisk: {
      herfindahlIndex,
      maxSingleHolding,
      top5Concentration,
      riskLevel
    },
    correlationInsights
  };
});

// Obtener recomendaciones de rebalanceo basadas en correlaciones
export const getRebalancingRecommendations = cache(async (
  positions: Array<{
    symbol: string;
    percentage: number;
    sector?: string;
  }>
): Promise<Array<{
  type: 'reduce' | 'increase' | 'add' | 'remove';
  symbol: string;
  currentWeight: number;
  recommendedWeight: number;
  reason: string;
}>> => {
  const correlations = await calculateCorrelationMatrix(
    positions.map(p => p.symbol), 
    90
  );

  const recommendations = [];

  // Identificar activos altamente correlacionados
  const highCorrPairs = correlations.filter(c => Math.abs(c.correlation) > 0.8);
  
  for (const pair of highCorrPairs) {
    const pos1 = positions.find(p => p.symbol === pair.symbol1);
    const pos2 = positions.find(p => p.symbol === pair.symbol2);
    
    if (pos1 && pos2) {
      // Recomendar reducir el de menor peso
      if (pos1.percentage > pos2.percentage) {
        recommendations.push({
          type: 'reduce' as const,
          symbol: pos2.symbol,
          currentWeight: pos2.percentage,
          recommendedWeight: pos2.percentage * 0.5,
          reason: `Alta correlación (${(pair.correlation * 100).toFixed(1)}%) con ${pos1.symbol}`
        });
      } else {
        recommendations.push({
          type: 'reduce' as const,
          symbol: pos1.symbol,
          currentWeight: pos1.percentage,
          recommendedWeight: pos1.percentage * 0.5,
          reason: `Alta correlación (${(pair.correlation * 100).toFixed(1)}%) con ${pos2.symbol}`
        });
      }
    }
  }

  // Identificar sectores sobreponderados
  const sectorWeights = new Map<string, number>();
  positions.forEach(pos => {
    const sector = pos.sector || 'Unknown';
    sectorWeights.set(sector, (sectorWeights.get(sector) || 0) + pos.percentage);
  });

  for (const [sector, weight] of sectorWeights.entries()) {
    if (weight > 0.4) { // Más del 40% en un sector
      const sectorPositions = positions.filter(p => (p.sector || 'Unknown') === sector);
      for (const pos of sectorPositions) {
        recommendations.push({
          type: 'reduce' as const,
          symbol: pos.symbol,
          currentWeight: pos.percentage,
          recommendedWeight: pos.percentage * 0.8,
          reason: `Sobreponderación en sector ${sector} (${(weight * 100).toFixed(1)}%)`
        });
      }
    }
  }

  return recommendations;
});
