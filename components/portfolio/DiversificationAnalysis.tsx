'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import { Shield, AlertTriangle, CheckCircle, TrendingUp } from 'lucide-react';
import { analyzeDiversification, type DiversificationAnalysis } from '@/lib/actions/correlation.actions';

type DiversificationAnalysisProps = {
  positions: Array<{
    symbol: string;
    percentage: number;
    sector?: string;
    region?: string;
  }>;
};

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00ff00', '#0088fe', '#00c49f', '#ffbb28', '#ff8042'];

export default function DiversificationAnalysis({ positions }: DiversificationAnalysisProps) {
  const [analysis, setAnalysis] = useState<DiversificationAnalysis | null>(null);
  const [loading, setLoading] = useState(false);

  const loadAnalysis = async () => {
    if (positions.length === 0) return;
    
    setLoading(true);
    try {
      const data = await analyzeDiversification(positions);
      setAnalysis(data);
    } catch (error) {
      console.error('Error loading diversification analysis:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalysis();
  }, [positions]);

  const getRiskColor = (riskLevel: 'low' | 'medium' | 'high') => {
    switch (riskLevel) {
      case 'low': return 'text-green-600';
      case 'medium': return 'text-yellow-600';
      case 'high': return 'text-red-600';
    }
  };

  const getRiskIcon = (riskLevel: 'low' | 'medium' | 'high') => {
    switch (riskLevel) {
      case 'low': return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'medium': return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case 'high': return <AlertTriangle className="h-5 w-5 text-red-500" />;
    }
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Análisis de Diversificación</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Analizando diversificación...</p>
        </CardContent>
      </Card>
    );
  }

  if (!analysis) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Análisis de Diversificación</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">No hay datos suficientes para el análisis</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Análisis de Diversificación
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Nivel de riesgo general */}
        <div className="text-center p-4 bg-muted rounded-lg">
          <div className="flex items-center justify-center gap-2 mb-2">
            {getRiskIcon(analysis.concentrationRisk.riskLevel)}
            <span className={`text-lg font-semibold ${getRiskColor(analysis.concentrationRisk.riskLevel)}`}>
              Riesgo de Concentración: {analysis.concentrationRisk.riskLevel.toUpperCase()}
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            {analysis.concentrationRisk.riskLevel === 'low' && 'Excelente diversificación del portfolio'}
            {analysis.concentrationRisk.riskLevel === 'medium' && 'Diversificación moderada, considera rebalancear'}
            {analysis.concentrationRisk.riskLevel === 'high' && 'Alta concentración, riesgo elevado de diversificación'}
          </p>
        </div>

        {/* Métricas de concentración */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="text-center p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground mb-2">Índice Herfindahl</p>
            <p className="text-2xl font-bold">{analysis.concentrationRisk.herfindahlIndex.toFixed(3)}</p>
            <Progress 
              value={analysis.concentrationRisk.herfindahlIndex * 100} 
              className="mt-2"
            />
            <p className="text-xs text-muted-foreground mt-1">
              {analysis.concentrationRisk.herfindahlIndex < 0.15 ? 'Bajo' : 
               analysis.concentrationRisk.herfindahlIndex < 0.25 ? 'Medio' : 'Alto'}
            </p>
          </div>

          <div className="text-center p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground mb-2">Mayor Holding</p>
            <p className="text-2xl font-bold">{(analysis.concentrationRisk.maxSingleHolding * 100).toFixed(1)}%</p>
            <Progress 
              value={analysis.concentrationRisk.maxSingleHolding * 100} 
              className="mt-2"
            />
            <p className="text-xs text-muted-foreground mt-1">
              {analysis.concentrationRisk.maxSingleHolding < 0.2 ? 'Bajo' : 
               analysis.concentrationRisk.maxSingleHolding < 0.3 ? 'Medio' : 'Alto'}
            </p>
          </div>

          <div className="text-center p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground mb-2">Top 5 Holdings</p>
            <p className="text-2xl font-bold">{(analysis.concentrationRisk.top5Concentration * 100).toFixed(1)}%</p>
            <Progress 
              value={analysis.concentrationRisk.top5Concentration * 100} 
              className="mt-2"
            />
            <p className="text-xs text-muted-foreground mt-1">
              {analysis.concentrationRisk.top5Concentration < 0.5 ? 'Bajo' : 
               analysis.concentrationRisk.top5Concentration < 0.7 ? 'Medio' : 'Alto'}
            </p>
          </div>
        </div>

        {/* Distribución por sectores */}
        <div>
          <h4 className="text-lg font-semibold mb-4">Distribución por Sectores</h4>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="h-64">
              <ResponsiveContainer width="100%" height={300} minWidth={0} minHeight={200}>
                <PieChart>
                  <Pie
                    data={analysis.sectorAllocation}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ sector, percentage }) => `${sector}: ${(percentage as number).toFixed(1)}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="percentage"
                  >
                    {analysis.sectorAllocation.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [`${(value as number).toFixed(1)}%`, 'Porcentaje']} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="space-y-2">
              {analysis.sectorAllocation.map((sector, index) => (
                <div key={sector.sector} className="flex items-center justify-between p-2 rounded-lg bg-muted">
                  <div className="flex items-center gap-2">
                    <div 
                      className="w-4 h-4 rounded" 
                      style={{ backgroundColor: COLORS[index % COLORS.length] }}
                    />
                    <span className="font-medium">{sector.sector}</span>
                    <Badge variant="outline" className="text-xs">
                      {sector.count} activos
                    </Badge>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold">{sector.percentage.toFixed(1)}%</p>
                    <Progress value={sector.percentage} className="w-20 h-2" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Distribución por regiones */}
        {analysis.regionAllocation.length > 1 && (
          <div>
            <h4 className="text-lg font-semibold mb-4">Distribución por Regiones</h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height={300} minWidth={0} minHeight={200}>
                <BarChart data={analysis.regionAllocation}>
                  <XAxis dataKey="region" />
                  <YAxis />
                  <Tooltip formatter={(value) => [`${(value as number).toFixed(1)}%`, 'Porcentaje']} />
                  <Bar dataKey="percentage" fill="#8884d8" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Insights de correlación */}
        {analysis.correlationInsights.length > 0 && (
          <div className="border-t pt-4">
            <h4 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Insights de Correlación
            </h4>
            <div className="space-y-3">
              {analysis.correlationInsights.map((insight, index) => (
                <div key={index} className={`p-4 rounded-lg ${
                  insight.type === 'high_correlation' ? 'bg-red-50 dark:bg-red-950' :
                  insight.type === 'low_correlation' ? 'bg-green-50 dark:bg-green-950' :
                  'bg-blue-50 dark:bg-blue-950'
                }`}>
                  <div className="flex items-start gap-3">
                    {insight.type === 'high_correlation' && <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5" />}
                    {insight.type === 'low_correlation' && <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />}
                    {insight.type === 'negative_correlation' && <TrendingUp className="h-5 w-5 text-blue-500 mt-0.5" />}
                    
                    <div className="flex-1">
                      <p className="font-medium mb-2">
                        {insight.type === 'high_correlation' && 'Alta Correlación Detectada'}
                        {insight.type === 'low_correlation' && 'Excelente Diversificación'}
                        {insight.type === 'negative_correlation' && 'Correlación Negativa Beneficiosa'}
                      </p>
                      
                      <div className="space-y-1 mb-2">
                        {insight.pairs.slice(0, 3).map((pair, pairIndex) => (
                          <div key={pairIndex} className="text-sm">
                            <span className="font-mono">{pair.symbol1}</span> ↔ 
                            <span className="font-mono">{pair.symbol2}</span>
                            <span className="ml-2 text-muted-foreground">
                              ({(pair.correlation * 100).toFixed(1)}%)
                            </span>
                          </div>
                        ))}
                      </div>
                      
                      <p className="text-sm text-muted-foreground">
                        {insight.recommendation}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
