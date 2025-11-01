'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { TrendingUp, TrendingDown, BarChart3, ExternalLink } from 'lucide-react';

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

type FundComparisonProps = {
  fundData: FundData;
};

export default function FundComparison({ fundData }: FundComparisonProps) {
  const { symbol, candles } = fundData;

  if (!candles) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Comparación</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">No hay datos suficientes para comparación</p>
        </CardContent>
      </Card>
    );
  }

  const currentPrice = candles.c[candles.c.length - 1];
  const yearAgoPrice = candles.c[Math.max(0, candles.c.length - 252)]; // Approximate 1 year ago
  const yearReturn = yearAgoPrice > 0 ? ((currentPrice - yearAgoPrice) / yearAgoPrice) * 100 : 0;

  // Mock benchmark data (in real app, this would come from API)
  const benchmarks = [
    { name: 'S&P 500', symbol: 'SPY', return: 12.5, volatility: 18.2, sharpe: 0.85 },
    { name: 'MSCI World', symbol: 'URTH', return: 10.8, volatility: 16.5, sharpe: 0.92 },
    { name: 'Emerging Markets', symbol: 'VWO', return: 8.3, volatility: 22.1, sharpe: 0.65 },
    { name: 'Gold', symbol: 'GLD', return: 5.2, volatility: 12.8, sharpe: 0.45 },
  ];

  // Calculate our fund's metrics
  const dailyReturns = [];
  for (let i = 1; i < candles.c.length; i++) {
    const return_ = (candles.c[i] - candles.c[i-1]) / candles.c[i-1];
    dailyReturns.push(return_);
  }
  
  const avgReturn = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length;
  const variance = dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) / dailyReturns.length;
  const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100;
  const annualReturn = avgReturn * 252 * 100;
  const sharpeRatio = volatility > 0 ? (annualReturn - 2) / volatility : 0;

  const ourFund = {
    name: fundData.profile.name || symbol,
    symbol: symbol,
    return: yearReturn,
    volatility: volatility,
    sharpe: sharpeRatio,
  };

  const allFunds = [ourFund, ...benchmarks];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Comparación con Benchmarks
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Performance Comparison */}
        <div>
          <h4 className="text-sm font-semibold mb-3">Rendimiento Anual</h4>
          <div className="space-y-2">
            {allFunds.map((fund, index) => (
              <div key={fund.symbol} className={`flex items-center justify-between p-2 rounded-lg ${
                index === 0 ? 'bg-primary/10 border border-primary/20' : 'bg-muted'
              }`}>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{fund.symbol}</span>
                  {index === 0 && <Badge variant="default" className="text-xs">Tu ETF</Badge>}
                </div>
                <div className="flex items-center gap-2">
                  {fund.return >= 0 ? (
                    <TrendingUp className="h-4 w-4 text-green-500" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-red-500" />
                  )}
                  <span className={`font-semibold ${fund.return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {fund.return >= 0 ? '+' : ''}{fund.return.toFixed(1)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Risk-Return Scatter */}
        <div>
          <h4 className="text-sm font-semibold mb-3">Riesgo vs Rendimiento</h4>
          <div className="space-y-2">
            {allFunds.map((fund, index) => (
              <div key={fund.symbol} className="flex items-center justify-between p-2 rounded-lg bg-muted">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{fund.symbol}</span>
                  {index === 0 && <Badge variant="outline" className="text-xs">Tu ETF</Badge>}
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold">{fund.return.toFixed(1)}%</div>
                  <div className="text-xs text-muted-foreground">Vol: {fund.volatility.toFixed(1)}%</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Sharpe Ratio Comparison */}
        <div>
          <h4 className="text-sm font-semibold mb-3">Ratio de Sharpe</h4>
          <div className="space-y-2">
            {allFunds.map((fund, index) => (
              <div key={fund.symbol} className="flex items-center justify-between p-2 rounded-lg bg-muted">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{fund.symbol}</span>
                  {index === 0 && <Badge variant="outline" className="text-xs">Tu ETF</Badge>}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={fund.sharpe > 1 ? 'default' : fund.sharpe > 0.5 ? 'secondary' : 'destructive'}>
                    {fund.sharpe.toFixed(2)}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Ranking */}
        <div>
          <h4 className="text-sm font-semibold mb-3">Ranking por Rendimiento</h4>
          <div className="space-y-1">
            {allFunds
              .sort((a, b) => b.return - a.return)
              .map((fund, index) => (
                <div key={fund.symbol} className="flex items-center justify-between p-2 rounded-lg bg-muted">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-muted-foreground">#{index + 1}</span>
                    <span className="font-medium text-sm">{fund.symbol}</span>
                    {fund.symbol === symbol && <Badge variant="default" className="text-xs">Tu ETF</Badge>}
                  </div>
                  <span className="text-sm font-semibold">{fund.return.toFixed(1)}%</span>
                </div>
              ))}
          </div>
        </div>

        {/* External Links */}
        <div className="border-t pt-4">
          <h4 className="text-sm font-semibold mb-3">Análisis Externo</h4>
          <div className="space-y-2">
            <Button variant="outline" size="sm" className="w-full justify-start" asChild>
              <a href={`https://www.morningstar.com/etfs/${symbol}`} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-2" />
                Ver en Morningstar
              </a>
            </Button>
            <Button variant="outline" size="sm" className="w-full justify-start" asChild>
              <a href={`https://finance.yahoo.com/quote/${symbol}`} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-2" />
                Ver en Yahoo Finance
              </a>
            </Button>
            <Button variant="outline" size="sm" className="w-full justify-start" asChild>
              <a href={`https://www.etf.com/${symbol}`} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-2" />
                Ver en ETF.com
              </a>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
