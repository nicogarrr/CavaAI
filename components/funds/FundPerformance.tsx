'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useState } from 'react';
import { TrendingUp, TrendingDown, BarChart3 } from 'lucide-react';

type FundData = {
  symbol: string;
  profile: {
    ticker?: string;
    name?: string;
    exchange?: string;
    currency?: string;
    country?: string;
    ipo?: string;
    logo?: string;
    weburl?: string;
  };
  holdings: Array<{
    symbol?: string;
    name?: string;
    percent?: number;
  }>;
  candles: {
    c: number[];
    t: number[];
    o: number[];
    h: number[];
    l: number[];
    v: number[];
  } | null;
};

type FundPerformanceProps = {
  fundData: FundData;
};

export default function FundPerformance({ fundData }: FundPerformanceProps) {
  const [selectedPeriod, setSelectedPeriod] = useState<'1M' | '3M' | '6M' | '1Y' | 'MAX'>('1Y');
  
  if (!fundData.candles) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Rendimiento Histórico</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">No hay datos históricos disponibles</p>
        </CardContent>
      </Card>
    );
  }

  const { c: closes, t: timestamps } = fundData.candles;
  const currentPrice = closes[closes.length - 1];
  
  // Calculate performance for different periods
  const getPerformanceData = (period: string) => {
    const now = Date.now() / 1000;
    let daysBack = 365; // Default to 1 year
    
    switch (period) {
      case '1M': daysBack = 30; break;
      case '3M': daysBack = 90; break;
      case '6M': daysBack = 180; break;
      case '1Y': daysBack = 365; break;
      case 'MAX': daysBack = timestamps.length; break;
    }
    
    const cutoffTime = now - (daysBack * 24 * 60 * 60);
    const startIndex = timestamps.findIndex(t => t >= cutoffTime);
    const startPrice = startIndex >= 0 ? closes[startIndex] : closes[0];
    
    const change = currentPrice - startPrice;
    const changePercent = startPrice > 0 ? (change / startPrice) * 100 : 0;
    
    return { change, changePercent, startPrice };
  };

  const performance = getPerformanceData(selectedPeriod);
  const isPositive = performance.change >= 0;

  // Calculate volatility (standard deviation of daily returns)
  const dailyReturns = [];
  for (let i = 1; i < closes.length; i++) {
    const return_ = (closes[i] - closes[i-1]) / closes[i-1];
    dailyReturns.push(return_);
  }
  
  const avgReturn = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length;
  const variance = dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) / dailyReturns.length;
  const volatility = Math.sqrt(variance) * 100; // Annualized volatility

  // Calculate Sharpe ratio (simplified)
  const riskFreeRate = 0.02; // Assume 2% risk-free rate
  const excessReturn = (performance.changePercent / 100) - riskFreeRate;
  const sharpeRatio = volatility > 0 ? excessReturn / (volatility / 100) : 0;

  // Calculate max drawdown
  let maxDrawdown = 0;
  let peak = closes[0];
  for (let i = 1; i < closes.length; i++) {
    if (closes[i] > peak) {
      peak = closes[i];
    }
    const drawdown = (peak - closes[i]) / peak;
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown;
    }
  }

  const periods = [
    { key: '1M', label: '1 Mes' },
    { key: '3M', label: '3 Meses' },
    { key: '6M', label: '6 Meses' },
    { key: '1Y', label: '1 Año' },
    { key: 'MAX', label: 'Máximo' },
  ] as const;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Rendimiento Histórico
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Period Selector */}
        <div className="flex gap-2 flex-wrap">
          {periods.map((period) => (
            <button
              key={period.key}
              onClick={() => setSelectedPeriod(period.key)}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                selectedPeriod === period.key
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted hover:bg-muted/80'
              }`}
            >
              {period.label}
            </button>
          ))}
        </div>

        {/* Performance Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="text-center p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground">Rendimiento {periods.find(p => p.key === selectedPeriod)?.label}</p>
            <div className="flex items-center justify-center gap-2 mt-2">
              {isPositive ? (
                <TrendingUp className="h-5 w-5 text-green-500" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-500" />
              )}
              <span className={`text-2xl font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                {isPositive ? '+' : ''}{performance.changePercent.toFixed(2)}%
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {isPositive ? '+' : ''}${performance.change.toFixed(2)}
            </p>
          </div>

          <div className="text-center p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground">Volatilidad Anualizada</p>
            <p className="text-2xl font-bold mt-2">{volatility.toFixed(2)}%</p>
            <Badge variant={volatility < 15 ? 'default' : volatility < 25 ? 'secondary' : 'destructive'} className="mt-1">
              {volatility < 15 ? 'Baja' : volatility < 25 ? 'Media' : 'Alta'}
            </Badge>
          </div>

          <div className="text-center p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground">Ratio de Sharpe</p>
            <p className="text-2xl font-bold mt-2">{sharpeRatio.toFixed(2)}</p>
            <Badge variant={sharpeRatio > 1 ? 'default' : sharpeRatio > 0 ? 'secondary' : 'destructive'} className="mt-1">
              {sharpeRatio > 1 ? 'Excelente' : sharpeRatio > 0 ? 'Bueno' : 'Pobre'}
            </Badge>
          </div>
        </div>

        {/* Additional Risk Metrics */}
        <div className="border-t pt-4">
          <h4 className="text-lg font-semibold mb-4">Métricas de Riesgo</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Máxima Caída (Max Drawdown)</p>
              <p className="text-xl font-bold text-red-600">-{(maxDrawdown * 100).toFixed(2)}%</p>
            </div>
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Precio Inicial</p>
              <p className="text-xl font-bold">${performance.startPrice.toFixed(2)}</p>
            </div>
          </div>
        </div>

        {/* Simple Sparkline */}
        <div className="border-t pt-4">
          <h4 className="text-lg font-semibold mb-4">Evolución del Precio</h4>
          <div className="h-32 bg-muted rounded-lg p-4 flex items-end justify-between">
            {closes.slice(-30).map((price, index) => {
              const height = ((price - Math.min(...closes.slice(-30))) / 
                (Math.max(...closes.slice(-30)) - Math.min(...closes.slice(-30)))) * 100;
              return (
                <div
                  key={index}
                  className={`w-1 ${isPositive ? 'bg-green-500' : 'bg-red-500'}`}
                  style={{ height: `${Math.max(height, 2)}%` }}
                />
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
