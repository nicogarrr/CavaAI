'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { AlertTriangle, Shield, TrendingUp, TrendingDown } from 'lucide-react';

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

type FundRiskMetricsProps = {
  fundData: FundData;
};

export default function FundRiskMetrics({ fundData }: FundRiskMetricsProps) {
  const { candles, holdings } = fundData;

  if (!candles) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Métricas de Riesgo</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">No hay datos suficientes para calcular métricas de riesgo</p>
        </CardContent>
      </Card>
    );
  }

  const { c: closes, h: highs, l: lows } = candles;
  const currentPrice = closes[closes.length - 1];

  // Calculate daily returns
  const dailyReturns = [];
  for (let i = 1; i < closes.length; i++) {
    const return_ = (closes[i] - closes[i-1]) / closes[i-1];
    dailyReturns.push(return_);
  }

  // Calculate volatility (annualized)
  const avgReturn = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length;
  const variance = dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) / dailyReturns.length;
  const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100; // Annualized

  // Calculate Sharpe ratio
  const riskFreeRate = 0.02; // 2% risk-free rate
  const annualReturn = avgReturn * 252 * 100;
  const excessReturn = annualReturn - (riskFreeRate * 100);
  const sharpeRatio = volatility > 0 ? excessReturn / volatility : 0;

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

  // Calculate Value at Risk (VaR) - 95% confidence
  const sortedReturns = [...dailyReturns].sort((a, b) => a - b);
  const var95 = sortedReturns[Math.floor(sortedReturns.length * 0.05)] * 100;

  // Calculate Beta (simplified - would need market data for real calculation)
  const beta = 1.0; // Placeholder - would need S&P 500 data

  // Calculate concentration risk
  const top5Holdings = holdings
    .filter(h => h.percent && h.percent > 0)
    .sort((a, b) => (b.percent || 0) - (a.percent || 0))
    .slice(0, 5);
  const top5Percentage = top5Holdings.reduce((sum, h) => sum + (h.percent || 0), 0);

  // Risk level assessment
  const getRiskLevel = () => {
    if (volatility < 15 && maxDrawdown < 0.15 && sharpeRatio > 1) return 'Bajo';
    if (volatility < 25 && maxDrawdown < 0.25 && sharpeRatio > 0.5) return 'Medio';
    return 'Alto';
  };

  const riskLevel = getRiskLevel();
  const riskColor = riskLevel === 'Bajo' ? 'text-green-600' : riskLevel === 'Medio' ? 'text-yellow-600' : 'text-red-600';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Métricas de Riesgo
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Overall Risk Level */}
        <div className="text-center p-4 bg-muted rounded-lg">
          <p className="text-sm text-muted-foreground mb-2">Nivel de Riesgo General</p>
          <div className="flex items-center justify-center gap-2">
            {riskLevel === 'Bajo' ? (
              <Shield className="h-6 w-6 text-green-600" />
            ) : riskLevel === 'Medio' ? (
              <AlertTriangle className="h-6 w-6 text-yellow-600" />
            ) : (
              <AlertTriangle className="h-6 w-6 text-red-600" />
            )}
            <span className={`text-2xl font-bold ${riskColor}`}>{riskLevel}</span>
          </div>
        </div>

        {/* Key Risk Metrics */}
        <div className="space-y-4">
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium">Volatilidad Anualizada</span>
              <span className="text-sm font-semibold">{volatility.toFixed(2)}%</span>
            </div>
            <Progress 
              value={Math.min(volatility, 50)} 
              className="h-2"
            />
            <p className="text-xs text-muted-foreground mt-1">
              {volatility < 15 ? 'Baja volatilidad' : volatility < 25 ? 'Volatilidad moderada' : 'Alta volatilidad'}
            </p>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium">Máxima Caída (Max Drawdown)</span>
              <span className="text-sm font-semibold text-red-600">-{(maxDrawdown * 100).toFixed(2)}%</span>
            </div>
            <Progress 
              value={maxDrawdown * 100} 
              className="h-2"
            />
            <p className="text-xs text-muted-foreground mt-1">
              {maxDrawdown < 0.15 ? 'Drawdown controlado' : maxDrawdown < 0.25 ? 'Drawdown moderado' : 'Drawdown alto'}
            </p>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium">Ratio de Sharpe</span>
              <span className="text-sm font-semibold">{sharpeRatio.toFixed(2)}</span>
            </div>
            <Progress 
              value={Math.min(Math.max(sharpeRatio * 25, 0), 100)} 
              className="h-2"
            />
            <p className="text-xs text-muted-foreground mt-1">
              {sharpeRatio > 1 ? 'Excelente' : sharpeRatio > 0.5 ? 'Bueno' : 'Pobre'}
            </p>
          </div>
        </div>

        {/* Additional Risk Metrics */}
        <div className="border-t pt-4 space-y-3">
          <h4 className="text-sm font-semibold">Métricas Adicionales</h4>
          
          <div className="grid grid-cols-2 gap-4 text-center">
            <div className="p-3 bg-muted rounded-lg">
              <p className="text-xs text-muted-foreground">VaR (95%)</p>
              <p className="text-lg font-bold text-red-600">{var95.toFixed(2)}%</p>
            </div>
            <div className="p-3 bg-muted rounded-lg">
              <p className="text-xs text-muted-foreground">Beta</p>
              <p className="text-lg font-bold">{beta.toFixed(2)}</p>
            </div>
          </div>

          <div className="p-3 bg-muted rounded-lg">
            <p className="text-xs text-muted-foreground mb-2">Concentración (Top 5 Holdings)</p>
            <div className="flex justify-between items-center">
              <span className="text-sm font-medium">{top5Percentage.toFixed(1)}%</span>
              <Badge variant={top5Percentage > 50 ? 'destructive' : top5Percentage > 30 ? 'secondary' : 'default'}>
                {top5Percentage > 50 ? 'Alta' : top5Percentage > 30 ? 'Media' : 'Baja'}
              </Badge>
            </div>
            <Progress 
              value={top5Percentage} 
              className="h-2 mt-2"
            />
          </div>
        </div>

        {/* Risk Warnings */}
        <div className="border-t pt-4">
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Consideraciones de Riesgo
          </h4>
          <div className="space-y-2 text-xs text-muted-foreground">
            {volatility > 25 && (
              <p>• Alta volatilidad: El precio puede fluctuar significativamente</p>
            )}
            {maxDrawdown > 0.25 && (
              <p>• Alto drawdown: Pérdidas máximas considerables</p>
            )}
            {sharpeRatio < 0.5 && (
              <p>• Bajo ratio de Sharpe: Rendimiento ajustado al riesgo pobre</p>
            )}
            {top5Percentage > 50 && (
              <p>• Alta concentración: Riesgo por dependencia de pocos holdings</p>
            )}
            {var95 < -5 && (
              <p>• Alto VaR: Posibles pérdidas significativas en el 5% de los casos</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
